"""Sessions of the known tools running outside Eyrie (in your own terminals).

Read-only: `ps` for the processes, `lsof` (macOS) or /proc (Linux) for each one's working
directory, and each tool's adapter for when it was last active. An interactive session is
a tool's process with a terminal; its helper processes (each adapter lists them: daemons,
background pty hosts, app servers) are skipped. Sessions Eyrie started itself are
excluded here because they're listed (and controllable) as Eyrie sessions.

Only the tool and a resume target are taken from each command line: arguments can contain a
prompt, and Eyrie doesn't read or show those. The parent processes are classified (which
terminal hosts the session: sessions/focus.py) and only the classification is kept.
"""
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.config import Settings
from app.sessions import focus
from app.sessions.names import display
from app.tools import TOOLS, enabled

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUNTIMES = {"node", "bun", "deno"}


def _etime_seconds(v: str) -> int:
    """ps etime: [[dd-]hh:]mm:ss"""
    days, _, rest = v.partition("-") if "-" in v else ("0", "", v)
    parts = [int(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return int(days) * 86400 + h * 3600 + m * 60 + s


def _rows(output: str):
    """`ps -axo pid=,ppid=,tty=,etime=,command=` rows (ppid optional) → (pid, ppid, tty, etime, command)."""
    for line in output.splitlines():
        cols = line.split(None, 4)
        if len(cols) == 5 and cols[0].isdigit() and cols[1].isdigit():
            yield cols[0], int(cols[1]), cols[2], cols[3], cols[4]
        elif len(cols) >= 4:
            cols = line.split(None, 3)
            yield cols[0], 0, cols[1], cols[2], cols[3]


def process_table(output: str) -> dict[int, tuple[int, str]]:
    """pid → (ppid, command), to find which terminal a session runs in."""
    return {int(pid): (ppid, command) for pid, ppid, _, _, command in _rows(output) if pid.isdigit()}


def parse_ps(output: str, tools=None) -> list[dict]:
    """Rows of `ps -axo pid=,ppid=,tty=,etime=,command=` → interactive sessions of the known tools."""
    found = []
    for pid, _, tty, etime, command in _rows(output):
        if tty in ("?", "??", "-"):
            continue  # no terminal: a daemon or helper
        args = command.split()
        # Node-based CLIs (Gemini) show up as `node /path/to/gemini …`.
        if os.path.basename(args[0]) in RUNTIMES and len(args) > 1:
            args = args[1:]
        tool = next((t for t in (tools or TOOLS).values() if t.sessions and os.path.basename(args[0]) == t.binary), None)
        if tool is None or (len(args) > 1 and args[1] in tool.sessions.helpers):
            continue
        resume = None
        # `claude attach <id>` is a terminal on a background session: the id is its target too.
        for flag in ("--resume", "-r", "resume", "attach"):
            if flag in args[1:] and (flag != "attach" or args[1] == "attach"):
                i = args.index(flag, 1)
                target = args[i + 1] if i + 1 < len(args) else None
                if target and (UUID_RE.match(target) or (NAME_RE.match(target) and not target.startswith("-"))):
                    resume = target
                break
        try:
            found.append({"pid": int(pid), "tool": tool.id, "tty": tty, "age_seconds": _etime_seconds(etime), "resume": resume})
        except ValueError:
            continue
    return found


def _ps() -> str:
    try:
        return subprocess.run(["ps", "-axo", "pid=,ppid=,tty=,etime=,command="], capture_output=True, text=True,
                              timeout=5, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _cwds(pids: list[int]) -> dict[int, str]:
    if not pids:
        return {}
    if sys.platform.startswith("linux"):
        out = {}
        for pid in pids:
            try:
                out[pid] = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                pass
        return out
    try:
        res = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", ",".join(map(str, pids)), "-Fpn"],
                             capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out, current = {}, None
    for line in res.splitlines():
        if line.startswith("p"):
            current = int(line[1:])
        elif line.startswith("n") and current is not None:
            out[current] = line[1:]
    return out


def session_href(pid: int, tool: str, conversation_id: str | None) -> str:
    """The app's link to an external session; tool + id let the page offer the resume command
    if it has ended by the time the link is opened."""
    q = {"ext": pid, "tool": tool, **({"id": conversation_id} if conversation_id else {})}
    return "/sessions?" + urlencode(q)


class ExternalSessions:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cwd_cache: dict[int, str] = {}
        # From the latest listing: each session's host, and the process table (for tmux clients).
        self.hosts: dict[int, focus.Host] = {}
        self.table: dict[int, tuple[int, str]] = {}

    def find(self, pid: int, tty: str, exclude_pids: set[int] = frozenset()) -> dict | None:
        """A fresh listing's session with this pid on this tty, or None."""
        return next((s for s in self.list(exclude_pids) if s["pid"] == pid and s["tty"] == tty), None)

    def list(self, exclude_pids: set[int] = frozenset()) -> list[dict]:
        now = datetime.now(timezone.utc)
        ps = _ps()
        self.table = process_table(ps)
        procs = [p for p in parse_ps(ps, enabled(self.settings)) if p["pid"] not in exclude_pids]
        missing = [p["pid"] for p in procs if p["pid"] not in self._cwd_cache]
        self._cwd_cache.update(_cwds(missing))
        live = {p["pid"] for p in procs}
        self._cwd_cache = {k: v for k, v in self._cwd_cache.items() if k in live}
        tools = {p["tool"] for p in procs}
        lookups = {t: TOOLS[t].sessions.activity(self.settings) for t in tools}
        namers = {t: TOOLS[t].sessions.names(self.settings) for t in tools}
        hosts = {}
        out = []
        for p in procs:
            cwd = self._cwd_cache.get(p["pid"])
            started = now - timedelta(seconds=p["age_seconds"])
            n = namers[p["tool"]](p["pid"], cwd, None, p["resume"], started)
            # Once the conversation is known (Claude's pid file), its activity is exact too.
            last, exact = lookups[p["tool"]](cwd, n.conversation_id if n.exact and n.conversation_id else p["resume"])
            name, source = display(n, f"{TOOLS[p['tool']].title} · {p['tty']}")
            host = hosts[p["pid"]] = focus.detect(self.table, p["pid"])
            out.append({
                "pid": p["pid"],
                "tool": p["tool"],
                "tty": p["tty"],
                "cwd": cwd,
                "resume": p["resume"],
                "started": started.isoformat(timespec="seconds"),
                "last_activity": last.isoformat(timespec="seconds") if last else None,
                "idle_minutes": int((now - last).total_seconds() // 60) if last else None,
                # True when tied to this exact conversation (resumed by id); otherwise it's the
                # newest activity of the same tool in the same directory.
                "activity_exact": exact,
                "conversation_id": n.conversation_id,
                "display_name": name,
                "name_source": source,
                "name_exact": n.exact,
                "terminal": host.label if host is not focus.UNKNOWN else None,
                "focus": host.focus if focus.TTY_RE.match(p["tty"]) else "none",
                "href": session_href(p["pid"], p["tool"], n.conversation_id if n.exact else None),
            })
        self.hosts = hosts
        # A guess shared by two processes (several sessions in one directory) is no guess at all.
        guesses = Counter((s["tool"], s["conversation_id"]) for s in out if not s["name_exact"])
        for s in out:
            if not s["name_exact"] and guesses[(s["tool"], s["conversation_id"])] > 1:
                s.update(conversation_id=None, display_name=f"{TOOLS[s['tool']].title} · {s['tty']}",
                         name_source="none", name_exact=True)
        out.sort(key=lambda s: s["last_activity"] or s["started"], reverse=True)
        return out
