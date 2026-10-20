# Tool adapters and first-run setup (design)

Status: design, 2026-10-20. Prototype and code follow as separate PRs.

## 1. Context

Eyrie works well on my machine and badly on anyone else's:

- **The tools are hard-coded.** `claude` and `codex` are literals throughout:
  - the action models (`Literal["claude", "codex"]` in `actions/registry.py:52,103,144` and `schemas.py:80,165,181,333,366`);
  - `Runner.binary`;
  - external detection (`sessions/external.py:23`);
  - the version probes (`summary.py:13`);
  - one source module per tool (`sources/claude.py`, `sources/codex.py`).

  A user with Gemini CLI sees nothing.
- **The defaults are mine.** `paths.vault = ~/workspace/Obsidian Vault` with `Personal/Tasks.md` fits one person. Anyone else has to hand-write `eyrie.toml`, and the config file lives in the repo checkout, which a packaged install won't have.
- **The pages are fixed.** The sidebar always shows Codex, Plugins, Tasks and Agent memory, even when there's nothing behind them.

Agent memory was made generic in #23. This design does the same for the tools and the rest of the setup.

## 2. Goals and non-goals

Goals:
1. Adding a tool is one new module, with no router, schema or page edits.
2. Claude Code, Codex and Gemini CLI at launch. Each tool supports what it actually has, and the UI only offers that.
3. A first run that finds what's installed, asks only what it can't detect, and writes the config.
4. No behaviour change for Claude and Codex, which is checked by the existing 180+ tests passing unchanged in the refactor PR.

Non-goals:
- IDE agents (Cursor, Windsurf, Copilot). They have no local CLI session model Eyrie could drive.
- Writing another tool's config files directly. Changes still go through each tool's own CLI, as today.
- Windows (still deferred).

## 3. The adapter

One Python module per tool in `backend/app/tools/<id>.py`, registered in `tools/__init__.py`. An adapter is a small class with **capabilities**. Each capability is optional, and the UI and API ask "does this tool have X?" instead of "is this Claude?".

```python
class Tool(Protocol):
    id: str                      # "claude" | "codex" | "gemini" — becomes the only literal
    title: str                   # "Claude Code"
    binary: str                  # default executable name; tools.<id>.bin overrides
    version_args: list[str]      # ["--version"]

    # each is None when the tool doesn't have it
    sessions: SessionCaps | None
    usage: UsageCaps | None
    mcp: McpCaps | None
    plugins: PluginCaps | None
    memory: MemoryCaps | None
```

| Capability | What the adapter provides | Used by |
|---|---|---|
| `sessions` | `argv(mode, cwd, resume_id, new_id)` for new / continue / resume. `match(cmdline)` returns `(tool, resume_target)` for a terminal process, or None for helpers. `activity(cwd, resume_target)` gives the last-activity time and whether it's exact | `sessions.start`, `sessions/external.py`, Sessions page |
| `usage` | `files()` lists transcript paths to index. `parse(line, path)` yields `UsageRow(key, ts, session_id, project, model, input, output, cache_read, cache_write, …)`. `conversations()` returns recent ones to resume. A price table | `usage/index.py`, Usage page, summary spend |
| `mcp` | `servers()` reads the configured servers (read-only). `add_argv(...)` / `remove_argv(...)` build CLI calls. Scopes and transports supported | MCP page, `mcp.*` actions |
| `plugins` | `list()` plus `enable_argv` / `disable_argv` | Plugins page (Claude only today) |
| `memory` | Folder of `<agent>/*.md` | Agent memory page (Claude only today) |

What stays shared, unchanged and tool-agnostic:
- the Runner;
- masking;
- the tmux session manager;
- the browser terminal;
- the audit log;
- the security middleware.

An adapter supplies data and argv; it never runs anything itself.

### 3.1 How the three tools map

