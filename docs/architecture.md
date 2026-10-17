# Eyrie — revamp architecture (draft)

Status: **draft, under review**. This PR is design only. The prototype and the code
come in separate PRs once this is agreed.

## 1. Context

Eyrie v0 is a **read-only** dashboard: a FastAPI app reads local agent state on every
request, and a React portal polls it. The revamp turns it into a **control plane**:
everything about the local AI tooling (sessions, MCP servers, plugins, agent memory,
personal tasks) should be manageable from Eyrie, with full usage history.

v0 was built page by page, and these problems carry into the revamp:

| # | Problem | Where |
|---|---------|-------|
| P1 | Every source is a one-off module with its own path constants, error handling and return shape. Adding a source means touching the router, `types.ts`, `client.ts` and a new page | `backend/app/services/*.py`, `routers/status.py` |
| P2 | Paths are hardcoded to this machine (`~/workspace/Obsidian Vault/...`) | `services/tasks.py:6`, `services/nexus.py:6` |
| P3 | Claude cost only counts the **last session** per project (`lastCost`), so long-term spend is invisible | `services/claude.py:29` |
| P4 | Tasks writes rebuild the whole file: any non-task lines are dropped, and index-based IDs race with edits made in Obsidian | `services/tasks.py:21`, `routers/tasks.py:24` |
| P5 | The MCP status scan re-reads the 15 newest transcripts on every 10s poll | `services/mcp.py:17` |
| P6 | Frontend response types are written by hand, so they can drift from the backend | `frontend/src/api/types.ts` |
| P7 | Personal tool, but it shows whatever is in `~/.claude.json`, including work MCP server names | `services/claude.py:67` |
| P8 | Tasks point at the vault-root `Tasks.md`, which holds **work** tasks. Eyrie should only touch personal tasks | `services/tasks.py:6` |

## 2. Decisions so far

| Question | Decision |
|----------|----------|
| Read-only or control? | **Full control.** Everything manageable from Eyrie |
| Usage history? | **Yes, full history** from session transcripts |
| Tasks home? | **Vault, personal only**: `Personal/Tasks.md` (created on first write). The vault-root work `Tasks.md` is never read or written |
| Company tools? | **None.** Personal project, so no Qure-hosted integrations |
| Remote / phone access? | **Laptop only** for now. Tailscale + token remains the path if it's ever wanted |
| Docker? | **Dropped.** Native-first; the v0 Docker files are removed in the code phase |

## 3. Goals / non-goals

**Goals**
- **Manage, not just view.** Each section has actions:
  - Sessions: start, resume, attach, stop.
  - MCP servers: add, remove, inspect.
  - Plugins: install, enable, disable.
  - Nexus memory: browse, edit, delete.
  - Tasks: full CRUD.
- **Full usage history**: cost and tokens over time, per model and per project.
- A uniform **source + action** abstraction: adding a capability means one backend module plus one page.
- Configurable paths, so it runs on another machine without code edits.
- Safe by default: localhost-only, authenticated actions, every action audit-logged.
- Keep the v0 principle: **local-only, no accounts, no cloud**.

**Non-goals**
- Multi-user and remote hosting.
- Any company/Qure integration.
- Replacing the Claude Code / Codex UIs. Eyrie orchestrates them and doesn't reimplement them.

## 4. Architecture

```mermaid
flowchart LR
  subgraph Host["Host machine"]
    subgraph Disk["Local state"]
      CJ["~/.claude.json + settings"]
      CT["~/.claude/projects/*.jsonl"]
      CX["~/.codex/state_5.sqlite"]
      V["Vault: Personal/Tasks.md, agent-memory/Nexus"]
    end
    CLI["claude / codex CLIs"]
    TMUX["tmux server (eyrie-* sessions)"]
  end

  subgraph Backend["Eyrie backend (FastAPI, 127.0.0.1 only)"]
    CFG["config"]
    REG["source registry (read)"]
    ACT["action layer (write)"]
    SESS["session manager"]
    IDX["usage indexer (SQLite)"]
    AUD["audit log"]
    API["/api/v1 + WS /term"]
  end

  UI["React portal + xterm.js"]

  CJ & CT & CX & V --> REG
  CT --> IDX
  ACT -- "official CLI commands" --> CLI
  ACT -- "in-place edits" --> V
  SESS --> TMUX --> CLI
  ACT & SESS --> AUD
  REG & ACT & SESS & IDX --> API
  API <--> UI
```

