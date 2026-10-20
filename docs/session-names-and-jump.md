# Session names, widget deep links, and jump to terminal (design)

Status: design, 2026-10-20. Prototype and code follow as separate PRs.

## 1. Context

Sessions are listed by things nobody remembers:

| # | Problem |
|---|---------|
| N1 | Eyrie sessions show `eyrie-7f3a`; external ones show `claude · ttys004`. The name you gave with Claude Code's `/rename` (or the tool's own title) is nowhere |
| N2 | In the widget, an external session is a tty you can't click. The tray menu's `ext:` item opens `/sessions` without saying which one |
| N3 | From the app there's no way to get back to the terminal a session is running in. You hunt through windows and tabs for `ttys004` |
| N4 | When a session has ended there is no next step; for an exited Eyrie session you have to rebuild the resume command yourself |

Goals:
1. Show each session's **name**, falling back to a short id, in the Sessions page, the home page, the widget panel and the tray menu.
2. Clicking a session in the widget opens the app **on that session**, for Eyrie and external sessions alike. `?open=<eyrie-name>` keeps working.
3. From the app, **jump** to where the session runs: Eyrie's in-app terminal or your terminal app for Eyrie sessions; the right terminal tab for external ones, where the terminal allows it.
4. When it can't, say so plainly and give the next step (where it runs, or the exact resume command).

