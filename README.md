# Eyrie

A local control plane for your AI coding tools. Eyrie runs on your laptop and lets you
see and manage Claude Code, Codex, their MCP servers and plugins, Nexus agent memory and
a personal task list from one place. Everything is read from, and written back to, the
files and CLIs those tools already use. No accounts, no cloud.

## What you can do

| Page | What it does |
|------|--------------|
| **Sessions** | Start, resume and stop Claude Code and Codex sessions. They run in Eyrie's own tmux server, so they keep going if Eyrie restarts. Type into them in the browser terminal, or attach from any terminal with the command Eyrie shows. |
| **Usage** | Claude Code cost and tokens per day, model and project, built from session transcripts and kept in `~/.eyrie/usage.db` after Claude Code prunes them. Codex totals per model. |
| **Claude Code / Codex** | Per-project and per-thread activity. |
| **MCP servers** | Claude Code (user, local, project scope) and Codex servers. Add and remove them; Eyrie runs `claude mcp` / `codex mcp` and shows you the exact command first. |
| **Plugins** | Enable or disable Claude Code plugins (`claude plugin`). |
| **Nexus memory** | Browse, edit, create and delete Nexus agents' memory files in the vault. Edits never overwrite an agent's change made in the meantime; deleted files go to the vault's `.trash`. |
| **Tasks** | A personal checklist in the vault (`Personal/Tasks.md`), edited one line at a time so the rest of the file stays as you wrote it. |
| **Activity** | Every change Eyrie has made, with secrets masked (`~/.eyrie/audit.jsonl`). |

## Install

Needs Python 3.12, Node 22, tmux, and the `claude` / `codex` CLIs you want to manage.

```bash
make install    # builds, then runs Eyrie in the background at login
                # (launchd on macOS, a systemd user unit on Ubuntu) -> http://127.0.0.1:8787
make status     # installed? answering?
make logs       # follow ~/.eyrie/logs/eyrie.log
make uninstall  # removes the agent; tmux sessions keep running
```

Services don't see your shell's `PATH`, so `make install` asks your login shell for it
(from a clean environment) and records it; that's how the service finds `claude`, `codex`
and `tmux`. After pulling changes, run `make install` again to rebuild and restart.
`make install DRY_RUN=1` prints the service file and the commands without changing
anything. On Ubuntu, `loginctl enable-linger` keeps Eyrie running while you're logged out.
Elsewhere, `make serve` runs the same thing in the foreground.

## Top-bar widget

A small menu-bar (macOS) / top-bar (Linux) app: an icon that changes when something needs
you, today's cost next to it on macOS, and a panel with what needs you, live sessions and
quick actions. It talks only to your installed Eyrie on 127.0.0.1. Needs Rust
(<https://rustup.rs>).

```bash
make widget        # build and run it (debug) against the installed Eyrie
make widget-dist   # build Eyrie.app + .dmg (macOS) or .deb/.rpm/AppImage (Linux)
```

On macOS click the icon for the panel and right-click it for the menu. On Linux the
indicator opens a menu (AppIndicator has no click events) with "Show panel". It starts at
login by default; turn that off in its menu. Not signed by a developer account yet, so on
macOS open it the first time with right-click → Open.

## Develop

```bash
make dev     # API on 127.0.0.1:8000 + UI with hot reload on http://localhost:5173
make test    # backend tests (some use a real tmux on a throwaway socket)
make types   # regenerate frontend/src/api/generated.ts after changing backend/app/schemas.py
make check   # tests + generated-types check + UI build + lint (what CI runs)
```

`make help` lists every target. The API contract is `backend/app/schemas.py`; the
frontend's types are generated from it, so change the schema and run `make types`
instead of editing types by hand.

## Configuration

Copy `eyrie.example.toml` to `eyrie.toml` (gitignored). Every key is optional: paths to
the vault and to Claude/Codex state, which sources are enabled, where sessions may start
(`[sessions] roots`), MCP servers to hide, price overrides, CLI paths. Env vars override
the file, e.g. `EYRIE_PATHS__VAULT=~/notes`; `EYRIE_CONFIG` points at another file.

## Security

Eyrie can run commands as you, so it only obeys this machine:

- It listens on `127.0.0.1` only and rejects any `Host` or `Origin` that isn't loopback,
  so another website or a DNS-rebinding page can't drive it.
- Every change needs the per-install token in `~/.eyrie/token` (mode 600). The UI gets it
  from a same-origin endpoint; the terminal WebSocket carries it as a subprotocol.
- Pages can't be framed by other sites (`X-Frame-Options: DENY`, `frame-ancestors 'none'`).
- It can only do a fixed list of things. There is no "run any command" endpoint. CLIs
  are called with argument lists, never through a shell, and their config files are
  never edited directly.
- Every write is checked against what you last saw (etags), confined to its folder, and
  logged.

## Architecture

FastAPI backend (`backend/app`): sources read state, a small action layer changes it
through the tools' own CLIs, and a session manager drives tmux. React + Vite + Tailwind +
shadcn/ui frontend (`frontend/src`). The design, what was learned building each part,
and the reasoning are in [`docs/architecture.md`](docs/architecture.md). There's a
clickable mock in [`prototype/`](prototype/index.html).

Personal project, laptop only, macOS first.
