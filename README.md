# Eyrie

A local portal for keeping an eye on your AI coding tools — Claude Code, Codex, MCP
servers, and installed agent plugins (e.g. Nexus) — plus a simple task list.

FastAPI backend + React/TypeScript frontend, run with `make dev` or Docker. No accounts, no cloud: everything
reads what's already on your disk, live, on every request.

## Architecture

```
eyrie/
├── backend/     FastAPI — app/services/*.py query ~/.claude.json, ~/.codex/*.sqlite,
│                session transcripts, and the agent-memory vault directly, per-request
│                (no batch/snapshot step — every API call reflects current state)
└── frontend/    React + TypeScript (Vite), Tailwind v4 + shadcn/ui, react-router-dom —
                 sidebar portal with a page per section, polling the backend every 10-15s
```

## What it tracks

- **Claude Code**: per-project cost, input/output tokens, and model breakdown, live
  from `~/.claude.json`'s own session stats.
- **Codex**: recent threads, tokens used, and which repos/models were active, live
  from `~/.codex/state_5.sqlite`.
- **MCP servers**: which are configured, and their last-known connect/fail status
  recovered from recent session transcripts (not a live ping — nothing outside a
  running Claude Code session can ping an MCP server).
- **Agent plugins** (e.g. Nexus): which agents have run and how much memory they've
  accumulated.
- **Tasks**: a plain checklist, stored as markdown (`Obsidian Vault/Tasks.md` by
  default) so it's editable from anywhere, Eyrie included.

## Running it locally

```bash
make dev   # installs deps on first run, then API :8000 + UI -> http://localhost:5173
```

`make help` lists everything (`build`, `lint`, `clean`, ...). Vite proxies `/api/*`
to the backend, so there's no CORS setup in dev.

### Docker

```bash
make up    # builds + runs -> http://localhost:8080  (EYRIE_PORT to change)
make down
```

nginx serves the built UI and proxies `/api` to the backend. `~/.claude.json`,
`~/.claude`, `~/.codex` are mounted read-only; the Obsidian vault is mounted
read-write (tasks). Paths are in `docker-compose.yml`.

## Configuration

`backend/app/services/tasks.py` hardcodes the tasks file path (`TASKS_FILE`) —
point it anywhere. Everything else reads from the standard `~/.claude` / `~/.codex`
locations directly, no config needed yet.

## Status

Personal project, built for one machine and one set of tools. Not yet portable
(different OS paths, missing tools, etc.) or containerized — both are next steps
once the feature set settles. Currently read-only: it observes Claude/Codex
activity but can't launch or control sessions.