Non-goals: renaming sessions from Eyrie (that would mean writing the tools' files), reading prompt text, Windows.

## 2. Flow

![Widget click → app deep link → focus terminal or a message](diagrams/session-jump.svg)

Source: [`diagrams/session-jump.workflow.json`](diagrams/session-jump.workflow.json) (Archify workflow; re-render with `archify deliver workflow … --quality showcase` and export SVG from the viewer).

## 3. Where names come from

Each adapter gets one new capability, `SessionCaps.names(settings) → lookup(pid, cwd, conversation_id, resume, started) → Name`, built once per listing like `activity()`. `Name = (conversation_id | None, name | None, source, exact)`. Formats below were checked on a real machine (Claude Code 2.1.303, Codex CLI with `state_5.sqlite`); Gemini from its source, since it isn't installed here.

### 3.1 Claude Code

| Source | Evidence | Gives |
|---|---|---|
| `~/.claude/sessions/<pid>.json` | Written by every running `claude`: `{"pid": 76190, "sessionId": "6636c681-…", "cwd": "…", "name": "build-eyrie", "nameSource": "user", "kind": "interactive", …}`. `nameSource` seen: `user` (`/rename` or `--resume <name>`), `auto` (named by Claude), `derived` (e.g. `qureai-f6`), absent (name is the id's first 8 chars) | pid → conversation id **and** name, exact |
| `~/.claude/projects/<cwd-slug>/<id>.jsonl` | Metadata lines re-appended near the end after each turn: `{"type":"custom-title","customTitle":"build-eyrie","sessionId":"…"}`, `{"type":"agent-name","agentName":"build-eyrie",…}`, `{"type":"ai-title","aiTitle":"Repo run",…}`. On this machine the last one was always within 32 KB of the end, even in a 200 MB transcript | conversation id → name, when there's no pid file (older Claude, exited Eyrie session) |

Rules: the pid file wins when its `pid` matches and `kind` is `interactive`. `nameSource: user` → source `user`; `auto`/`derived` → source `tool`; a name equal to the id prefix counts as no name. Without a pid file, read the transcript's **last 256 KB** and take the last `custom-title` (`user`), else the last `ai-title` (`tool`). `--resume <name>` with no other match gives the name with no id.

### 3.2 Codex

| Source | Evidence | Gives |
|---|---|---|
| `~/.codex/session_index.jsonl` | Append-only, one line per change: `{"id":"01a13480-…","thread_name":"Understand repo for production","updated_at":"…"}`; last line per id wins | id → name (source `tool`: Codex doesn't record whether you or it named the thread) |
| `state_5.sqlite` `threads` (read-only, as today) | `id, cwd, created_at, updated_at, title` where `title` is the **first prompt** | id ↔ cwd; never shown as a name (it's prompt text) |

Codex writes no pid file and doesn't hold the rollout open, so a pid maps to a thread only by: the `resume <uuid>` argument (exact), Eyrie's `@eyrie_conv` (exact), else the newest thread in the same cwd updated since the process started (`exact: false`, shown with `~`). When two running sessions would get the same guess (several in one directory), neither does: they fall back to the label.

### 3.3 Gemini CLI

`~/.gemini/tmp/<project>/chats/session-<time>-<sid8>.jsonl`: the first line is metadata (`sessionId`, `startTime`, …); `{"$set": {"summary": "…"}}` updates add an AI summary (`chatRecordingService.saveSummary`). There is no user rename. Name = last `summary` (source `tool`); id from `--resume <uuid>` / `@eyrie_conv` (exact) or the newest chat file in the project since the process started (`exact: false`).

### 3.4 Fallback

| Have | Shown |
|---|---|
| name | the name (max 80 chars, control characters stripped) |
| id only | short id, mono: first 8 hex chars; for UUIDv7 ids (Codex, version nibble `7`) the **last** 8, because v7 prefixes are timestamps and collide between threads started close together |
| neither | Eyrie session: `eyrie-7f3a`; external: `Codex · ttys015` (today's label) |

The full id is always in the row's secondary line / tooltip. Names and ids are read-only data from the tools' own files; nothing is written.

## 4. Deep links

| Link | Meaning |
|---|---|
| `/sessions?open=eyrie-7f3a` | Unchanged: select that Eyrie session and open its in-app terminal |
| `/sessions?ext=<pid>&tool=<tool>&id=<conversation id>` | Select that external session; `tool` and `id` are only used if it's no longer running, to show the resume command |

The backend builds them: `SummarySession.href` and `ExternalSession.href`, so the panel, the tray menu and the home page all use the same link. The widget checks every path as today (`/`-relative, no `//`, no `..`) before opening `EYRIE_URL + path`. The page validates parameters before use (`pid` digits, `tool` a known id, `id` a UUID or a session name); anything else is ignored.

## 5. Jumping to the terminal

### 5.1 Eyrie sessions (tmux, `-L eyrie`)

- **Open** (exists): the in-app xterm (`SessionTerminal`).
- **Open in Terminal / iTerm** (new, macOS): action `sessions.open_terminal {name, app}` asks Terminal.app (`do script`) or iTerm2 (`create window …` + `write text`) to run `<tmux> -L eyrie attach -t <name>`. The command is built by Eyrie from a validated name and passed as an argv item.
- **Copy attach command** (exists) everywhere, including Linux.

### 5.2 External sessions

Find the terminal by walking the session's parent processes in the same `ps` snapshot (`ps -axo pid=,ppid=,tty=,etime=,command=`), stopping at the first known host:

| Host (how it's recognised) | macOS | Linux | How |
|---|---|---|---|
| Terminal.app (`…/Terminal.app/…`) | **tab** | — | AppleScript: find the tab whose `tty` is `/dev/<tty>`, select it, raise its window, activate |
| iTerm2 (`iTermServer-*`, `…/iTerm.app/…`) | **tab** | — | AppleScript: find the session whose `tty` matches, select window, tab and session, activate |
| tmux, your own server (`tmux` with optional `-L`/`-S`) | **pane** | **pane** | `tmux list-panes -a` to find the pane by tty, then `switch-client -t %N ; select-window -t %N ; select-pane -t %N`; on macOS also bring the client's terminal (Terminal/iTerm) forward |
| Ghostty, Warp, WezTerm, kitty, Alacritty, VS Code, Cursor | **app** | message | AppleScript `activate` on the app; Eyrie says which tab (`ttys015`) since it can't pick it |
| Anything else (GNOME Terminal, Konsole, xterm, ssh, unknown) | message | message | "Running in <host> on <tty>; switch to it" |

Why not more: Ghostty/Warp have no tab-scripting API; WezTerm (`wezterm cli activate-pane`) and kitty (`kitty @ focus-window`, needs `allow_remote_control`) can do it but need a second lookup command and per-user setup, so they're **app-level for now** (open question 1). VS Code/Cursor terminals can't be selected from outside the editor. On Linux, raising another app's window is not portable (Wayland forbids it), so only tmux is supported.

### 5.3 Failure states and messages

| State | Where | Message and next step |
|---|---|---|
| External session ended (deep link pid gone, or pid no longer listed when Jump is pressed) | Sessions page banner / 409 | "That Claude Code session isn't running any more." + `claude --resume <id>` (copyable) + **Resume in Eyrie** when the directory is allowed |
| Eyrie session exited | Row | "Exited (1)" + **Resume** (starts a new Eyrie session with `mode: resume`) + copyable resume command |
| Host supports app only | Toast after Jump | "Brought Warp to the front. Eyrie can't pick its tab: look for ttys015." |
| Host unknown / Linux non-tmux | Jump disabled, tooltip | "Running in GNOME Terminal on pts/3. Eyrie can't switch to it; switch yourself." |
| Tab not found (closed between listing and click) | Toast | "Couldn't find a Terminal tab on ttys004. It may have just closed." |
| macOS Automation permission denied (osascript error -1743) | Toast | "macOS blocked Eyrie from controlling iTerm2. Allow it in System Settings → Privacy & Security → Automation, then try again." |
| tmux pane not attached anywhere | Toast | "Selected the pane, but no terminal is attached to that tmux session. Run `tmux attach -t <session>`." |
| Not running anywhere and no id known | Banner | "Not running. Start a new session in Eyrie." |

Resume commands are display-only strings: `cd <cwd> && claude --resume <id>` (Codex `codex resume <id>`, Gemini `gemini --resume <id>`), each part `shlex.quote`d.

## 6. API changes

Additive; `make types` regenerates the frontend types.

```
Session (Eyrie)     + display_name: str, name_source: "user" | "tool" | "id" | "none",
                      resume_command: str | None
ExternalSession     + conversation_id: str | None, display_name: str, name_source, name_exact: bool,
                      terminal: str | None            # "iTerm2", "Warp", "tmux", …
                      focus: "tab" | "pane" | "app" | "none"
                      href: str                       # /sessions?ext=…
SummarySession      + display_name, name_source, conversation_id, href
Features            + terminal_windows: bool          # macOS: offer "Open in Terminal / iTerm2"
```

New actions in `actions/registry.py` (both non-destructive, token-protected like every action, audited):

| Action | Params | Runs |
|---|---|---|
| `sessions.focus` | `{pid: int, tty: str}` | `osascript -e … <tty>` or `tmux … select-pane`, per §5.2 |
| `sessions.open_terminal` | `{name: eyrie-…, app: "terminal" \| "iterm"}` | `osascript -e … <attach command>` |

`Action` gains `precheck_first` (so the session is checked against the live list **before** any process is inspected or argv built, including on `dry_run`), `Planned.then` (a follow-up argv: tmux pane, then the client's terminal), and `explain(result)` to turn osascript output (`ok`, `missing`, error -1743) into the messages above.

## 7. Security

- **Same gate as today.** Both actions go through `POST /api/v1/actions/{id}`: `X-Eyrie-Token`, local-only middleware, Pydantic validation, audit log. No new endpoint shape, no generic "run".
- **Only listed sessions.** `sessions.focus` re-lists external sessions and refuses (409) unless `pid` is a current interactive session of an **enabled** tool **and** its tty equals the given `tty`. A pid of some other process (or a reused pid on another tty) is rejected before anything else happens.
- **Strict inputs.** `tty` must match `^ttys?\d{1,4}$` (macOS) or `^pts/\d{1,4}$` (Linux); `name` must match `^eyrie-[a-z0-9]{4,16}$`; `app` is a literal.
- **No user strings in AppleScript source.** The scripts are constants in the code (`on run argv … end run`); the tty, app name or attach command is passed as `osascript -e … -- <arg>`, read with `item 1 of argv`, and compared or executed as a value, never compiled. Names from transcripts are never passed to osascript or a shell at all.
- **argv only.** Everything runs through the `Runner` (`shell=False`, stdin closed, timeout). tmux targets are pane ids (`%12`) read from tmux itself, never from the request.
- **Process inspection** stays read-only (`ps`, `lsof`/`/proc`, `tmux list-panes`), as external detection already does. Prompt text is still never read: only argv[0], resume targets and the tmux socket flag are parsed.
- **macOS consent.** The first jump to Terminal/iTerm triggers macOS's Automation prompt for Eyrie; refusing it is handled (§5.3). Eyrie only *selects/activates*; it never types into your terminals (`open_terminal` opens a *new* window running the attach command).
- **Reading names.** Transcript tails are bounded (256 KB) and cached by (size, mtime); malformed lines are skipped; names are length-capped and stripped of control characters before they reach the UI or the tray menu.

## 8. Testing plan

Backend (pytest, no real processes or osascript, existing conftest guards):
- Name extraction per tool from fixture files: Claude pid file (`user`/`auto`/`derived`/absent), transcript `custom-title` after `ai-title`, title beyond the tail window, malformed lines; Codex `session_index.jsonl` last-wins and UUIDv7 short ids; Gemini `$set.summary`.
- Fallback order (name → short id → label) and approximate matches.
- Deep links: `href` built for Eyrie and external sessions; odd values never produced.
- Action validation: unknown pid, pid of a non-tool process, tty mismatch, bad tty formats (`../`, `ttys004;`, `pts/x`), disabled tool, bad `name`/`app`.
- osascript argv construction: script is constant, tty passed after `--`, never interpolated; tmux socket flags; `explain()` mapping (`missing`, -1743).
- Host detection from ps fixtures (iTermServer, Terminal, Warp, tmux, unknown, Linux).

Widget (Rust): unit tests for the session-href check. Frontend: `make check` (typecheck, lint, build). Manual on macOS: jump to Terminal.app and iTerm2 tabs, tmux pane inside iTerm, Warp (app), Automation prompt allow/deny; on Ubuntu: tmux pane, GNOME Terminal message.

## 9. Delivery

1. This design.
2. Prototype ([`prototype/session-names-and-jump.html`](../prototype/session-names-and-jump.html)): Sessions page with names and fallbacks, Jump and every message, the widget panel and tray menu.
3. Code: adapters' `names()`, schema fields, actions, Sessions page, widget panel, tray menu (Rust), tests.

## 10. Open questions

1. WezTerm and kitty can select a tab via their own CLIs. Worth adding as a second lookup step, or wait until someone asks (my default)?
2. Should Claude's AI title (`ai-title`) show when you never renamed a session? It's usually descriptive, but it isn't a name you chose. Default: yes, marked as source `tool`.
3. `open_terminal` app choice: remembered per browser (default), or a setting in `eyrie.toml`?
4. Linux: is a GNOME Shell / KDE window-raise worth doing for X11 sessions, given it can't work on Wayland?