| | Claude Code | Codex | Gemini CLI |
|---|---|---|---|
| Binary | `claude` | `codex` | `gemini` |
| New / continue / resume | `--session-id <uuid>` / `--continue` / `--resume <id>` | `--cd <dir>` / `resume --last` / `resume <id>` | (none) / `--resume` (latest) / `--resume <uuid>`. Resume only works from the same project directory |
| Process match | `claude` with a tty; skip `daemon`, `bg-*`, `mcp` | `codex`; skip `app-server`, `mcp` | `gemini` (a node script: match on argv[1] basename too); skip non-tty |
| Transcripts | `~/.claude/projects/<slug>/*.jsonl` plus `*/subagents/*.jsonl` | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | `~/.gemini/tmp/<project_hash>/chats/session-*.jsonl` (older: `.json`); subagents in `chats/<parent>/` |
| Usage per call | `message.usage`, dedupe on `(message.id, requestId)` | `token_count` events: `last_token_usage {input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens}` | `tokens {input, output, cached, thoughts, tool, total}` on `gemini` messages; records patched via `$set` / `$patch` / `$rewindTo` |
| Project of a session | `cwd` on each line | `session_meta.cwd` in the rollout | metadata line has `projectHash` and `directories`; the hash is derived from the project root |
| MCP config | `~/.claude.json`, `.mcp.json` | `~/.codex/config.toml` | `~/.gemini/settings.json`, `.gemini/settings.json` (`mcpServers`: `command/args/env/cwd`, `url` for SSE, `httpUrl` for HTTP) |
| MCP CLI | `claude mcp add/remove -s user/local/project` | `codex mcp add/remove` | `gemini mcp add/remove -s user/project -t stdio/sse/http -e -H` |
| Plugins | `claude plugin …` | (none) | (none; Gemini has "extensions", out of scope for v1) |
| Memory | `~/.claude/agent-memory` | (none) | (none; `GEMINI.md` is context, not memory) |

Two wins fall out of this:
- **Codex gets real daily usage.** Today Eyrie only reads a lifetime `tokens_used` per thread from `state_5.sqlite`, so Codex is "per model, never per day". The rollout files have per-turn `last_token_usage` with timestamps, so Codex joins the same daily index and spend chart as Claude.
- **Gemini's churn is contained.** Its storage moved from `.json` to append-only `.jsonl` with patch records within months. Google also says Gemini CLI was replaced by "Antigravity CLI" for free-tier and Google One users on 2026-06-18. All of that is confined to `tools/gemini.py`. When the format can't be read, the adapter reports usage as unavailable; it never crashes the index.

## 4. Usage index changes

- `messages` gets a `tool` column. Keys are prefixed `<tool>:` so tools can't collide. This needs schema version 2, with a migration: existing rows become `tool = 'claude'`, and the keys are rewritten once. It's a migration, not a rebuild, because Claude Code has already pruned transcripts the index still holds.
- Cache columns are generalised: `cache_read` and `cache_write`, with Claude's 5m/1h split kept as `cache_write_1h` (zero for other tools). Each tool's price table says how its counters map to dollars.
- `report()` groups by tool as well as by model, project and day. The Usage page gets a tool filter.

## 5. Config and first run

### 5.1 Where config lives

- Today it's `<repo>/eyrie.toml`, which a packaged app has no repo for. New default: `~/.eyrie/eyrie.toml`. `EYRIE_CONFIG` still overrides it, and `<repo>/eyrie.toml` is still read if present, for dev.
- New keys:

  ```toml
  [tools]
  enabled = "auto"            # or ["claude", "gemini"]; auto = every adapter whose binary is found
  [tools.claude]
  bin = "/opt/homebrew/bin/claude"   # replaces cli.claude_bin (old key read as an alias for one release)
  [tools.gemini]
  home = "~/.gemini"
  ```

- `paths.vault` loses its personal default. Tasks becomes `paths.tasks = "<file>"`, and it's off until set.

**As built (2026-10-20):** binaries and tool homes stay under their existing keys
(`cli.<tool>_bin`, `paths.<tool>_home`) rather than `[tools.<id>]` tables; first run doesn't
need to set them. `paths.tasks` is an absolute file path, and `paths.vault` / `tasks_file`
are gone. New answers are applied to the running app (no restart), and writing merges into
the existing file so other sections survive. Obsidian vaults are offered as a starting
folder only, never a file name, since a vault can hold several task lists.

### 5.2 First-run flow

