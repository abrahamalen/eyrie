# Eyrie

A local portal for keeping an eye on your AI coding tools — Claude Code, Codex, MCP
servers, and installed agent plugins (e.g. Nexus) — plus a simple task list.

FastAPI backend + React/TypeScript frontend, run as plain code for now (no Docker
yet — that's the next step once this is stable). No accounts, no cloud: everything
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

Two processes, two terminals:

```bash
# backend
cd backend
source .venv/bin/activate   # venv already has fastapi + uvicorn installed
uvicorn app.main:app --port 8000 --reload

# frontend
cd frontend
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api/*` to the backend on port 8000
(see `frontend/vite.config.ts`), so there's no CORS setup needed in dev.

## Configuration

`backend/app/services/tasks.py` hardcodes the tasks file path (`TASKS_FILE`) —
point it anywhere. Everything else reads from the standard `~/.claude` / `~/.codex`
locations directly, no config needed yet.

## Status

Personal project, built for one machine and one set of tools. Not yet portable
(different OS paths, missing tools, etc.) or containerized — both are next steps
once the feature set settles. Currently read-only: it observes Claude/Codex
activity but can't launch or control sessions.
