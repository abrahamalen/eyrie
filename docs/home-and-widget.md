# Home page, top-bar widget, and packaging (design draft)

Status: **draft, under review**. Design only. A prototype PR follows, then code in slices.

## 1. Context

The revamp in `architecture.md` shipped, but two things are missing:

- **The home page was never rebuilt.** It is still v0 (`frontend/src/pages/OverviewPage.tsx`):

  | # | Problem |
  |---|---------|
  | H1 | A marketing hero ("Your agents, at a glance") takes the top quarter of the screen and tells you nothing |
  | H2 | The headline "$146.25" sums each project's *last session*, even though the Usage index now has real daily history |
  | H3 | "6 MCP servers failing" sits next to "5 ok". The failures include plugin and hidden servers, and no names are shown |
  | H4 | Sessions, the thing Eyrie now controls, don't appear at all |
  | H5 | A fake terminal shows one Codex prompt. It's decoration, and it puts work content on the home page |
  | H6 | "1 Nexus agent" and "0 open tasks" get the same weight as everything else, and there are no actions |

- **There's no glanceable view.** You have to open a browser tab to know whether a session needs you or what today cost.

Decisions so far:

| Question | Decision |
|----------|----------|
| What the widget shows | Live sessions, today's cost, needs attention, quick actions |
| Widget technology | **Tauri v2** tray app: one codebase, with the popover reusing the React UI |
| Packaging | **Widget and Eyrie together**: one installer per OS, Mac and Ubuntu first |

## 2. One summary, two views

The home page and the widget answer the same question: "what needs me, and what's going on?" So both read one endpoint, and the two can never disagree.

`GET /api/v1/summary`, built from existing sources:

```
state            "ok" | "attention" | "problem"   (drives the tray icon)
attention[]      { kind, severity, title, detail, href, since }   most severe first
sessions[]       live Eyrie sessions: name, tool, project, alive, idle_for, last_output
spend            today, yesterday, last_7_days[] (daily), change_vs_prev_7_pct, top_project_today
tasks            open_count, next[3]
recent_projects  [{ path, last_used, tool }]   for one-click "new session here"
health           { tmux, claude, codex, usage_index }   is each tool found and working?
```

**What counts as "needs attention"**, most severe first:

| Kind | When | Severity |
|------|------|----------|
| `cli_missing` | `tmux`, `claude` or `codex` isn't found, so sessions or actions can't work | problem |
| `session_exited_error` | An Eyrie session exited with a non-zero code | problem |
| `mcp_failed` | A *configured, not hidden* MCP server's last connect failed. The server is named, with when it was last seen | attention |
| `session_idle` | A live session has printed nothing for 10+ minutes. Most likely it's waiting for you | attention |
| `unpriced_model` | Usage contains a model with no price, so cost reads low | attention |

**Waiting for input.** A session that's idle (no output for 10 min, configurable) is the honest signal Eyrie has. Detecting Claude's "waiting for input" prompt would mean scraping its TUI, and that would break whenever the TUI changes. Not doing that.

**Cost** comes from the usage index (today and the last 7 days), never from `lastCost`. That fixes H2.

**Snapshot cost**: the slowest input is the transcript scan, which takes about 6 ms warm. The summary is cheap enough to poll every 10 s from both views.

## 3. New home page

Ordered by what you act on first. No hero (H1).

```
┌ Overview ───────────────────────────────────────────── Sat 17 Oct ┐
│ NEEDS ATTENTION (2)                                                │
│ ● eyrie-7f3a has been idle 14 min · Claude Code · ~/…/eyrie  [Open]│
│ ● MCP context7 failed to connect · 2 h ago               [MCP page]│
├──────────────────────────────┬─────────────────────────────────────┤
│ SESSIONS (2 live)  [+ New]   │ SPEND                               │
│ eyrie-7f3a  Claude · eyrie   │ $8.42 today     ▁▃▂▅▇▆█ last 7 days │
│   running · 2 min ago [Open] │ +12% vs previous 7 days             │
│ eyrie-2c91  Codex · dotfiles │ Top today: ~/personal/projects/eyrie│
│   idle 14 min         [Open] │                           [Usage →] │
│ Start in: eyrie · blog · …   │                                     │
├──────────────────────────────┼─────────────────────────────────────┤
│ TASKS (3 open)               │ TOOLS                               │
│ ☐ Renew passport             │ tmux 3.6 ✓  claude 2.1 ✓  codex ✓   │
│ ☐ Back up Postgres  [+ add]  │ 4 MCP servers · 3 plugins on        │
└──────────────────────────────┴─────────────────────────────────────┘
```

