"""Claude Code and Codex sessions running outside Eyrie (in your own terminals).

Read-only: `ps` for the processes, `lsof` (macOS) or /proc (Linux) for each one's working
directory, and the tools' own transcripts / thread DB for when it was last active. An
interactive session is a `claude` or `codex` process with a terminal; their helper processes
(daemons, background pty hosts, app servers) are skipped. Sessions Eyrie started itself are
excluded here because they're listed (and controllable) as Eyrie sessions.

Only the tool and a resume target are taken from each command line: arguments can contain a
prompt, and Eyrie doesn't read or show those.
"""
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings

TOOLS = {"claude", "codex"}
# First argument of helper processes that aren't interactive sessions.
HELPERS = {"daemon", "bg-pty-host", "bg-spare", "app-server", "mcp", "mcp-server", "exec-server", "login",
           "logout", "plugin", "--version", "-v", "doctor", "update", "install", "proto", "code-mode-host"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _etime_seconds(v: str) -> int:
    """ps etime: [[dd-]hh:]mm:ss"""
    days, _, rest = v.partition("-") if "-" in v else ("0", "", v)
    parts = [int(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return int(days) * 86400 + h * 3600 + m * 60 + s


def parse_ps(output: str) -> list[dict]:
    """Rows of `ps -axo pid=,tty=,etime=,command=` → interactive claude/codex sessions."""
    found = []
    for line in output.splitlines():
        cols = line.split(None, 3)
        if len(cols) < 4:
            continue
        pid, tty, etime, command = cols
        if tty in ("?", "??", "-"):
            continue  # no terminal: a daemon or helper
        args = command.split()
        tool = os.path.basename(args[0])
        if tool not in TOOLS or (len(args) > 1 and args[1] in HELPERS):
            continue
        resume = None
        for flag in ("--resume", "-r", "resume"):
            if flag in args[1:]:
                i = args.index(flag, 1)
                target = args[i + 1] if i + 1 < len(args) else None
                if target and (UUID_RE.match(target) or (NAME_RE.match(target) and not target.startswith("-"))):
                    resume = target
                break
        try:
            found.append({"pid": int(pid), "tool": tool, "tty": tty, "age_seconds": _etime_seconds(etime), "resume": resume})
        except ValueError:
            continue
    return found


def _ps() -> str:
    try:
        return subprocess.run(["ps", "-axo", "pid=,tty=,etime=,command="], capture_output=True, text=True,
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


def transcript_dir(claude_home: Path, cwd: str) -> Path:
    # Claude Code keeps a project's transcripts under its path with non-alphanumerics as "-".
    return claude_home / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)


class ExternalSessions:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cwd_cache: dict[int, str] = {}

    def list(self, exclude_pids: set[int] = frozenset()) -> list[dict]:
        now = datetime.now(timezone.utc)
        procs = [p for p in parse_ps(_ps()) if p["pid"] not in exclude_pids]
        missing = [p["pid"] for p in procs if p["pid"] not in self._cwd_cache]
        self._cwd_cache.update(_cwds(missing))
        live = {p["pid"] for p in procs}
        self._cwd_cache = {k: v for k, v in self._cwd_cache.items() if k in live}
        codex_last = self._codex_activity()
        out = []
        for p in procs:
            cwd = self._cwd_cache.get(p["pid"])
            if p["tool"] == "claude":
                last, exact = self._claude_activity(cwd, p["resume"])
            else:
                last, exact = codex_last.get(cwd or ""), False
            out.append({
                "pid": p["pid"],
                "tool": p["tool"],
                "tty": p["tty"],
                "cwd": cwd,
                "resume": p["resume"],
                "started": (now - timedelta(seconds=p["age_seconds"])).isoformat(timespec="seconds"),
                "last_activity": last.isoformat(timespec="seconds") if last else None,
                "idle_minutes": int((now - last).total_seconds() // 60) if last else None,
                # True when tied to this exact conversation (resumed by id); otherwise it's the
                # newest activity of the same tool in the same directory.
                "activity_exact": exact,
            })
        out.sort(key=lambda s: s["last_activity"] or s["started"], reverse=True)
        return out

    def _claude_activity(self, cwd: str | None, resume: str | None) -> tuple[datetime | None, bool]:
        if not cwd:
            return None, False
        d = transcript_dir(self.settings.paths.claude_home, cwd)
        exact = d / f"{resume}.jsonl" if resume and UUID_RE.match(resume) else None
        if exact and exact.exists():
            return datetime.fromtimestamp(exact.stat().st_mtime, tz=timezone.utc), True
        mtimes = [f.stat().st_mtime for f in d.glob("*.jsonl")] if d.is_dir() else []
        return (datetime.fromtimestamp(max(mtimes), tz=timezone.utc) if mtimes else None), False

    def _codex_activity(self) -> dict[str, datetime]:
        db = self.settings.paths.codex_home / "state_5.sqlite"
        if not db.exists():
            return {}
        try:
            with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                rows = con.execute("SELECT cwd, max(updated_at) FROM threads GROUP BY cwd").fetchall()
        except sqlite3.Error:
            return {}
        return {cwd: datetime.fromtimestamp(ts, tz=timezone.utc) for cwd, ts in rows if cwd and ts}