Two halves:
- **Read path**: the source registry reads state from disk.
- **Write path**: the action layer and session manager change things, and only through official interfaces.

### 4.1 Source contract (read, fixes P1)

```python
class Source(Protocol):
    id: str
    title: str
    def available(self) -> Availability: ...    # present? readable? why not?
    def snapshot(self) -> BaseModel: ...        # typed payload
```

- `GET /api/v1/sources` lists sources and their availability. `GET /api/v1/sources/{id}` returns a snapshot.
- Failures go through one shared envelope (`{available: false, reason}`).
- Parse results are cached, keyed by the inputs' `(path, mtime, size)`, so a poll costs a `stat()` (fixes P5).

### 4.2 Action layer (write)

Built in slice 4. **Rule: never hand-edit another tool's config files.** Changes go through that tool's own CLI; reads come from its config files.

| Capability | Write (CLI) | Read |
|------------|-------------|------|
| MCP servers (Claude) | `claude mcp add` / `remove`, scopes user / local / project | `~/.claude.json` (user, and local per project) + each known project's `.mcp.json` |
| MCP servers (Codex) | `codex mcp add` / `remove` (global only, stdio or http) | `~/.codex/config.toml` |
| Plugins | `claude plugin enable` / `disable --json` | `claude plugin list --json`, cached until the plugin state files change (~0.7 s per call) |
| Plugin install / uninstall | Not yet: marketplace installs can declare a command a person must approve by sha256 (`--accept-command`), which needs its own two-step flow | |
| Codex threads, sessions | Slice 5 (session manager) | |
| Nexus memory | Slice 6 (direct file ops inside `agent-memory/Nexus` only) | |
| Personal tasks | Slice 2 (in-place line edits) | |

