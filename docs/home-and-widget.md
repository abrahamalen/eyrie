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
sessions[]       Eyrie's sessions, then ones in your own terminals: name, tool, project, alive, idle_for,
                 last_output, managed, tty, pid
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

**Sessions in your own terminals.** Most sessions aren't started from Eyrie, so the summary also lists interactive `claude` / `codex` processes it finds with `ps` (those with a terminal; daemons, background helpers, `app-server` and MCP children are skipped). Eyrie's own tmux panes are excluded by pid. From each command line Eyrie keeps only the tool and a `--resume` target, never prompt text. The working directory comes from `lsof` (macOS) or `/proc` (Linux). Last activity is the transcript's mtime when the session was resumed by id, and otherwise the newest conversation in that directory (marked approximate). Codex activity is the newest thread for that directory. They're read-only in Eyrie: no attach, no stop, and no idle attention, since leaving a terminal session parked is normal.

**Cost** comes from the usage index (today and the last 7 days), never from `lastCost`. That fixes H2.

**Cost of a poll** (measured on real data): about 60 ms warm. It was about 200 ms until the MCP source stopped re-reading its 15 newest transcripts on every call; it now caches each transcript's failures by modified time and size, so only the active transcript is re-read (this closes P5 from `architecture.md`). Tool versions are cached until the binary changes. Cheap enough to poll every 10 s from both views.

## 3. Visual direction and the new home page

*Revised after review: the home page should explain Eyrie, and the whole UI needs a stronger look. The reference is the Nexus site, <https://nexus-ai.aayushostwal.com> (source `aayushostwal/nexus`, `apps/nexus-web`).*

### 3.1 Design language (app-wide)

Eyrie manages Nexus agents' memory, so the two should read as siblings. Eyrie takes Nexus's design language, with its own accent so the two stay distinguishable.

| Element | Nexus (reference) | Eyrie |
|---|---|---|
| Ground and ink | Warm paper `hsl(40 25% 97%)`, navy ink `hsl(222 30% 14%)`, warm hairlines `hsl(35 15% 85%)`. Dark: navy `hsl(222 28% 9%)` | Same |
| Accent | Rust `hsl(18 84% 38%)`, used sparingly: eyebrow dot, one emphasised word, small labels | **Sky teal**, Eyrie's own (an eyrie sits high up), a token. The prototype can switch to rust for comparison |
| Type | Geist, a tight bold display; one italic serif phrase in the hero | Geist and Geist Mono (already in the app), plus **Instrument Serif** italic for the one emphasised phrase, bundled locally so it works offline and on Ubuntu |
| Labels | Mono uppercase, letter-spaced eyebrows ("01 / A COMPLETE WORKFLOW") | Same, numbered only where it's a real sequence |
| Surfaces | White cards with hairline borders on paper, lots of whitespace, warm-tinted command boxes with Copy | Same. Command previews (which Eyrie already shows before every change) get the warm box |
| Chrome | Top header: logo tile, a mono product subtitle, nav, ⌘K search, theme, GitHub | Header with logo tile `e.`, mono "AGENT CONTROL PLANE", a live status pill, theme. The left sidebar stays (ten pages), restyled with mono group labels |
| Page headers | Eyebrow + tight title + one-line description | Every page gets the same, e.g. `SESSIONS`, "Sessions", one line on what it is |

Data colours stay as they are. The chart palette is the validated categorical one, and status colours keep their meaning.

### 3.2 Two pages: a public landing page and the in-app home

"Explaining Eyrie" and "what's going on right now" are different jobs for different places.

**Landing page**: public, at **<https://alenabraham.me/eyrie>**.

- **Where it lives**: in the site repo (`alen-abraham.github.io`, Hugo + PaperMod, deployed from its `hugo` branch). It's a standalone static page under `static/eyrie/`, so it can use Eyrie's design language without fighting the blog theme, and it ships as its own PR in that repo.
- **No live data**: a public page can't, and shouldn't, reach a local Eyrie. Eyrie's Origin check would refuse it anyway.
- **Sections**, Nexus-style:
  1. **Hero**:
     - Eyebrow: `LOCAL · ON YOUR MACHINE ONLY`.
     - Headline: "Every coding agent on your machine, *in one place.*"
     - One paragraph on what Eyrie is.
     - CTAs: **Install** and **See how it works ↓**.
     - Mono footnote: `127.0.0.1 only · no accounts · open source`.
     - Side card: **THE DEAL**. Eyrie reads your tools' own files, changes things only through their own CLIs, shows you the command first, and logs every change.
  2. **Stat strip**: the Claude Code and Codex it manages, MCP scopes, pages, and `v0.1.0`.
  3. **01 / What it does**: a card for each area: Sessions, Usage, MCP servers, Plugins, Nexus memory, Tasks, Activity. Each has one sentence, the real command it runs with Copy, and a screenshot.
  4. **02 / How it works**: a timeline:
     1. reads your tools' files;
     2. changes go through their CLIs;
     3. sessions run in Eyrie's own tmux;
     4. everything is logged.
  5. **03 / Safe by design**: localhost only, the token, no shell and no "run anything" endpoint, etag checks, the audit log, and anti-framing headers.
  6. **04 / Install**: the macOS `.dmg` and Ubuntu `.deb` once packaging ships; until then, from source with `make install`. Plus the top-bar widget.

