"""Run the backend for the journey suite: the real app, except that "sessions running in your
own terminals" come from a fixed list instead of this machine's `ps`, so the recording never
shows (or depends on) whatever the person running the suite has open.

    HOME=<root>/home backend/.venv/bin/python frontend/e2e/env/serve.py <port>
"""
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from app.main import create_app  # noqa: E402
from app.sessions import external  # noqa: E402

PROJECTS = Path.home() / "projects"
FAKE_PS = (
    "90001 ttys009 02:13:45 claude --resume 2b6f0d1e-5a4c-4e8b-9f21-0c3d4e5f6a7b\n"
    "90002 ttys011 41:07 codex\n"
)
FAKE_CWDS = {90001: str(PROJECTS / "eyrie"), 90002: str(PROJECTS / "atlas")}

external._ps = lambda: FAKE_PS
external._cwds = lambda pids: {p: FAKE_CWDS[p] for p in pids if p in FAKE_CWDS}

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
