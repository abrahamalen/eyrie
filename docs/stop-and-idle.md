# Stop any session, and idle suggestions (design)

Status: design, 2026-10-20. Prototype and code follow as separate PRs.

## 1. Context

| # | Problem |
|---|---------|
| P1 | Eyrie can stop the sessions it started (tmux), but not the ones in your own terminals. To end a forgotten `claude` in some tab you hunt for the tab, or `kill` a pid by hand and hope it's the right one |
| P2 | Sessions pile up. A week-old Codex in a tab you never look at still holds a few hundred MB and its MCP servers, and nothing tells you |
| P3 | Coming back to a long-idle session with a huge context is silently expensive: the prompt cache expired long ago, so the next message re-reads the whole context. Nobody suggests `/compact` or a fresh start |

Goals:
1. **Stop** any listed session: Eyrie's (exists: `tmux kill-session`) and external ones, safely (§4), with the exact resume command in front of you before you confirm.
2. **Suggest** idle sessions to stop or refresh, with what keeping them costs (RAM, child processes) and, when the context is large, the token cost of resuming.
3. Show it where you look: the home page, the Sessions page, the widget panel. **Stop all idle…** with a checklist.
4. **Snooze / dismiss** a suggestion per session, in Eyrie's own state.

Non-goals: stopping anything Eyrie doesn't list (helpers, MCP servers, shells, terminals), killing process groups, automatic stopping (Eyrie only ever suggests), editing the tools' files, Windows.

## 2. Flow

![Idle suggestion → confirm → validated SIGTERM → result, with the two failure branches](diagrams/stop-and-idle.svg)

Source: [`diagrams/stop-and-idle.workflow.json`](diagrams/stop-and-idle.workflow.json) (Archify workflow; re-render with `archify deliver workflow … --quality showcase` and export SVG from the viewer).

## 3. Definitions

### 3.1 Idle

A **live** session is **idle** when its last activity is at least `sessions.idle_hours` ago (default **24**). It is **suggested** when it is idle, not snoozed or dismissed (§7), and, if `sessions.idle_requires_detached = true`, no client is known to be attached.

