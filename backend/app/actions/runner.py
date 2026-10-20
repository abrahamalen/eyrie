"""Runs the claude / codex CLIs on Eyrie's behalf.

Always an argv list with shell=False, so no argument is ever interpreted by a shell;
stdin is closed so a CLI can never block waiting on a prompt. Calls to the same CLI are
serialised because claude and codex each rewrite whole config files; different CLIs, and
tmux (whose server serialises commands itself), don't wait on each other, so a slow
`claude mcp add` can't stall the session list or the summary.
"""
import contextlib
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings

_locks = {"claude": threading.Lock(), "codex": threading.Lock()}
TAIL = 4000


class CliNotFound(Exception):
    pass


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Runner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def binary(self, tool: str) -> str:
        from app.tools import TOOLS

        configured = getattr(self.settings.cli, f"{tool}_bin", None)
        found = configured or shutil.which(TOOLS[tool].binary if tool in TOOLS else tool)
        if not found:
            raise CliNotFound(f"`{tool}` CLI not found on PATH; set cli.{tool}_bin in eyrie.toml")
        return found

    def run(self, tool: str, args: list[str], cwd: Path | None = None) -> RunResult:
        argv = [self.binary(tool), *args]
        env = {**os.environ, **self.settings.cli.env}
        if cwd is None:
            cwd = self.settings.paths.data_dir
            cwd.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        with _locks.get(tool) or contextlib.nullcontext():
            try:
                p = subprocess.run(
                    argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=self.settings.cli.timeout_s, shell=False,
                )
                code, out, err = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as e:
                code, out, err = -1, _text(e.stdout), f"Timed out after {self.settings.cli.timeout_s:.0f}s"
        return RunResult(code, out[-TAIL:], err[-TAIL:], (time.perf_counter() - started) * 1000)


def _text(v: str | bytes | None) -> str:
    if isinstance(v, bytes):
        return v.decode(errors="replace")
    return v or ""
