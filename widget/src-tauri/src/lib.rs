//! Eyrie's top-bar widget (docs/home-and-widget.md §4).
//!
//! A tray icon (macOS menu bar, Linux AppIndicator) plus a small panel window. Everything
//! comes from Eyrie's own API on 127.0.0.1: the summary is polled here every 10 s and drives
//! the icon, the menu-bar title and the menu; the panel gets it pushed as an event.
//!
//! The panel never talks HTTP itself. Its origin would fail Eyrie's Origin check (on purpose)
//! and it would need the token in JavaScript, so it calls the commands below, which read
//! ~/.eyrie/token and proxy to the API. The capability file gives the webview nothing else.

use std::{
    fs,
    path::PathBuf,
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::{
    image::Image,
    menu::{CheckMenuItem, IsMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, Position, Rect, Runtime, WebviewWindow, WindowEvent,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_opener::OpenerExt;

const TRAY_ID: &str = "eyrie";
const PANEL: &str = "panel";
const POLL: Duration = Duration::from_secs(10);

// ------------------------------------------------------------------ talking to Eyrie

fn base_url() -> String {
    // Only ever a loopback address: the widget must not be pointed at another machine.
    let url = std::env::var("EYRIE_URL").unwrap_or_else(|_| "http://127.0.0.1:8787".into());
    let ok = ["http://127.0.0.1:", "http://localhost:"].iter().any(|p| url.starts_with(p));
    if ok { url.trim_end_matches('/').to_string() } else { "http://127.0.0.1:8787".into() }
}

fn token() -> Result<String, String> {
    let dir = std::env::var("EYRIE_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| dirs::home_dir().unwrap_or_default().join(".eyrie"));
    fs::read_to_string(dir.join("token"))
        .map(|t| t.trim().to_string())
        .map_err(|_| "Eyrie's token isn't there yet. Is Eyrie installed (make install)?".into())
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .http_status_as_error(false)
        .timeout_global(Some(Duration::from_secs(8)))
        .build()
        .into()
}

/// Returns (status, json body). Network errors mean Eyrie isn't running.
fn request(method: &str, path: &str, body: Option<Value>, if_match: Option<&str>) -> Result<(u16, Value), String> {
    let url = format!("{}{}", base_url(), path);
    let a = agent();
    let unreachable = |e: ureq::Error| format!("Eyrie isn't answering at {} ({e})", base_url());
    let mut resp = if method == "GET" {
        a.get(&url).call().map_err(unreachable)?
    } else {
        let mut req = match method {
            "POST" => a.post(&url),
            "PATCH" => a.patch(&url),
            _ => return Err(format!("unsupported method {method}")),
        };
        req = req.header("X-Eyrie-Token", &token()?);
        if let Some(etag) = if_match {
            req = req.header("If-Match", etag);
        }
        req.send_json(body.unwrap_or(json!({}))).map_err(unreachable)?
    };
    let status = resp.status().as_u16();
    let value = resp.body_mut().read_json::<Value>().unwrap_or(Value::Null);
    Ok((status, value))
}

fn get(path: &str) -> Result<Value, String> {
    match request("GET", path, None, None)? {
        (200, v) => Ok(v),
        (s, v) => Err(v["detail"].as_str().map(String::from).unwrap_or(format!("HTTP {s}"))),
    }
}

// ------------------------------------------------------------------ settings

#[derive(Serialize, Deserialize, Clone)]
struct Settings {
    /// macOS only: show today's cost next to the icon in the menu bar.
    show_cost: bool,
    /// Start at login is switched on once, on the first run; after that it's the user's choice.
    autostart_initialised: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Self { show_cost: true, autostart_initialised: false }
    }
}

struct AppState {
    settings: Mutex<Settings>,
    last: Mutex<Option<Value>>,
}

fn settings_path<R: Runtime>(app: &AppHandle<R>) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("settings.json"))
}

fn load_settings<R: Runtime>(app: &AppHandle<R>) -> Settings {
    settings_path(app)
        .and_then(|p| fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_settings<R: Runtime>(app: &AppHandle<R>, s: &Settings) {
    if let Some(p) = settings_path(app) {
        let _ = fs::create_dir_all(p.parent().unwrap());
        let _ = fs::write(p, serde_json::to_string_pretty(s).unwrap_or_default());
    }
}

// ------------------------------------------------------------------ commands for the panel

#[tauri::command]
async fn summary(state: tauri::State<'_, AppState>) -> Result<Value, String> {
    if let Some(v) = state.last.lock().unwrap().clone() {
        return Ok(v);
    }
    tauri::async_runtime::spawn_blocking(|| get("/api/v1/summary")).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn refresh(app: AppHandle) -> Result<Value, String> {
    let v = tauri::async_runtime::spawn_blocking(|| get("/api/v1/summary")).await.map_err(|e| e.to_string())??;
    apply_summary(&app, &v);
    Ok(v)
}

/// Runs one of Eyrie's declared actions (the API validates, previews, confirms and audits).
#[tauri::command]
async fn action(id: String, params: Value, dry_run: bool, confirm: bool) -> Result<Value, String> {
    if !id.chars().all(|c| c.is_ascii_lowercase() || c == '.' || c == '_') {
        return Err("bad action id".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let (status, body) = request("POST", &format!("/api/v1/actions/{id}"),
                                     Some(json!({"params": params, "dry_run": dry_run, "confirm": confirm})), None)?;
        Ok(json!({"status": status, "body": body}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Adds a task to Personal/Tasks.md, carrying the file's current etag like the web app does.
#[tauri::command]
async fn add_task(text: String) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let current = get("/api/v1/tasks")?;
        let etag = current["etag"].as_str().unwrap_or("absent").to_string();
        let (status, body) = request("POST", "/api/v1/tasks", Some(json!({"text": text})), Some(&etag))?;
        if status == 200 { Ok(body) } else { Err(body["detail"].as_str().unwrap_or("Couldn't add the task").into()) }
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Opens a page of Eyrie in the default browser. Only Eyrie's own pages.
#[tauri::command]
fn open_eyrie(app: AppHandle, path: String) -> Result<(), String> {
    if !path.starts_with('/') || path.starts_with("//") || path.contains("..") {
        return Err("not an Eyrie page".into());
    }
    hide_panel(&app);
    app.opener().open_url(format!("{}{}", base_url(), path), None::<&str>).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_settings(app: AppHandle, state: tauri::State<'_, AppState>) -> Value {
    let s = state.settings.lock().unwrap().clone();
    json!({
        "show_cost": s.show_cost,
        "autostart": app.autolaunch().is_enabled().unwrap_or(false),
        "platform": std::env::consts::OS,
        "base_url": base_url(),
        "home": dirs::home_dir().map(|h| h.display().to_string()).unwrap_or_default(),
    })
}

#[tauri::command]
fn set_show_cost(app: AppHandle, state: tauri::State<'_, AppState>, on: bool) {
    let s = {
        let mut s = state.settings.lock().unwrap();
        s.show_cost = on;
        s.clone()
    };
    save_settings(&app, &s);
    if let Some(v) = state.last.lock().unwrap().clone() {
        apply_summary(&app, &v);
    }
}

#[tauri::command]
fn set_autostart(app: AppHandle, on: bool) -> Result<(), String> {
    let al = app.autolaunch();
    if on { al.enable() } else { al.disable() }.map_err(|e| e.to_string())
}

/// When Eyrie isn't answering: start (or restart) its background service.
#[tauri::command]
async fn start_eyrie() -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let (cmd, args): (&str, Vec<String>) = if cfg!(target_os = "macos") {
            let uid = std::process::Command::new("id").arg("-u").output().map_err(|e| e.to_string())?;
            let uid = String::from_utf8_lossy(&uid.stdout).trim().to_string();
            ("launchctl", vec!["kickstart".into(), "-k".into(), format!("gui/{uid}/local.eyrie")])
        } else {
            ("systemctl", vec!["--user".into(), "restart".into(), "eyrie.service".into()])
        };
        let out = std::process::Command::new(cmd).args(&args).output().map_err(|e| e.to_string())?;
        if out.status.success() {
            Ok(format!("$ {cmd} {}", args.join(" ")))
        } else {
            Err(format!("Couldn't start Eyrie's service ({}). Install it with `make install`.",
                        String::from_utf8_lossy(&out.stderr).trim()))
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn hide(app: AppHandle) {
    hide_panel(&app);
}

#[tauri::command]
fn quit(app: AppHandle) {
    app.exit(0);
}

// ------------------------------------------------------------------ tray, menu, panel

fn tray_image(state: &str) -> Image<'static> {
    let bytes: &'static [u8] = match state {
        "problem" => include_bytes!("../icons/tray-problem@2x.png"),
        "attention" => include_bytes!("../icons/tray-attention@2x.png"),
        _ => include_bytes!("../icons/tray-ok@2x.png"),
    };
    Image::from_bytes(bytes).expect("bundled tray icon")
}

fn money(v: &Value) -> String {
    format!("${:.2}", v.as_f64().unwrap_or(0.0))
}

fn state_text(summary: &Value) -> String {
    let n = summary["attention"].as_array().map(|a| a.len()).unwrap_or(0);
    match n {
        0 => "All fine".into(),
        1 => "1 needs you".into(),
        n => format!("{n} need you"),
    }
}

/// The tray menu. On macOS it's the right-click menu; on Linux it's the only interaction
/// (AppIndicator has no click events), so it also carries the key facts.
fn build_menu<R: Runtime>(app: &AppHandle<R>, summary: Option<&Value>) -> tauri::Result<Menu<R>> {
    let mut items: Vec<Box<dyn IsMenuItem<R>>> = vec![
        Box::new(MenuItem::with_id(app, "show", "Show panel", true, None::<&str>)?),
        Box::new(PredefinedMenuItem::separator(app)?),
    ];
    match summary {
        Some(s) => {
            items.push(Box::new(MenuItem::with_id(app, "state", state_text(s), false, None::<&str>)?));
            for (i, a) in s["attention"].as_array().into_iter().flatten().take(5).enumerate() {
                let title = a["title"].as_str().unwrap_or("");
                items.push(Box::new(MenuItem::with_id(app, format!("att:{i}"), format!("  {title}"), true, None::<&str>)?));
            }
            let sessions: Vec<&Value> = s["sessions"].as_array().into_iter().flatten().collect();
            if !sessions.is_empty() {
                items.push(Box::new(PredefinedMenuItem::separator(app)?));
                for sess in sessions.iter().take(6) {
                    let name = sess["name"].as_str().unwrap_or("");
                    let label = if !sess["alive"].as_bool().unwrap_or(false) {
                        format!("{name}  ·  exited")
                    } else {
                        match sess["idle_minutes"].as_i64() {
                            Some(m) if m >= 10 => format!("{name}  ·  idle {m}m"),
                            _ => format!("{name}  ·  running"),
                        }
                    };
                    items.push(Box::new(MenuItem::with_id(app, format!("ses:{name}"), label, true, None::<&str>)?));
                }
            }
            let today = money(&s["spend"]["today"]);
            let change = s["spend"]["change_vs_prev_7_pct"].as_f64()
                .map(|c| format!(" · {}{:.0}% vs last week", if c >= 0.0 { "+" } else { "−" }, c.abs()))
                .unwrap_or_default();
            items.push(Box::new(MenuItem::with_id(app, "spend", format!("Today {today}{change}"), false, None::<&str>)?));
        }
        None => items.push(Box::new(MenuItem::with_id(app, "state", "Eyrie isn't answering", false, None::<&str>)?)),
    }
    let autostart = app.autolaunch().is_enabled().unwrap_or(false);
    items.push(Box::new(PredefinedMenuItem::separator(app)?));
    items.push(Box::new(MenuItem::with_id(app, "open", "Open Eyrie", true, None::<&str>)?));
    items.push(Box::new(CheckMenuItem::with_id(app, "autostart", "Start at login", true, autostart, None::<&str>)?));
    if cfg!(target_os = "macos") {
        let show_cost = app.state::<AppState>().settings.lock().unwrap().show_cost;
        items.push(Box::new(CheckMenuItem::with_id(app, "cost", "Show today's cost in the menu bar", true, show_cost, None::<&str>)?));
    }
    items.push(Box::new(PredefinedMenuItem::separator(app)?));
    items.push(Box::new(MenuItem::with_id(app, "quit", "Quit widget", true, None::<&str>)?));
    let refs: Vec<&dyn IsMenuItem<R>> = items.iter().map(|b| b.as_ref()).collect();
    Menu::with_items(app, &refs)
}

/// Push a fresh summary to the icon, title, menu and panel.
fn apply_summary<R: Runtime>(app: &AppHandle<R>, summary: &Value) {
    *app.state::<AppState>().last.lock().unwrap() = Some(summary.clone());
    let state = summary["state"].as_str().unwrap_or("ok").to_string();
    let show_cost = app.state::<AppState>().settings.lock().unwrap().show_cost;
    let title = show_cost.then(|| money(&summary["spend"]["today"]));
    let tooltip = format!("Eyrie · {}", state_text(summary));
    let s = summary.clone();
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(tray) = handle.tray_by_id(TRAY_ID) {
            let _ = tray.set_icon(Some(tray_image(&state)));
            let _ = tray.set_icon_as_template(true);
            let _ = tray.set_tooltip(Some(&tooltip));
            #[cfg(target_os = "macos")]
            let _ = tray.set_title(title.as_deref());
            #[cfg(not(target_os = "macos"))]
            let _ = &title;
            if let Ok(menu) = build_menu(&handle, Some(&s)) {
                let _ = tray.set_menu(Some(menu));
            }
        }
    });
    let _ = app.emit_to(PANEL, "summary", summary);
}

fn apply_unreachable<R: Runtime>(app: &AppHandle<R>, error: &str) {
    *app.state::<AppState>().last.lock().unwrap() = None;
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(tray) = handle.tray_by_id(TRAY_ID) {
            let _ = tray.set_icon(Some(tray_image("problem")));
            let _ = tray.set_icon_as_template(true);
            let _ = tray.set_tooltip(Some("Eyrie isn't answering"));
            #[cfg(target_os = "macos")]
            let _ = tray.set_title(None::<&str>);
            if let Ok(menu) = build_menu(&handle, None) {
                let _ = tray.set_menu(Some(menu));
            }
        }
    });
    let _ = app.emit_to(PANEL, "unreachable", error);
}

fn panel<R: Runtime>(app: &AppHandle<R>) -> Option<WebviewWindow<R>> {
    app.get_webview_window(PANEL)
}

fn hide_panel<R: Runtime>(app: &AppHandle<R>) {
    if let Some(w) = panel(app) {
        let _ = w.hide();
    }
}

/// Show the panel under the tray icon (macOS) or at the top right of the screen (Linux,
/// where the indicator gives us no position).
fn show_panel<R: Runtime>(app: &AppHandle<R>, anchor: Option<Rect>) {
    let Some(w) = panel(app) else { return };
    let monitor = w.current_monitor().ok().flatten().or_else(|| w.primary_monitor().ok().flatten());
    if let (Some(m), Ok(size)) = (monitor, w.outer_size()) {
        let scale = m.scale_factor();
        let (mx, my) = (m.position().x as f64, m.position().y as f64);
        let (mw, mh) = (m.size().width as f64, m.size().height as f64);
        let (ww, wh) = (size.width as f64, size.height as f64);
        let margin = 8.0 * scale;
        let (x, y) = match anchor {
            Some(rect) => {
                let p = rect.position.to_physical::<f64>(scale);
                let s = rect.size.to_physical::<f64>(scale);
                let below = p.y < my + mh / 2.0; // menu bar at the top, taskbar maybe at the bottom
                let y = if below { p.y + s.height + 4.0 * scale } else { p.y - wh - 4.0 * scale };
                (p.x + s.width / 2.0 - ww / 2.0, y)
            }
            None => (mx + mw - ww - margin, my + 36.0 * scale),
        };
        let x = x.clamp(mx + margin, mx + mw - ww - margin);
        let y = y.clamp(my, my + mh - wh);
        let _ = w.set_position(Position::Physical(PhysicalPosition::new(x as i32, y as i32)));
    }
    let _ = w.show();
    let _ = w.set_focus();
    if let Some(v) = app.state::<AppState>().last.lock().unwrap().clone() {
        let _ = app.emit_to(PANEL, "summary", &v);
    }
}

fn toggle_panel<R: Runtime>(app: &AppHandle<R>, anchor: Option<Rect>) {
    match panel(app).map(|w| w.is_visible().unwrap_or(false)) {
        Some(true) => hide_panel(app),
        _ => show_panel(app, anchor),
    }
}

fn on_menu<R: Runtime>(app: &AppHandle<R>, id: &str) {
    let open = |path: &str| {
        let _ = app.opener().open_url(format!("{}{}", base_url(), path), None::<&str>);
    };
    match id {
        "show" => show_panel(app, None),
        "open" => open("/"),
        "quit" => app.exit(0),
        "autostart" => {
            let al = app.autolaunch();
            let _ = if al.is_enabled().unwrap_or(false) { al.disable() } else { al.enable() };
        }
        "cost" => {
            let state = app.state::<AppState>();
            let s = {
                let mut s = state.settings.lock().unwrap();
                s.show_cost = !s.show_cost;
                s.clone()
            };
            save_settings(app, &s);
            let last = state.last.lock().unwrap().clone();
            if let Some(v) = last {
                apply_summary(app, &v);
            }
        }
        other => {
            let last = app.state::<AppState>().last.lock().unwrap().clone();
            if let Some(name) = other.strip_prefix("ses:") {
                open(&format!("/sessions?open={name}"));
            } else if let (Some(i), Some(s)) = (other.strip_prefix("att:"), last) {
                let href = i.parse::<usize>().ok().and_then(|i| s["attention"][i]["href"].as_str().map(String::from));
                open(&href.unwrap_or_else(|| "/".into()));
            }
        }
    }
}

fn start_polling<R: Runtime>(app: AppHandle<R>) {
    thread::spawn(move || loop {
        match get("/api/v1/summary") {
            Ok(v) => apply_summary(&app, &v),
            Err(e) => apply_unreachable(&app, &e),
        }
        thread::sleep(POLL);
    });
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .invoke_handler(tauri::generate_handler![
            summary, refresh, action, add_task, open_eyrie, get_settings, set_show_cost, set_autostart,
            start_eyrie, hide, quit
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            // A menu-bar app: no Dock icon, no app switcher entry.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let mut settings = load_settings(&handle);
            if !settings.autostart_initialised {
                let _ = handle.autolaunch().enable();
                settings.autostart_initialised = true;
                save_settings(&handle, &settings);
            }
            app.manage(AppState { settings: Mutex::new(settings), last: Mutex::new(None) });

            TrayIconBuilder::with_id(TRAY_ID)
                .icon(tray_image("ok"))
                .icon_as_template(true)
                .tooltip("Eyrie")
                .menu(&build_menu(&handle, None)?)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| on_menu(app, event.id().as_ref()))
                .on_tray_icon_event(|tray, event| {
                    // macOS / Windows: left click toggles the panel under the icon. (Linux sends
                    // no click events; there the menu's "Show panel" opens it.)
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, rect, .. } = event {
                        toggle_panel(tray.app_handle(), Some(rect));
                    }
                })
                .build(app)?;

            if let Some(w) = panel(&handle) {
                let h = handle.clone();
                w.on_window_event(move |e| {
                    if let WindowEvent::Focused(false) = e {
                        hide_panel(&h);
                    }
                });
            }
            start_polling(handle);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Eyrie's widget");
}