- **Needs attention** (H3, H4): each row names the thing and links to where you fix it. When the list is empty: "Nothing needs you right now".
- **Sessions**: live sessions with Open, which goes to `/sessions?open=<name>`. Recent projects appear as chips that start a session in one click, through the same confirm-and-preview action as the Sessions page.
- **Spend**: today, a 7-day sparkline, the change against the previous 7 days, and the top project today.
- **Tasks**: the next three open tasks, which you can tick off inline, plus an inline add.
- **Tools**: a one-line health check, replacing the equal-weight tiles (H6).
- **Removed**: the hero (H1) and the fake terminal (H5).

## 4. The widget

A tray app: a menu-bar icon on macOS, an indicator in the Ubuntu top bar.

### 4.1 Icon

- Monochrome, with three states driven by `summary.state`:
  - **ok**: plain icon;
  - **attention**: a dot;
  - **problem**: a warning mark.
- On macOS it's a template image, so it follows light and dark menu bars.
- Optionally, the menu-bar title can show today's cost (`$8.42`). This is macOS only; the Ubuntu indicator has no title.

### 4.2 Popover (about 360 × 520, anchored top right)

```
┌───────────────────────────────┐
│ Eyrie            ● 2 need you │
│ ● eyrie-7f3a idle 14 min [Open]│
│ ● context7 failed        [Fix] │
│ SESSIONS                      │
│ eyrie-7f3a  Claude  running   │
│ eyrie-2c91  Codex   idle      │
│ TODAY  $8.42  ▁▃▂▅▇▆█  +12%   │
│ [+ Session in…] [+ Task]      │
│ [Open Eyrie]          [Quit]  │
└───────────────────────────────┘
```

- A frameless window that hides when it loses focus.
- It's a second Vite entry (`widget.html`) in the same frontend, reusing its components and generated types.
- **Open** opens Eyrie in your default browser at that session's terminal.
- **+ Session in…** lists your recent projects and starts the session through Eyrie's action API.

### 4.3 Platform differences

These come from Tauri v2's tray behaviour.

| | macOS | Ubuntu (GNOME + AppIndicator) |
|---|---|---|
| Left-click on icon | Toggles the popover, positioned under the icon | **Not supported**: AppIndicator only shows a menu. The menu's first item is **Show panel**, which opens the popover at the top-right of the primary screen |
| Menu | Right-click | Click (the only interaction) |
| Menu contents | Show panel, Open Eyrie, Quit | Show panel; the attention count; live sessions (each opens in Eyrie); Open Eyrie; Quit |
| Title text | Today's cost (optional) | n/a |

The Ubuntu menu repeats the key facts, so you can glance at it without opening the panel.

### 4.4 Talking to Eyrie

- The popover never calls the API from the webview.
  - Its origin (`tauri://localhost` or `http://tauri.localhost`) would fail Eyrie's Origin check, which is on purpose.
  - It would also need the token in JavaScript.
- Instead, **Rust commands proxy** to `http://127.0.0.1:<port>`:
  - `summary()`
  - `run_action(id, params, dry_run)`
  - `open_in_browser(path)`
- They read `~/.eyrie/token` (mode 600, same user). The webview calls them with `invoke()`.
- The Tauri capability allowlist exposes only those commands: no shell, no filesystem, no arbitrary HTTP from the webview.
- If Eyrie isn't answering, the popover says so and offers **Start Eyrie**, which (re)loads the service.

### 4.5 Autostart

The widget starts at login, through Tauri's autostart plugin (a LaunchAgent on macOS, `~/.config/autostart/*.desktop` on Ubuntu). It's separate from the backend service, so quitting the widget never stops Eyrie or its sessions.

## 5. Packaging: Eyrie and the widget together

One installer per OS. It contains the widget, the Eyrie backend as a self-contained binary, and the built web UI.

