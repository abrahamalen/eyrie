"""Browser terminal: a `tmux attach` client in a pty, bridged to a WebSocket.

Output is sent as binary frames; input arrives as binary frames (raw keystrokes) and
control messages as JSON text frames ({"type": "resize", "cols": N, "rows": N}).
Closing the socket only detaches this client: the tmux session keeps running.
"""
import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import termios

from starlette.websockets import WebSocket

from app.config import Settings
from app.sessions.tmux import base_args

MAX_TERMINALS = 8
_open = 0


class TooManyTerminals(Exception):
    pass


def _set_size(fd: int, cols: int, rows: int) -> None:
    cols, rows = max(20, min(cols, 500)), max(5, min(rows, 200))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            view = view[os.write(fd, view):]
        except BlockingIOError:
            # pty buffer full (a big paste); the reader on the other side drains it quickly
            import time
            time.sleep(0.005)


async def bridge(ws: WebSocket, settings: Settings, tmux_bin: str, name: str, readonly: bool,
                 size: tuple[int, int] = (120, 32)) -> str:
    """Runs until either side closes. Returns why it ended."""
    global _open
    if _open >= MAX_TERMINALS:
        raise TooManyTerminals()
    argv = [tmux_bin, *base_args(settings), "attach-session", "-t", name, *(["-r"] if readonly else [])]
    env = {**os.environ, **settings.cli.env, "TERM": "xterm-256color"}
    env.pop("TMUX", None)  # in case Eyrie itself was started inside tmux
    master, slave = pty.openpty()
    _set_size(master, *size)
    try:
        proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, env=env,
                                start_new_session=True, close_fds=True)
    except OSError:
        os.close(master)
        raise
    finally:
        os.close(slave)
    _open += 1
    os.set_blocking(master, False)
    loop = asyncio.get_running_loop()
    output: asyncio.Queue[bytes] = asyncio.Queue()

    def readable() -> None:
        try:
            data = os.read(master, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        output.put_nowait(data)
        if not data:
            loop.remove_reader(master)

    loop.add_reader(master, readable)

    async def to_browser() -> str:
        while True:
            data = await output.get()
            if not data:
                return "session ended or detached"
            await ws.send_bytes(data)

    async def from_browser() -> str:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return "browser disconnected"
            if msg.get("bytes") is not None:
                if not readonly:
                    _write_all(master, msg["bytes"])
            elif msg.get("text"):
                try:
                    ctl = json.loads(msg["text"])
                except ValueError:
                    continue
                if ctl.get("type") == "resize":
                    _set_size(master, int(ctl.get("cols", 120)), int(ctl.get("rows", 32)))
                    # The pty isn't the client's controlling terminal (new session, no
                    # TIOCSCTTY), so the kernel won't deliver SIGWINCH; send it ourselves.
                    if proc.poll() is None:
                        os.kill(proc.pid, signal.SIGWINCH)

    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(from_browser())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        reason = next(iter(done)).result()
    except Exception as e:  # a send/receive on a closing socket
        reason = f"connection error: {e}"
        for t in tasks:
            t.cancel()
    finally:
        try:
            loop.remove_reader(master)
        except Exception:
            pass
        if proc.poll() is None:
            # Ends only this tmux client; the session itself keeps running.
            os.killpg(proc.pid, signal.SIGHUP)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        os.close(master)
        _open -= 1
    return reason
