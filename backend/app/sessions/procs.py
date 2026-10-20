"""What a session costs to keep (RSS of its process tree, child processes), and stopping one
external session safely (docs/stop-and-idle.md §3.2, §4).

Read-only inspection is `ps` on macOS and Linux alike. The only thing here that changes
anything is `stop()`: one signal to one pid, after re-checking that the pid is still the
process you were shown (same uid, same start time, still that tool). Never a process group.
"""
import os
import select
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

# `ps` prints dates in the C locale's format with LC_ALL=C, the same on macOS and procps.
PS_ENV = {**os.environ, "LC_ALL": "C"}
LSTART = "%a %b %d %H:%M:%S %Y"


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    uid: int
    rss_kb: int
    started: int | None  # epoch seconds (ps lstart)


@dataclass(frozen=True)
class Identity:
    uid: int
    started: int | None
    state: str      # ps stat: Z is a zombie (exited, not yet reaped)
    command: str    # only matched against the tool's binary, never shown or stored


def _lstart(tokens: list[str]) -> int | None:
    try:
        return int(datetime.strptime(" ".join(tokens), LSTART).timestamp())
    except ValueError:
        return None


def _run_ps(args: list[str]) -> str:
    try:
        return subprocess.run(["ps", *args], capture_output=True, text=True, timeout=5,
                              stdin=subprocess.DEVNULL, env=PS_ENV).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _stats() -> str:
    return _run_ps(["-axo", "pid=,ppid=,uid=,rss=,lstart="])


def parse_stats(output: str) -> dict[int, Proc]:
    """`ps -axo pid=,ppid=,uid=,rss=,lstart=` → pid → Proc. lstart is five words."""
    out = {}
    for line in output.splitlines():
        cols = line.split()
        if len(cols) < 4 or not all(c.isdigit() for c in cols[:4]):
            continue
        pid, ppid, uid, rss = map(int, cols[:4])
        out[pid] = Proc(pid, ppid, uid, rss, _lstart(cols[4:9]) if len(cols) >= 9 else None)
    return out


def stats() -> dict[int, Proc]:
    return parse_stats(_stats())


def descendants(table: dict[int, Proc], pid: int) -> list[int]:
    """Every process below `pid` in the snapshot (children, their children, …)."""
    children: dict[int, list[int]] = {}
    for p in table.values():
        children.setdefault(p.ppid, []).append(p.pid)
    out, todo, seen = [], list(children.get(pid, [])), {pid}
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
        todo.extend(children.get(c, []))
    return sorted(out)


def resources(table: dict[int, Proc], pid: int | None) -> dict:
    """RSS of the process and all its descendants (an upper bound: shared pages count in
    each), and how many descendants there are."""
    if pid is None or pid not in table:
        return {"rss_bytes": None, "child_processes": None}
    kids = descendants(table, pid)
    rss = sum(table[p].rss_kb for p in (pid, *kids))
    return {"rss_bytes": rss * 1024, "child_processes": len(kids)}


def _read_one(pid: int) -> str:
    return _run_ps(["-o", "uid=,stat=,lstart=,command=", "-p", str(pid)])


def parse_identity(output: str) -> Identity | None:
    """`ps -o uid=,stat=,lstart=,command= -p <pid>` → Identity, or None when there's no such process."""
    for line in output.splitlines():
        cols = line.split(None, 7)
        if len(cols) >= 7 and cols[0].isdigit():
            return Identity(int(cols[0]), _lstart(cols[2:7]), cols[1], cols[7] if len(cols) > 7 else "")
    return None


def identity(pid: int) -> Identity | None:
    return parse_identity(_read_one(pid))


def protected(pid: int) -> bool:
    """Pids Eyrie never signals whatever the request says: init, itself, its parent, and
    anything that isn't a single positive pid (0 and negatives mean process groups)."""
    return not isinstance(pid, int) or pid < 2 or pid in (os.getpid(), os.getppid())


def _kill(pid: int, sig: int, pidfd: int | None = None) -> None:
    """The one place Eyrie sends a signal. Tests replace it with a guard."""
    if protected(pid):
        raise PermissionError(f"refusing to signal pid {pid}")
    if pidfd is not None:
        signal.pidfd_send_signal(pidfd, sig)
    else:
        os.kill(pid, sig)


def _pidfd(pid: int) -> int | None:
    """A handle on this exact process (Linux ≥ 5.3): a signal sent through it can't reach a
    process that reused the pid."""
    if not hasattr(os, "pidfd_open"):
        return None
    try:
        return os.pidfd_open(pid)
    except ProcessLookupError:
        raise
    except OSError:
        return None


@dataclass
class Expect:
    """What the process must still be: the listing's view of it."""
    pid: int
    uid: int
    started: int
    is_tool: Callable[[str], bool]


@dataclass
class Outcome:
    state: str  # exited | still_running | already_exited | reused | denied
    seconds: float = 0.0
    survivors: list[int] = field(default_factory=list)


def check(expect: Expect, ident: Identity | None) -> str | None:
    """None when `ident` is still the expected live process; otherwise why not."""
    if ident is None or ident.state.startswith("Z"):
        return "already_exited"
    if ident.uid != expect.uid or ident.started != expect.started or not expect.is_tool(ident.command):
        return "reused"
    return None


def _alive(expect: Expect, pidfd: int | None) -> bool:
    if pidfd is not None:
        # Readable once the process has exited (zombie or reaped).
        return not select.select([pidfd], [], [], 0)[0]
    return check(expect, identity(expect.pid)) is None


def stop(expect: Expect, sig: int, wait_s: float, children: dict[int, int | None], poll_s: float = 0.2) -> Outcome:
    """Re-verify, signal once, wait for the exit, report. `children` (pid → start) are only
    re-checked afterwards, never signalled."""
    try:
        fd = _pidfd(expect.pid)
    except ProcessLookupError:
        return Outcome("already_exited")
    try:
        problem = check(expect, identity(expect.pid))
        if problem:
            return Outcome(problem)
        started = time.monotonic()
        try:
            _kill(expect.pid, sig, fd)
        except ProcessLookupError:
            return Outcome("already_exited")
        except PermissionError:
            return Outcome("denied")
        while time.monotonic() - started < wait_s:
            if not _alive(expect, fd):
                break
            time.sleep(poll_s)
        elapsed = time.monotonic() - started
        if _alive(expect, fd):
            return Outcome("still_running", elapsed)
        table = stats()
        return Outcome("exited", elapsed, sorted(c for c, st in children.items() if c in table and table[c].started == st))
    finally:
        if fd is not None:
            os.close(fd)
