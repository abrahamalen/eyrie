# Eyrie

A local control plane for your AI coding tools: Claude Code, Codex, MCP servers and
agent plugins (e.g. Nexus), plus a personal task list. The revamp toward full control
(sessions, MCP/plugin management, usage history) is in progress; see
[`docs/architecture.md`](docs/architecture.md) and the clickable
[`prototype/`](prototype/index.html).

FastAPI backend + React/TypeScript frontend, run natively with `make dev`. No accounts,
no cloud: everything reads what's already on your disk, live, on every request.

## Architecture

```
eyrie/
├── backend/     FastAPI. app/sources/*.py each implement one Source (available + snapshot),
│                registered from config and served at /api/v1/sources/{id}
├── frontend/    React + TypeScript (Vite), Tailwind v4 + shadcn/ui, react-router-dom.
│                Sidebar portal with a page per source, polling every 10-15s
├── docs/        Architecture and design decisions
└── prototype/   Clickable HTML mock of the revamped portal
```

## What it tracks

- **Sessions**: start, resume and stop Claude Code and Codex sessions in Eyrie's own
  tmux server (`tmux -L eyrie`); they keep running if Eyrie restarts. Watch a live
  read-only view of each, or attach from a terminal with the command Eyrie shows.
- **Claude Code**: per-project cost, tokens and models from `~/.claude.json` (last
  session per project).
- **Usage**: full Claude Code cost and token history by day, model and project,
  indexed from session transcripts into `~/.eyrie/usage.db` (kept after Claude Code
  prunes old transcripts) and priced from `backend/app/usage/prices.py`.
- **Codex**: recent threads, tokens, repos and models from `~/.codex/state_5.sqlite`.
- **MCP servers**: Claude Code (user, local, project scopes) and Codex servers, with
  last-known connect failures from recent transcripts (not a live ping). Add and remove
  them from Eyrie; it runs `claude mcp` / `codex mcp` and shows the exact command first.
- **Plugins**: Claude Code plugins, enabled or disabled from Eyrie via `claude plugin`.
- **Activity**: every change Eyrie makes, in `~/.eyrie/audit.jsonl` (secrets masked).
- **Nexus memory**: which agents have memory in the vault and how much.
- **Tasks**: a plain markdown checklist in the vault at `Personal/Tasks.md`, editable
  from Obsidian too. The vault-root `Tasks.md` is never touched.

## Running it

```bash
make dev    # installs deps on first run, then API 127.0.0.1:8000 + UI -> http://localhost:5173
make test   # backend tests
```

`make help` lists every target. Vite proxies `/api/*` to the backend.

## Configuration

Copy `eyrie.example.toml` to `eyrie.toml` (gitignored) to change paths, enabled
sources, or MCP servers to hide. Env vars override the file, e.g.
`EYRIE_PATHS__VAULT=~/notes`. `EYRIE_CONFIG` points at a different config file.

## Security

Eyrie is moving toward changing local tool config and running sessions, so it only
obeys this machine:

- The API binds to `127.0.0.1` and rejects any `Host` or `Origin` that isn't loopback
  (blocks DNS rebinding and other websites), and any cross-site browser fetch.
- Every write needs the per-install token in `~/.eyrie/token` (created on first run,
  mode 600) as `X-Eyrie-Token`. The portal fetches it from `/api/v1/auth/token`, which
  only same-machine, same-origin pages can read.

Laptop only: there's no remote access.
