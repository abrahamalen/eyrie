"""Run the backend for the journey suite: the real app, except that "sessions running in your
own terminals" come from a fixed list instead of this machine's `ps`, so the recording never
shows (or depends on) whatever the person running the suite has open.

    HOME=<root>/home backend/.venv/bin/python frontend/e2e/env/serve.py <port>

The idle-sessions journey starts one real throwaway process (`sleep`, named `claude`) and
writes its pid to <root>/idle-session.pid; it's listed as an idle external session and is
the only process this backend may ever signal. The fixed fake pids can't be signalled at all.
"""
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from app.main import create_app  # noqa: E402
from app.sessions import external, procs  # noqa: E402

PROJECTS = Path.home() / "projects"
IDLE_PID_FILE = Path.home().parent / "idle-session.pid"
IDLE_CONV = "7d3c2b1a-0f9e-4d8c-b7a6-5f4e3d2c1b0a"  # seeded in seed.py, last active 3 days ago
FAKE_PS = (
    "90001 ttys009 02:13:45 claude --resume 2b6f0d1e-5a4c-4e8b-9f21-0c3d4e5f6a7b\n"
    "90002 ttys011 41:07 codex\n"
)
FAKE_CWDS = {90001: str(PROJECTS / "eyrie"), 90002: str(PROJECTS / "atlas")}
# uid, RSS and a fixed start time for the fake pids (never a real process's).
FAKE_STATS = (f"90001 1 {os.getuid()} 412000 Sat Oct 17 21:03:44 2026\n"
              f"90003 90001 {os.getuid()} 51000 Sat Oct 17 21:03:46 2026\n"
              f"90002 1 {os.getuid()} 180000 Mon Oct 19 10:00:00 2026\n")
REAL_STATS, REAL_READ_ONE, REAL_KILL = procs._stats, procs._read_one, procs._kill


def idle_pid() -> int | None:
    """The journey's throwaway process, while it's running (listed like a real session is)."""
    try:
        pid = int(IDLE_PID_FILE.read_text().strip())
        os.kill(pid, 0)  # signal 0 only checks it exists
    except (OSError, ValueError):
        return None
    return pid


def fake_ps() -> str:
    pid = idle_pid()
    extra = f"{pid} ttys012 3-02:00:00 claude --resume {IDLE_CONV}\n" if pid else ""
    return FAKE_PS + extra


def fake_cwds(pids):
    cwds = {**FAKE_CWDS, **({idle_pid(): str(PROJECTS / "eyrie")} if idle_pid() else {})}
    return {p: cwds[p] for p in pids if p in cwds}


def fake_stats() -> str:
    pid = idle_pid()
    real = [line for line in REAL_STATS().splitlines() if pid and line.split()[:1] == [str(pid)]]
    return FAKE_STATS + "".join(line + "\n" for line in real)


def read_one(pid: int) -> str:
    return REAL_READ_ONE(pid) if pid == idle_pid() else ""


def kill(pid, sig, pidfd=None):
    if pid != idle_pid():
        raise PermissionError(f"the journey backend only signals its throwaway process, not {pid}")
    return REAL_KILL(pid, sig, pidfd)


external._ps = fake_ps
external._cwds = fake_cwds
procs._stats = fake_stats
procs._read_one = read_one
procs._kill = kill

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