**In-app home**: the Overview at `127.0.0.1:8787/`.

- **Content**: the live "what's going on" page, in the new design language: needs attention, sessions (with start-in-a-recent-project), spend, tasks and tool health. It fixes H1–H6.
- **Page header**: like every page, an eyebrow, a title and one line, plus a **What is Eyrie? ↗** link to the landing page instead of a hero.

## 4. The widget

**Built** (`widget/`, Tauri 2.12.1). What the build found:

- **Mark**: the app's logo, "e." in Geist Bold, so the tray, app icon, favicon and sidebar all match. Earlier marks failed at 22 px: a nest read as a smiley face, then a peak with a bird read as macOS's photo glyph. State lives in the dot: `e.` fine, `e●` (big raised dot) needs you, `e!` problem. `widget/make_icons.py` draws the three tray states and the app icon; `npx tauri icon` derives the bundle sizes.
- **Release**: `Eyrie.app` (ad-hoc signed, `LSUIElement` so there's no Dock icon at launch) and `Eyrie_0.1.0_aarch64.dmg`, 3.1 MB.
- **DMG layout**: `bundle_dmg.sh` drives Finder with AppleScript to lay out the DMG window, which needs automation permission. Builds run it with `CI=true`, which skips that step.
- **Linux**: builds and bundles in an Ubuntu 24.04 container as `Eyrie_0.1.0_arm64.deb` (3.7 MB). It depends on `libayatana-appindicator3-1`, `libwebkit2gtk-4.1-0` and `libgtk-3-0`. amd64 builds come from release CI.
- **Testing**: the panel is a second Vite entry. A dev-only bridge fallback lets it be checked in a browser; production builds don't include it.

A tray app: a menu-bar icon on macOS, an indicator in the Ubuntu top bar.

### 4.1 Icon

- Monochrome, with three states driven by `summary.state`:
  - **ok**: plain icon;
  - **attention**: a dot;
  - **problem**: a warning mark.
- On macOS it's a template image, so it follows light and dark menu bars.
- Optionally, the menu-bar title can show today's cost (`$8.42`). This is macOS only; the Ubuntu indicator has no title.

### 4.2 Popover (368 × 560, anchored top right)

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
| Menu contents | Same on both: Show panel; state and up to 5 attention items; up to 8 sessions (Eyrie's open their terminal, ones in your own terminals open Sessions); today's spend; Open Eyrie; Start at login; Show cost in menu bar (macOS); Quit | (same) |
| Title text | Today's cost (optional) | n/a |

The Ubuntu menu repeats the key facts, so you can glance at it without opening the panel.

### 4.4 Talking to Eyrie

- The popover never calls the API from the webview.
  - Its origin (`tauri://localhost` or `http://tauri.localhost`) would fail Eyrie's Origin check, which is on purpose.
  - It would also need the token in JavaScript.
- Instead, **Rust commands proxy** to `http://127.0.0.1:<port>`:
  - `summary`, `refresh`, `action` (id, params, dry_run), `add_task`
  - `open_eyrie` (a `/…` path in the browser), `start_eyrie` (kickstarts the service)
  - `get_settings`, `set_show_cost`, `set_autostart`, `hide`, `quit`
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
| PATH for the service | Neither launchd nor systemd user units see your shell's PATH, so `claude`, `codex` and `tmux` wouldn't be found. At service install, Eyrie runs your login shell **from a clean environment** (`env -i HOME USER SHELL TERM $SHELL -lic …`, reading the value between markers so shell noise doesn't matter) and writes the result into the unit. A clean environment matters: a login shell otherwise inherits the caller's PATH, including session-specific entries |
| Not bundled | `tmux`, `claude`, `codex`. These are your tools, and Eyrie manages them rather than shipping them. Missing ones show up as `cli_missing` attention items, with how to install |
| Data | Unchanged: `~/.eyrie` (token, usage DB, audit log, tmux.conf) and your `eyrie.toml`. Install, upgrade and uninstall never delete it |
| Upgrade | Install the new package; the widget restarts the service if `eyrie-server`'s version changed |
| Uninstall | The widget's **Quit and remove service** (and the `.deb`'s `prerm`) unload the service. Sessions keep running |
| CI | A release workflow (tag `v*`) builds `.dmg`, `.deb`, `.rpm`, AppImage and the Windows installer (see §5.1). It's skipped on the `alenabraham-qure` fork, like `ci.yml` |
| Dev install | `make install` stays for running from a checkout. It also gains Ubuntu support (a systemd user unit), so dev and packaged installs behave the same |

### 5.1 Platforms

Target list: **macOS, Ubuntu, Fedora, other Linux, Windows**. What changes per platform:

| Platform | Package | Background service | Widget (tray) | Sessions (tmux) | Status |
|---|---|---|---|---|---|
| **macOS** 13+ (Apple Silicon and Intel) | `.dmg` (`Eyrie.app`) | launchd agent | Menu bar: click → panel, right-click → menu | tmux (Homebrew) | Service built; app and widget next |
| **Ubuntu** 24.04 / Debian | `.deb` | systemd user unit | GNOME top bar via AppIndicator (enabled by default on Ubuntu); click → menu with "Show panel" | tmux (apt) | Service built; suite passes on 24.04 |
| **Fedora** 40+ | `.rpm` (Tauri bundles it) | systemd user unit (same unit as Ubuntu) | **Fedora's GNOME has no tray by default.** It needs the *AppIndicator and KStatusNotifierItem Support* extension; KDE works as is. Without a tray, the widget opens as a small window from the app launcher and the first run says how to enable the extension | tmux (dnf) | To verify in a `fedora` container (suite + `systemd-analyze`) |
| **Other Linux** | AppImage | systemd user unit, if present; otherwise `make serve` / autostart | AppIndicator / StatusNotifier, depending on the desktop | tmux | An AppImage moves on disk, so on first run the server binary is copied to `~/.local/lib/eyrie/` and the unit points there |
| **Windows** 10/11 | `.msi` / NSIS installer | Per-user scheduled task at logon | System tray: click → panel (Windows has real click events) | **Native session layer** (no tmux). See below | **Deferred**: native, after the others are stable |

**Windows.** The Eyrie backend is portable, but two parts aren't:

1. **The session manager is built on tmux.** There's no native tmux on Windows.
2. **The browser terminal uses Unix ptys** (`pty`, `fcntl`, `termios`, signals in `sessions/terminal.py`).

Smaller gaps: the token file's mode 600 needs a Windows ACL instead; service install would use a per-user scheduled task at logon (there's no launchd or systemd); and path and CLI resolution need `.exe`/`.cmd` handling.

**Decision (2026-10-18): native Windows (option B), deferred.** It starts only once macOS, Ubuntu, Fedora and other Linux are stable and working, and its scope will be shaped by feedback from those users. Until then, nothing Windows-specific is built, and the code just keeps Unix-only pieces confined (today they're all in `sessions/terminal.py` and tmux) so a second session layer can slot in behind an interface later. The options considered:

- **A. Through WSL2 (recommended first).**
  - Eyrie's backend and tmux run inside WSL2 (Ubuntu), exactly as on Linux, with a systemd user unit; WSL supports systemd.
  - The **widget runs natively on Windows** and talks to `127.0.0.1:8787`, which WSL forwards to Windows by default.
  - You get everything, including sessions, for little new code. The cost: it manages the Claude Code and Codex installed *inside WSL*, not native Windows installs.
- **B. Native Windows.**
  - Replace tmux with an Eyrie-owned session supervisor: a small background process that keeps each session in a ConPTY (via `pywinpty`) and outlives the API server.
  - Replace the pty bridge with a ConPTY bridge, and read Windows-native Claude Code and Codex state.
  - That's a real second implementation of the session layer behind an interface, and the most work of anything on this list.

**CI.** The release workflow builds and tests on `macos-14`, `ubuntu-24.04` and a `fedora:41` container. `windows-latest` joins when native Windows work starts.

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
2. **Prototype**, in the new design language: the public landing page, the in-app home, one restyled inner page (Sessions), and the widget popover in its macOS and Ubuntu variants.
3. **Code**:
   1. **UI refresh** (§3.1): tokens, type (incl. bundled Instrument Serif), header and sidebar, page headers, cards, buttons, command boxes, applied to every page
   2. `GET /api/v1/summary` and the new in-app home (§3.2, fixes H1–H6)
   3. **Landing page** at alenabraham.me/eyrie: a PR in `alen-abraham.github.io` (`static/eyrie/`)
   4. Ubuntu support for running Eyrie as a service: a systemd user unit and a cross-platform `make install`
   5. The widget in dev mode (`npm run tauri dev`) against an installed Eyrie: tray, popover, Rust proxy, autostart
   6. Packaging: the PyInstaller sidecar, bundling, first-run service install, and a release CI building `.dmg` and `.deb`

## 9. Decisions on the open questions

Defaults taken when the design merged without answers; each is cheap to change.

| Question | Default |
|----------|---------|
| macOS signing | **Ad-hoc**, for personal use. The first launch needs right-click → Open. Developer ID signing and notarization can be added later in release CI |
| Ubuntu target | **24.04 LTS, default GNOME** (AppIndicator extension enabled by default) |
| Cost in the macOS menu bar | **Shown** next to the icon (`$8.42`), with a widget setting to switch to icon only |
