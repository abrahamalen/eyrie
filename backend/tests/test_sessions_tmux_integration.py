"""Real tmux on a throwaway socket, with a stand-in `claude` script: checks Eyrie's
argv, @eyrie_* tags, listing, capture and kill against tmux itself."""
import json
import shutil
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.actions import runner
from app.config import Cli, Sessions
from app.main import create_app
from tests.conftest import REAL_BINARY, REAL_RUN

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")


@pytest.fixture
def real(settings, home, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.Runner, "run", REAL_RUN)
    monkeypatch.setattr(runner.Runner, "binary", REAL_BINARY)
    fake_claude = tmp_path / "claude"
    fake_claude.write_text('#!/bin/sh\necho "fake claude args: $*"\necho "cwd: $(pwd)"\nread line\necho "got: $line"\n')
    fake_claude.chmod(0o755)
    proj = home / "proj"
    proj.mkdir()
    cj = json.loads((home / ".claude.json").read_text())
    cj["projects"][str(proj)] = {}
    (home / ".claude.json").write_text(json.dumps(cj))
    socket = f"eyrie-test-{uuid.uuid4().hex[:8]}"
    s = settings.model_copy(update={"cli": Cli(claude_bin=str(fake_claude)), "sessions": Sessions(socket=socket)})
    app = create_app(s)
    c = TestClient(app, base_url="http://localhost", headers={"X-Eyrie-Token": app.state.token})
    yield c, proj, socket
    import os
    import subprocess
    from pathlib import Path
    subprocess.run(["tmux", "-L", socket, "kill-server"], capture_output=True)
    sock = Path(os.environ.get("TMUX_TMPDIR", "/tmp")) / f"tmux-{os.getuid()}" / socket
    sock.unlink(missing_ok=True)


def wait_for(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    return fn()


def test_real_tmux_lifecycle(real):
    c, proj, socket = real
    conv = str(uuid.uuid4())
    r = c.post("/api/v1/actions/sessions.start", json={"params": {
        "tool": "claude", "cwd": str(proj), "name": "eyrie-itest", "conversation_id": conv}}).json()
    assert r["ok"], r
    s = c.get("/api/v1/sources/sessions").json()["sessions"]
    assert [(x["name"], x["tool"], x["cwd"], x["conversation_id"], x["alive"]) for x in s] == [
        ("eyrie-itest", "claude", str(proj), conv, True)]
    assert s[0]["attach"] == f"tmux -L {socket} attach -t eyrie-itest"
    screen = wait_for(lambda: (t := c.get("/api/v1/sessions/eyrie-itest/screen").json()["text"]) and "cwd:" in t and t)
    assert f"fake claude args: --session-id {conv}" in screen and f"cwd: {proj.resolve()}" in screen
    # The process exits: the session stays (remain-on-exit) and reports its exit status.
    import subprocess
    subprocess.run(["tmux", "-L", socket, "send-keys", "-t", "eyrie-itest", "hello", "Enter"], check=True)
    # tmux can mark the pane dead a moment before it records the exit status, so wait for both.
    s = wait_for(lambda: (x := c.get("/api/v1/sources/sessions").json()["sessions"][0])
                 and not x["alive"] and x["exit_status"] is not None and x)
    assert s, "session never reported an exit status"
    assert s["exit_status"] == 0 and "got: hello" in c.get("/api/v1/sessions/eyrie-itest/screen").json()["text"]
    r = c.post("/api/v1/actions/sessions.stop", json={"params": {"name": "eyrie-itest"}, "confirm": True}).json()
    assert r["ok"], r
    assert c.get("/api/v1/sources/sessions").json()["sessions"] == []


def test_real_tmux_keeps_arguments_literal(real):
    c, proj, socket = real
    # A directory name with shell metacharacters must reach the process untouched.
    weird = proj / "a;b $HOME"
    weird.mkdir()
    cj_path = c.app.state.settings.paths.claude_json
    cj = json.loads(cj_path.read_text())
    cj["projects"][str(weird)] = {}
    cj_path.write_text(json.dumps(cj))
    r = c.post("/api/v1/actions/sessions.start", json={"params": {"tool": "claude", "cwd": str(weird), "name": "eyrie-lit1"}}).json()
    assert r["ok"], r
    screen = wait_for(lambda: (t := c.get("/api/v1/sessions/eyrie-lit1/screen").json()["text"]) and "cwd:" in t and t)
    assert "a;b $HOME" in screen
