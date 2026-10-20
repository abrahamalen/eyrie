"""Browser terminal against real tmux on a throwaway socket, with a stand-in program."""
import json
import re
import shutil
import subprocess
import time

import pytest

from tests.test_sessions_tmux_integration import real  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")


def start(c, proj, name):
    r = c.post("/api/v1/actions/sessions.start", json={"params": {"tool": "claude", "cwd": str(proj), "name": name}}).json()
    assert r["ok"], r


CSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")


def screen_text(buf: bytes) -> bytes:
    """What the terminal shows, roughly: tmux redraws can move the cursor instead of writing
    spaces (so "a b" may arrive as "a<ESC>[1Cb"), so match on text with escapes as spaces."""
    return re.sub(rb"\s+", b" ", CSI.sub(b" ", buf))


# Wait on the program's *last* startup line: if tmux has to shrink the window from Eyrie's
# initial 80x24 to a smaller client, the first line isn't always in the redrawn region.
def read_until(ws, needle, timeout=4.0):
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        buf += ws.receive_bytes()
        if needle in screen_text(buf):
            return buf
    raise AssertionError(f"{needle!r} not seen; screen: {screen_text(buf)[-700:]!r}")


def proto(c):
    return ["eyrie", f"eyrie.token.{c.app.state.token}"]


def test_type_into_session_and_detach_keeps_it_running(real):  # noqa: F811
    c, proj, socket = real
    start(c, proj, "eyrie-term1")
    with c.websocket_connect("ws://localhost/api/v1/sessions/eyrie-term1/term", subprotocols=proto(c)) as ws:
        assert ws.accepted_subprotocol == "eyrie"
        read_until(ws, b"cwd:")
        ws.send_bytes(b"hello from the browser\r")
        read_until(ws, b"got: hello from the browser")
    time.sleep(0.3)
    s = c.get("/api/v1/sources/sessions").json()["sessions"][0]
    # The stand-in exits after one line, so the session shows exited; it still exists.
    assert s["name"] == "eyrie-term1"
    entry = c.get("/api/v1/audit").json()[0]
    assert entry["action"] == "sessions.attach" and entry["params"] == {"name": "eyrie-term1", "readonly": False}


def test_readonly_ignores_input(real):  # noqa: F811
    c, proj, socket = real
    start(c, proj, "eyrie-term2")
    with c.websocket_connect("ws://localhost/api/v1/sessions/eyrie-term2/term?readonly=true", subprotocols=proto(c)) as ws:
        read_until(ws, b"cwd:")
        ws.send_bytes(b"should not arrive\r")
        time.sleep(0.5)
    screen = c.get("/api/v1/sessions/eyrie-term2/screen").json()["text"]
    assert "should not arrive" not in screen
    assert c.get("/api/v1/sources/sessions").json()["sessions"][0]["alive"] is True


def test_attach_at_the_browser_size_keeps_the_first_line(real):  # noqa: F811
    c, proj, socket = real
    start(c, proj, "eyrie-term5")
    time.sleep(0.3)  # let the program print before anyone attaches
    with c.websocket_connect("ws://localhost/api/v1/sessions/eyrie-term5/term?cols=100&rows=30", subprotocols=proto(c)) as ws:
        buf = read_until(ws, b"cwd:")
        assert b"fake claude args" in screen_text(buf)
        size = subprocess.run(["tmux", "-L", socket, "display-message", "-p", "-t", "eyrie-term5",
                               "#{window_width}x#{window_height}"], capture_output=True, text=True).stdout.strip()
        assert size == "100x29", size  # 30 rows less the status line


def test_resize_reaches_tmux(real):  # noqa: F811
    c, proj, socket = real
    start(c, proj, "eyrie-term3")
    with c.websocket_connect("ws://localhost/api/v1/sessions/eyrie-term3/term", subprotocols=proto(c)) as ws:
        read_until(ws, b"cwd:")
        ws.send_text(json.dumps({"type": "resize", "cols": 97, "rows": 29}))
        size = ""
        for _ in range(30):
            time.sleep(0.1)
            size = subprocess.run(["tmux", "-L", socket, "display-message", "-p", "-t", "eyrie-term3",
                                   "#{window_width}x#{window_height}"], capture_output=True, text=True).stdout.strip()
            if size.startswith("97x"):
                break
        assert size.startswith("97x"), size


def test_session_kill_closes_terminal(real):  # noqa: F811
    c, proj, socket = real
    start(c, proj, "eyrie-term4")
    with c.websocket_connect("ws://localhost/api/v1/sessions/eyrie-term4/term", subprotocols=proto(c)) as ws:
        read_until(ws, b"cwd:")
        subprocess.run(["tmux", "-L", socket, "kill-session", "-t", "eyrie-term4"], check=True)
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            for _ in range(200):
                ws.receive_bytes()