| Session | Activity (already computed today) | Attached client |
|---|---|---|
| Eyrie (tmux) with a known conversation | The tool's own last activity for that conversation (transcript / rollout / chat file mtime, as external sessions use) | tmux `session_attached` (the in-app terminal counts) |
| Eyrie without one | tmux `session_activity` (last output in the pane) | same |
| External, Claude Code | Transcript mtime for the conversation in `~/.claude/sessions/<pid>.json` (exact), else newest transcript in the cwd (approximate, `~`) | Unknown for now (your own tmux's `session_attached` could tell; open question 6) |
| External, Codex | Rollout mtime for the `resume` id (exact), else newest thread in the cwd (`~`) | same |
| External, Gemini CLI | Chat file mtime for the session id (exact), else newest in the project (`~`) | same |
| Any, activity unknown | not idle: Eyrie never suggests what it can't measure | — |

Unknown attachment never blocks a suggestion. An approximate activity time is shown with `~` and still counts; two sessions sharing a guess (several in one directory) both get the newest time, so they can only look *less* idle than they are.

`sessions.idle_minutes` (10, "probably waiting for you" on the home page) is unchanged and unrelated: that one is about attention, this one is about cleanup.

### 3.2 What keeping it costs

| Figure | How | Shown |
|---|---|---|
| RAM | Sum of RSS of the session's process and all its descendants, from one `ps -axo pid=,ppid=,rss=` per listing (KiB on macOS and Linux procps) | `~410 MB`; RSS counts shared pages in each process, so it's an upper bound |
| Child processes | Number of descendants in the same snapshot (MCP servers, language servers, shells the agent opened) | `3 child processes`. Their command lines are not read or shown (they can hold tokens) |
| Context size | Usage index: the session's **last top-level turn**, `input + cache_read + cache_write_5m + cache_write_1h` (every adapter stores `input` as the uncached part, so the sum is the prompt size for all three tools) | `~142k tokens` |
| Prompt-cache lifetime | Claude Code: 1 h if that turn wrote a 1 h cache entry (`cache_write_1h > 0`), else 5 min. Codex: 24 h (the longest retention OpenAI offers; conservative). Gemini CLI: not documented, so **no hint** | used only for the hint |

### 3.3 The context hint

Shown on an idle session when the context is at least `sessions.large_context_tokens` (default 100 000), the conversation is known exactly, and idle time exceeds the cache lifetime. Copy, exactly:

> Idle sessions don't use tokens. Its prompt cache has expired, so your next message re-reads ~142k tokens of context. Run `/compact` first, or start fresh.

`/compact` comes from the adapter (`SessionCaps.compact_command`: Claude Code and Codex `/compact`, Gemini `/compress`). No dollar figure: what the re-read costs depends on the plan and on cache-write pricing Eyrie can't see from a transcript. Missing data at any step → no hint, never a guess.

## 4. Stopping an external session: safety

### 4.1 What may be signalled

Exactly one pid, and only when **all** of these hold, checked in this order:

| # | Check | Where | On failure |
|---|---|---|---|
| 1 | Params valid: `pid` 2…99 999 999, `tool` a known id, `tty` matches `^ttys?\d{1,4}$` / `^pts/\d{1,4}$`, `started` an ISO timestamp, `force` a bool | Pydantic | 422 |
| 2 | The pid is in a **fresh** external listing (enabled tool, interactive, has a terminal, not one of Eyrie's panes) with the same `tool` and `tty` | precheck, before planning, also on dry runs | 409 "That session isn't running any more, or isn't one of your Claude Code, Codex or Gemini sessions." |
| 3 | It belongs to Eyrie's own uid | precheck | 409 "pid 4242 belongs to another user; Eyrie only stops your own sessions." |
| 4 | Its exact start time equals `started` (what the UI showed you) | precheck | 409 "pid 4242 is a different process now; nothing was signalled. Refresh the list." |
| 5 | Not Eyrie itself or its parent | precheck | 409 |
| 6 | **Re-verify immediately before the signal**: a one-pid read (`ps -o uid=,stat=,lstart=,command= -p <pid>`) still gives the same uid and start time, isn't a zombie, and its command is still recognised as the same tool | in the action, after you confirmed | "That session had already exited; nothing was signalled." / "pid 4242 is a different process now; nothing was signalled." |

Start time is `ps -o lstart=` (second resolution, `LC_ALL=C`, same format on macOS and procps), not `now - etime`, which jitters by a second between reads. A reused pid would need the same uid, the same tool's binary *and* a start in the same second as the original: not a practical risk.

On **Linux** the race between check 6 and the signal is closed entirely: Eyrie opens a pidfd (`os.pidfd_open`) *before* re-verifying and signals through it (`signal.pidfd_send_signal`), so if the pid was reused in between, the signal can't reach the new process. **macOS** has no pidfd; the window there is the few microseconds between the read and `kill(2)`.

### 4.2 Signals

| Step | What |
|---|---|
| Stop | `SIGTERM` to the pid: `os.kill(pid, SIGTERM)` (pidfd on Linux). Never `kill(-pgid)`, `kill(0)`, `kill(-1)` or `killpg`; pid ≥ 2 is enforced twice (validation and just before the call) |
| Wait | Poll the one-pid read every 200 ms for up to `sessions.stop_wait_seconds` (default 5): gone, a zombie, or a different start time all mean exited |
| Report | `exited` / `still_running` (§6.4). After an exit, the descendants recorded before the signal are checked again; survivors are reported, never signalled |
| Force | Only as a **separate**, explicitly chosen action (`force: true`): goes through the same checks and the same confirm, then sends `SIGKILL`. The UI offers it only after a `still_running` result |

Claude Code, Codex and Gemini CLI all handle SIGTERM as a normal quit (the conversation is already on disk after every turn), so resuming works. SIGKILL can lose the turn in progress; the force dialog says so.

Signals are sent in-process, not via `/bin/kill`: the identity check and the signal must be in the same place to keep the window small (and pidfd isn't reachable from a shell). The action still shows and audits an argv, `kill -TERM 4242` / `kill -KILL 4242`, so the preview and the audit log read the same as every other action.

### 4.3 What never gets signalled

- Anything not in the external list at that moment: helpers (`claude daemon`, Codex app servers), processes without a terminal, other tools, your shell, the terminal app, your tmux server.
- The session's children (MCP servers, language servers). If they outlive the session, Eyrie says which pids are still running and leaves them.
- Process groups, sessions (`setsid`), pid 1, Eyrie and its parent, other users' processes.
- Eyrie's own sessions through this path: they're excluded from the external list and stopped with `tmux kill-session` as today.

### 4.4 Eyrie sessions

Unchanged: `sessions.stop {name}` → `tmux -L eyrie kill-session -t <name>` (tmux sends SIGHUP to the pane). The confirm dialog gains the same details as external ones (idle, RAM, resume command).

## 5. API and schema

Additive; `make types` regenerates the frontend types.

```
Resources           rss_bytes: int | None, child_processes: int | None
Idle                minutes: int, exact: bool,             # activity time is for this conversation
                    since: str,                             # ISO, the activity it's measured from
                    suggested: bool, key: str,              # snooze key, §7
                    snoozed_until: str | None, dismissed: bool,
                    attached: bool | None,                  # None: unknown
                    context_tokens: int | None, cache_expired: bool | None,
                    compact_command: str | None             # set only when the hint applies
Session (Eyrie)     + resources: Resources, idle: Idle | None
ExternalSession     + process_started: str | None           # exact start (lstart), the identity token
                    + uid_ok: bool                           # owned by Eyrie's uid
                    + resume_command: str | None
                    + resources: Resources, idle: Idle | None
Summary             + suggestions: {idle_hours: int, count: int, items: [SuggestionItem]}
SuggestionItem      key, managed, name (eyrie-…) | None, pid | None, tool, display_name, project,
                    idle_minutes, rss_bytes, child_processes, context_tokens, href
ActionResult        + state: str | None                      # sessions.stop_external: exited, still_running
SetupState/Body     + idle_hours: int (1…720)
```

New action in `actions/registry.py` (destructive, `precheck_first`, token-protected, audited like every action):

| Action | Params | Runs |
|---|---|---|
| `sessions.stop_external` | `{pid, tool, tty, started, force: false}` | §4: SIGTERM (or SIGKILL with `force`) to that one pid, wait, report |

Framework change: `Planned.call`, an in-process step that returns a `RunResult`, used instead of the Runner when set. Shown argv, dry run, 428 confirm, precheck, audit and `explain` all work as for CLI steps.

Snooze endpoints (Eyrie's own state, so a small router like tasks/memory rather than an action; token-protected by the middleware, audited):

```
PUT    /api/v1/suggestions/{key}   {"snooze": "1d" | "7d" | "dismiss"}   → Snooze
DELETE /api/v1/suggestions/{key}                                         → 204
```

Deep link: `/sessions?filter=idle` opens the Sessions page filtered to idle sessions.

## 6. UX

### 6.1 Home page: Suggestions card

Below "Needs you", only when `suggestions.count > 0`:

```
Suggestions · 3                                         Stop all idle…
●  build-eyrie          Claude Code · ~/p/eyrie · idle 2 days
   ~410 MB · 3 child processes · ~142k tokens of context        [Stop…] [Snooze ▾]
●  Codex · ttys015      Codex · ~/p/atlas · idle 26 h
   ~180 MB                                                       [Stop…] [Snooze ▾]
```

Snooze menu: "For a day", "For a week", "Don't suggest until it's used again". Footnote line: "Idle = no activity for 24 h. Idle sessions don't use tokens; they hold memory." with a link to Settings.

### 6.2 Sessions page

- Filter above the tables: `All · Idle (3)`; `?filter=idle` selects Idle. Idle shows only idle sessions (suggested or snoozed), both tables.
- Idle rows get a badge `idle 2 d` (amber; grey when snoozed: `snoozed`) and a second line `~410 MB · 3 children`.
- External rows get **Stop** next to Jump. Eyrie rows keep Stop/Close.
- Context hint (§3.3) appears under the row when it applies.

### 6.3 Confirm dialog (external)

```
Stop build-eyrie?
Claude Code · ~/projects/eyrie · idle 2 days · iTerm2 on ttys004 · pid 4242

Eyrie sends SIGTERM to this one process (not its terminal, not its process group).
The conversation is saved; resume it later with:
  cd ~/projects/eyrie && claude --resume 6636c681-…            [Copy]
It has 3 child processes (MCP servers and the like). Eyrie won't signal them; if any
outlive the session, you'll see their pids.

$ kill -TERM 4242
                                                    [Cancel] [Stop session]
```

No resume command known (approximate conversation) → "Eyrie doesn't know which conversation this is, so it can't give you a resume command; `claude --continue` in that folder picks up the newest." Eyrie sessions get the same layout with `tmux … kill-session` as the command.

### 6.4 Results and errors

| Case | Shown in the dialog |
|---|---|
| Exited | "Stopped. Claude Code (pid 4242) exited 0.8 s after SIGTERM." + resume command |
| Exited, children left | … + "2 processes it started are still running (pids 5512, 5513). Eyrie leaves them alone." |
| Still running after the wait | "Still running 5 s after SIGTERM. It may be finishing something, or ignoring the signal." + **Force stop** (opens the force confirm: "SIGKILL ends it immediately; anything it hasn't written yet is lost.", `$ kill -KILL 4242`) |
| Still running after SIGKILL | "Still running after SIGKILL. The process is stuck in the kernel; it will go when that call returns." |
| Already exited (before the signal) | "That session had already exited; nothing was signalled." |
| Not listed / not a tool session / disabled tool | "That session isn't running any more, or isn't one of your Claude Code, Codex or Gemini sessions." |
| Other user | "pid 4242 belongs to another user; Eyrie only stops your own sessions." |
| pid reused | "pid 4242 is a different process now; nothing was signalled. Refresh the list." |
| Permission denied (EPERM) | "The system refused to signal pid 4242 (permission denied). Nothing was stopped." |

### 6.5 Stop all idle…

A dialog listing every live session Eyrie can stop, most idle first. Each row: checkbox, name, tool, folder, idle, RAM, resume command (copy). **Ticked**: idle ≥ threshold and not snoozed. Unticked: everything else (newer, snoozed, unknown activity). Footer: "Stop 3 sessions" (count follows the ticks; disabled at 0). Each stop is a separate action (own checks, own audit entry), run one after another; each row then shows its own §6.4 result, and a row left running offers Force on that row only.

### 6.6 Widget panel

One line under "Needs you" when `suggestions.count > 0`: `● 3 idle sessions · ~1.2 GB  [Review]`, Review opens `/sessions?filter=idle`. The tray menu (Rust) is unchanged.

### 6.7 Settings

A row in "Where you work": **Suggest stopping sessions idle for** `[24]` hours (1–720), saved to `[sessions] idle_hours`.

## 7. Snooze and dismiss

Stored in `<data_dir>/suggestions.json` (default `~/.eyrie/`), written atomically:

```json
{"version": 1, "items": {"claude:6636c681-…": {"until": "2026-10-21T09:00:00+00:00", "activity": "…"}}}
```

| Key | Session |
|---|---|
| `eyrie:<name>` | Eyrie session |
| `<tool>:<conversation id>` | external, conversation known exactly (survives a restart of the same conversation) |
| `pid:<pid>:<start epoch>` | external, conversation unknown |

`until` set → snoozed until then. `until: null` → dismissed until the session's activity is newer than the stored `activity`. Expired snoozes set more than 30 days ago are dropped on write (at most 500 entries are kept). Nothing is written to the tools' files.

## 8. Config

```toml
[sessions]
idle_hours = 24              # suggest stopping after this long without activity
large_context_tokens = 100000  # the /compact hint's threshold
idle_requires_detached = false # true: only suggest sessions with no client attached (where known)
stop_wait_seconds = 5        # how long to wait for an exit after SIGTERM
```

`idle_hours` is also in Settings; the others are file-only.

## 9. Data sources per OS

| Need | macOS | Linux |
|---|---|---|
| Sessions | `ps -axo pid=,ppid=,tty=,etime=,command=` (today) | same (procps) |
| RSS, tree, uid, start | `ps -axo pid=,ppid=,uid=,rss=,lstart=` (`LC_ALL=C`), one call per listing | same |
| Identity re-read | `ps -o uid=,stat=,lstart=,command= -p <pid>` | same, plus a pidfd held across it |
| Signal | `os.kill` | `signal.pidfd_send_signal` (Python ≥ 3.9, kernel ≥ 5.3), `os.kill` if pidfd is unavailable |
| Attached | tmux `session_attached` (Eyrie's server; your own server when the host is tmux) | same |
| Context | usage index (`usage.db`), last top-level row per (tool, session) | same |

No new dependencies.

## 10. Testing plan

Backend (pytest; the conftest guards gain a **signal guard**: the low-level kill refuses any pid a test didn't spawn):
- Validation: unlisted pid, listed pid of another tool or tty, other uid, start-time mismatch (pid reuse), zombie, pid 1 / Eyrie's own pid, bad tty/started formats, `force` flag carried into the argv (`-KILL`) and the signal.
- Signal sequencing with a **real throwaway child** the test spawns (`exec -a claude sleep 60`): SIGTERM → exits → `exited`; a child that traps TERM → `still_running`; then `force` → exited; already-exited before the signal; orphaned grandchild reported but not signalled.
- Idle computation: threshold boundaries, unknown activity, approximate activity, `idle_requires_detached` with attached / unknown, Eyrie sessions via conversation vs tmux output.
- Context hint: Claude 5 min vs 1 h TTL, Codex, Gemini omitted, below threshold, missing usage rows, approximate conversation → omitted.
- Threshold config from eyrie.toml and Settings (write + range).
- Snooze persistence: snooze, dismiss, return after new activity, expiry, pruning, bad keys, corrupt file.
- RSS / children parsing from fixture `ps` output (macOS and procps spacing, `lstart` with single-digit days).
- API schema (`make types-check`), summary `suggestions`.

Journeys (`make journeys`): "Review idle sessions and stop one": the e2e backend spawns a throwaway process dressed as `claude` and lists it (with the fake ones) as an idle external session; the journey opens the Suggestions card, the Idle filter, the confirm dialog with the resume command, stops it, and checks the process is gone. The fake pids in the list can never be signalled (serve.py's signal guard).

Manual: macOS and Ubuntu, a real `claude` in Terminal/iTerm and in a tmux pane, stop and resume; Codex ignoring SIGTERM mid-turn → Force.

## 11. Delivery

1. This design.
2. Prototype (`prototype/stop-and-idle.html`): Suggestions card, Sessions Idle filter and stop flow, confirm dialog, Stop all idle checklist, widget line, every §6.4 state.
3. Code: process stats and identity (`sessions/procs.py`), idle and suggestions (`sessions/idle.py`), the action, snooze router, schema, pages, widget panel, tests, journey.

## 12. Open questions

1. Orphaned children: offer to stop them too (each listed, same checks)? Default: report only.
2. Codex cache lifetime: 24 h is the conservative upper bound; if Codex never asks for extended retention the real figure is under an hour, and the hint could show sooner.
3. Gemini CLI: show the context size without the cache wording?
4. Stop all idle runs stops one after another (up to 5 s each when a session lingers). Run them in parallel?
5. Should a snoozed session still show its badge in the Idle filter (default: yes, grey), or be hidden there?
6. External sessions in your own tmux: read `session_attached` from your server so `idle_requires_detached` can apply to them too? (Not done: it means running your tmux on every listing.)