| Piece | How |
|-------|-----|
| Backend binary | **PyInstaller** onefile build of `app.main` → `eyrie-server`, built per OS (it can't cross-compile). Shipped as a Tauri sidecar (`externalBin`, which takes a single executable), so no Python is needed on the target. Onefile adds about a second to start-up, which is fine for a service |
| Web UI | `frontend/dist`, bundled as a Tauri resource; the backend's `server.ui_dir` points at it |
| macOS | `Eyrie.app` in a `.dmg`. The first launch installs the backend as LaunchAgent `local.eyrie`, pointing at the `eyrie-server` inside the app, using the same settings as `scripts/launchd.py` (`AbandonProcessGroup`, KeepAlive, 127.0.0.1:8787) |
| Ubuntu | A `.deb` (fixed paths under `/usr/lib/eyrie`, which a service needs). The first launch installs a **systemd user unit** `eyrie.service` (`systemctl --user enable --now`) with `KillMode=process`, systemd's equivalent of `AbandonProcessGroup`, so tmux sessions survive restarts. AppImage is deferred: it moves on disk, which breaks a service path |
| PATH for the service | Neither launchd nor systemd user units see your shell's PATH, so `claude`, `codex` and `tmux` wouldn't be found. At service install, Eyrie asks your login shell (`$SHELL -lic 'echo $PATH'`) and writes the result into the unit |
| Not bundled | `tmux`, `claude`, `codex`. These are your tools, and Eyrie manages them rather than shipping them. Missing ones show up as `cli_missing` attention items, with how to install |
| Data | Unchanged: `~/.eyrie` (token, usage DB, audit log, tmux.conf) and your `eyrie.toml`. Install, upgrade and uninstall never delete it |
| Upgrade | Install the new package; the widget restarts the service if `eyrie-server`'s version changed |
| Uninstall | The widget's **Quit and remove service** (and the `.deb`'s `prerm`) unload the service. Sessions keep running |
| CI | A release workflow (tag `v*`) with a matrix of `macos-14` and `ubuntu-24.04` builds the `.dmg` and `.deb` as artifacts. It's skipped on the `alenabraham-qure` fork, like `ci.yml` |
| Dev install | `make install` stays for running from a checkout. It also gains Ubuntu support (a systemd user unit), so dev and packaged installs behave the same |

## 6. Repo layout

```
widget/              Tauri app
  src-tauri/         Rust: tray, popover window, API proxy commands, service install
  tauri.conf.json    bundles eyrie-server (sidecar) + frontend/dist (resource)
frontend/
  widget.html        second Vite entry → src/widget/ (reuses components + generated types)
packaging/
  eyrie-server.spec  PyInstaller
  eyrie.service.in   systemd user unit template
scripts/
  launchd.py         + systemd.py (shared service logic)
```

## 7. Security

The widget doesn't change Eyrie's model; it's one more local client.

- The backend still listens on `127.0.0.1` only, and keeps its Host and Origin checks and its token.
- The widget's webview can only call the declared Rust commands, and those only talk to `127.0.0.1`.
- The token stays in Rust, never in JavaScript. Actions go through the same action layer, so they're previewed, confirmed where destructive, and audited.
- Service install writes only the user's own LaunchAgent or systemd user unit; no root is needed. The `.deb` itself installs as root, as any `.deb` does.

## 8. Delivery plan

Each step is its own PR.

1. **Design**: this document.
2. **Prototype**: a clickable mock of the new home page, plus the widget popover in its macOS and Ubuntu variants.
3. **Code**:
   1. `GET /api/v1/summary` and the new home page (fixes H1–H6)
   2. Ubuntu support for running Eyrie as a service: a systemd user unit and a cross-platform `make install`
   3. The widget in dev mode (`npm run tauri dev`) against an installed Eyrie: tray, popover, Rust proxy, autostart
   4. Packaging: the PyInstaller sidecar, bundling, first-run service install, and a release CI building `.dmg` and `.deb`

## 9. Decisions on the open questions

Defaults taken when the design merged without answers; each is cheap to change.

| Question | Default |
|----------|---------|
| macOS signing | **Ad-hoc**, for personal use. The first launch needs right-click → Open. Developer ID signing and notarization can be added later in release CI |
| Ubuntu target | **24.04 LTS, default GNOME** (AppIndicator extension enabled by default) |
| Cost in the macOS menu bar | **Shown** next to the icon (`$8.42`), with a widget setting to switch to icon only |