- **No health checks**: `claude mcp list` / `get` health-check servers, which launches every stdio server. So they're never used for reads.
- **Declared actions only**: `POST /api/v1/actions/{id}` with `{params, dry_run, confirm}`. The current ids are `mcp.add`, `mcp.remove`, `plugins.enable` and `plugins.disable`. There is no generic command action.
- **Validation**: params are checked with pydantic before anything runs.
  - Names: `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, so a value can't pass itself off as a flag.
  - URLs: http(s) only.
  - Env and header names are checked, and header values can't contain newlines.
  - `project_dir` must be an existing absolute directory.
  - Client-specific limits apply, for example Codex has no SSE and no scopes.
- **Running**: argv list, `shell=False`, stdin closed, timeout, serialised by a lock. A stdio command always comes after `--`. Local and project scope run with `cwd` set to the project.
- **Preview**: `dry_run` returns the exact argv, with env and header values masked. The UI shows it before any change.
- **Confirm**: destructive actions (`mcp.remove`) return `428` until `confirm: true` is sent.
- **Verify**: after a run, Eyrie checks the change actually happened, because some CLI paths exit 0 without doing it.
  - `claude plugin enable` of a plugin that isn't installed reports success and records it as enabled. So plugin toggles are refused (`409`) unless the plugin is installed, and the enabled state is rechecked afterwards.
- **Audit**: every run appends to `~/.eyrie/audit.jsonl`: action, masked argv, params with secret values masked, ok, exit code, duration, message. `GET /api/v1/audit` serves it, and the Activity page shows it.
- **Sandbox**: `[cli] env` (e.g. `CLAUDE_CONFIG_DIR`, `CODEX_HOME`), together with matching `paths.*`, points the CLIs and reads at a scratch config. That's how this slice was tested end to end with the real CLIs.

### 4.3 Session manager

Claude Code and Codex are interactive TUIs, so Eyrie runs them inside **tmux**. tmux 3.6 is already installed.

- **Start**: `tmux new-session -d -s eyrie-<id> -c <repo> claude [--resume <sid>]`, or `codex` / `codex resume`.
- **Attach in the browser**: a WebSocket bridges a tmux client pty to **xterm.js** in the portal.
- **Attach from a terminal**: `tmux attach -t eyrie-<id>`. It's the same session, so the browser and terminal stay interchangeable.
- **Survives restarts**: sessions keep running if Eyrie restarts or crashes. On boot, Eyrie rediscovers them with `tmux ls`.
- **Stop**: `tmux kill-session`, after a confirm step.
- **Headless jobs** ("run this prompt in repo X"): `claude -p` / `codex exec` with output streamed to the UI.
- **Allowed repos**: sessions only start in directories from a config allowlist (`[sessions] roots`).

Why tmux rather than an in-process pty: sessions outlive Eyrie, you get free terminal attach, and there's no pty lifecycle code to maintain. The cost is a dependency on tmux, which is acceptable for a single-machine tool.

### 4.4 Usage history (fixes P3)

Built in slice 3. What the real transcripts showed, and how the design handles it:

- **Source**: transcripts (`~/.claude/projects/*/*.jsonl`, plus `*/<session>/subagents/*.jsonl`) carry per-response `usage`. Subagent runs are billed to their parent session, so they're included.
- **Dedupe**: one API response is written as several lines (one per content block), each repeating its usage. Naive summing overcounts about 2.3×. Streaming lines can carry partial output counts. Rows are keyed on `(message.id, requestId)` and keep the max of each counter.
- **Retention**: Claude Code prunes old transcripts, so `~/.eyrie/usage.db` is the **system of record** for history, not a disposable cache. Rows outlive their files. A schema change needs a migration, not a rebuild.
- **Incremental**: each file is read from its last byte offset, and only up to its last complete line. A replaced or truncated file is reread, which the upsert keeps idempotent. Measured on this laptop: cold scan of 97 MB / 79 files takes 260 ms; warm scan takes 6 ms. So scanning runs inline on request, throttled to every 10 s, with no background worker.
- **Cost**: tokens × a per-model price table (`app/usage/prices.py`, overridable under `[pricing]`), applied at query time, so a price fix corrects all history. 5-minute and 1-hour cache writes are priced separately; 1-hour writes are about 8× the volume here.
  - Validated against Claude Code's own `cost-state` records: its token counts priced with this table land within a few percent of the cost it reports.
  - `cost-state` itself isn't usable as the source: it has no timestamps, resets on each resumed run, and omits subagents.
  - Transcript-based cost reads 0–15% low, because Claude Code doesn't log some background calls (titles, compaction). The UI says so.
- **Model ids** are normalised (`[1m]`, `-YYYYMMDD` suffixes). Unknown models are listed as unpriced instead of silently counting $0.
- **Projects**: a session counts toward the directory it started in, even if it later `cd`s.
- **Codex**: `threads.tokens_used` is a lifetime total per thread (one thread holds over 1B tokens), so spreading it by day would be wrong. It's reported per model, for threads active in the range.
- **Usage page**: daily cost or tokens (7/30/90 days) stacked by model, by-model table, by-project bars, and a Codex panel. `GET /api/v1/usage?days=N`.

### 4.5 Personal tasks (fixes P4, P8)

- Default file: `<vault>/Personal/Tasks.md`, configurable. The vault-root `Tasks.md` (work) is out of scope.
- **Edit lines in place**: change only the target line and preserve every other line (headings, notes, blank lines).
- Task ID = hash of the task text (not the checkbox, so it survives toggling) plus its ordinal among duplicates.
- Writes carry the file's etag in `If-Match`: a hash of the file content, so it can't be fooled by mtime granularity. If the file changed in Obsidian since the read, the write gets `409` with the current state, and the UI shows it.
- Atomic writes (temp file + rename).

### 4.6 Config (fixes P2, P7)

`eyrie.toml` (gitignored, with a committed `eyrie.example.toml`), overridable with `EYRIE_*` env vars and loaded through `pydantic-settings`:

```toml
[paths]
claude_home = "~/.claude"
codex_home  = "~/.codex"
vault       = "~/workspace/Obsidian Vault"
tasks_file  = "Personal/Tasks.md"   # relative to vault

[sessions]
roots = ["~/personal/projects"]     # where sessions may be started

[privacy]
hide_mcp = []                       # server names hidden from the UI

[server]
port = 8000                         # always bound to 127.0.0.1
```

### 4.7 Security model

Control means Eyrie can run commands as you, so the threat to design against is **another web page or LAN device driving it**.

- **Bind address**: the backend binds to `127.0.0.1` only, never `0.0.0.0`.
- **Auth token**: a random token is generated on first run (`~/.eyrie/token`, mode 600) and is required on every mutating request and on the terminal WebSocket. The portal gets it through a one-time local bootstrap.
- **Host/Origin checks** block DNS rebinding and cross-site requests (only `localhost` / `127.0.0.1` are accepted).
- **Commands**: no arbitrary command endpoint. Only the declared actions in §4.2, with validated arguments.
- **Paths**: file actions are confined to their roots (resolve, then check the prefix) so `../` can't escape them.
- **Remote/phone access**: laptop only (decided). If it's wanted later, it goes through Tailscale plus the same token, never a port open to the internet.

### 4.8 Deployment change

A container can't drive host tmux or the host's `claude`/`codex` with their credentials, so the revamp is **native-first**:
- `make dev` for development.
- `make install` adds a macOS `launchd` agent so Eyrie runs in the background.
- The Docker setup from v0 is **dropped** (decided): `Dockerfile`s, `nginx.conf`, `docker-compose.yml` and `make up/down/logs` are removed in code slice 7.

### 4.9 API and types (fixes P6)

- `/api/v1` plus a WebSocket at `/api/v1/sessions/{id}/term`.
- TS types are generated from OpenAPI (`openapi-typescript`) with `make types`. CI fails if the file is stale.

### 4.10 Frontend

- Same stack: React + Vite + Tailwind v4 + shadcn/ui (Base UI) + react-router. xterm.js is added for terminals.
- The sidebar comes from `GET /api/v1/sources`.
- Pages:
  - Overview
  - **Sessions** (new): list, start, attach, stop
  - Claude Code
  - Codex
  - **Usage** (new)
  - MCP: with add and remove
  - Plugins: with enable and disable
  - Nexus: browse and edit memory
  - Tasks
- Destructive actions use a confirm dialog that shows exactly what will run.

## 5. Repo layout (target)

```
backend/app/
  config.py  security.py  audit.py
  sources/   base.py claude.py codex.py mcp.py plugins.py nexus.py tasks.py
  actions/   base.py runner.py          # argv-only subprocess wrapper
  sessions/  manager.py term_ws.py      # tmux + websocket bridge
  index/     usage.py                   # transcript indexer
  routers/   sources.py actions.py sessions.py usage.py
frontend/src/
  api/generated.ts
  pages/ ...  components/Terminal.tsx
docs/architecture.md
eyrie.example.toml
```

## 6. Tooling / MCPs used to build this

| Tool | Used for |
|------|----------|
| Obsidian MCP | Verify the vault layout (`Personal/`, `agent-memory/Nexus`) while building tasks and nexus |
| GitHub via `gh` | One PR per phase and per code slice |
| Artifact / `archify` | Clickable prototype and diagrams |
| Browser automation skill | Headless QA of every page before each merge |

At runtime, Eyrie makes no MCP calls. It manages MCP **config** through the official CLIs.

## 7. Delivery plan

Each step is its own PR, reviewed before the next one starts.

1. **Design**: this document.
2. **Prototype**: a clickable mock covering Sessions (with terminal), Usage, MCP add/remove, and Tasks with a conflict state.
3. **Code**, sliced:
   1. config, security (token, Host/Origin), source registry; existing sources ported
   2. personal tasks: in-place edits, etag
   3. usage indexer and Usage page
   4. action layer: MCP and plugins via the CLIs, audit log
   5. session manager: tmux, xterm.js, headless jobs
   6. Nexus memory management
   7. generated types, CI check, `launchd` install, remove Docker, README

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Eyrie becomes a local command runner | §4.7: localhost only, token, Origin checks, declared actions only, audit log |
| CLI output formats change (`claude mcp list`, etc.) | Prefer JSON flags where they exist; parse defensively; integration test per CLI version |
| Transcript format is undocumented | Indexer ignores unknown fields, stores a schema version, falls back to `lastCost` |
| Pricing table goes stale | In config, with the date shown in the UI |
| First index build over a large history is slow | Background build with progress; incremental after that |
| A tmux session is orphaned after a crash | Rediscovered on boot via the `eyrie-` prefix; listed and killable from the UI |

## 9. Open questions

None blocking. Prototype feedback lands here.