`GET /api/v1/setup` reports what Eyrie detects; `POST /api/v1/setup` writes `~/.eyrie/eyrie.toml`, using the token, the etag check and the audit log as usual. The UI shows a setup screen whenever no config file exists.

1. **Tools.** Each adapter's binary is found on the login PATH (the same capture `service.py` uses), with its version and whether its home folder exists. You untick what you don't want.
2. **Where you work.** The session roots are suggested from the directories the tools already know, e.g. `~/personal/projects` when that holds 5 known projects. You confirm or edit them.
3. **Tasks (optional).** Pick a markdown file, or skip. An Obsidian vault is detected from `~/.config/obsidian/obsidian.json` (Linux) or `~/Library/Application Support/obsidian/obsidian.json` (macOS) and offered as a starting folder. It's never required.
4. **Agent memory** is shown when the folder exists, and needs nothing to set up.
5. Write the config. The **Settings** page later edits the same file, so first run isn't a one-shot.

For me, first run writes what's implicit today (vault tasks file, roots), so nothing changes on my machine.

## 6. API and UI

- `Literal["claude", "codex"]` becomes `ToolId`, validated against the registry at request time. An unknown or disabled tool is a 422.
- **Sources:**
  - `/api/v1/sources` lists per-tool sources (`claude`, `codex`, `gemini`) next to the shared ones (`sessions`, `usage`, `mcp`, `tasks`, `memory`).
  - `/api/v1/meta` returns the enabled tools and their capabilities, so the UI can build itself from that.
- **Sidebar, home page and widget:**
  - pages appear only for capabilities some enabled tool has (no Plugins page without a plugin-capable tool, no Tasks without a tasks file);
  - the summary's `health` becomes one entry per enabled tool;
  - `cli_missing` fires only for tools you enabled.
- **Session dialog:** offers enabled tools with `sessions`. Modes are limited to what that tool supports. Gemini resume is only offered in the conversation's own directory.

**As built (2026-10-20):** `/api/v1/meta` returns `tools[]` (installed, used, enabled,
capabilities) and `features` (tasks, agent_memory, mcp, plugins); the UI keeps them in a
subscribable store, refreshed when Settings saves. The sidebar, the home page's tasks card,
the setup card and the widget's "+ Task" follow them; `summary.tasks` is `null` without a
tasks file. Sources stay registered (so a tool installed later works without a restart);
what's hidden is decided per request. A disabled tool's history stays in usage.db but out
of reports and recent projects.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Gemini or Antigravity changes storage again | Format handling stays inside the adapter; parse failures mark usage unavailable rather than wrong; fixture-based tests per format version |
| The project hash can't be reversed to a path | Use the metadata line's `directories` for the project; when it's missing, fall back to "unknown project" |
| The index migration goes wrong on real data | Back up `usage.db` to `usage.db.v1` before migrating; check that totals before and after are equal in the migration test; refuse to start on mismatch |
| Capability-driven UI hides something I use | The refactor PR lands with no UI change; capability gating comes in its own PR |
| Gemini isn't installed here to test against | Prototype step: install it in a throwaway `HOME` (`HOME=/tmp/eyrie-gemini`), run one session, and build the fixtures from real files |

## 8. Plan (one PR each)

1. **Prototype:** static HTML of the setup screen, a three-tool Sessions/Usage view, and the capability-driven sidebar, for review only.
2. **Refactor:** an adapter interface plus Claude and Codex adapters. Existing behaviour and tests are unchanged.
3. **Codex daily usage** from rollout files (index schema v2 and the migration).
4. **Gemini adapter:** sessions, external detection, usage, MCP. Fixtures come from a real install.
5. **Config move and setup:** `~/.eyrie/eyrie.toml`, `/api/v1/setup`, the first-run screen, the Settings page.
6. **Capability-driven UI:** sidebar, home, widget, health.

Packaging comes after 5, since it's what makes a first run happen on someone else's machine.

## 9. Open questions

1. Gemini "extensions": skip for v1 (my default), or treat them as plugins?
2. Antigravity CLI: add it as its own adapter once its local storage is known, or wait for users to ask (my default)?
3. Should the Settings page also manage `sessions.idle_minutes` and `privacy.hide_mcp`, or keep those TOML-only?
