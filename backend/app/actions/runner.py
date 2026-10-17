"""Runs the claude / codex CLIs on Eyrie's behalf.

Always an argv list with shell=False, so no argument is ever interpreted by a shell;
stdin is closed so a CLI can never block waiting on a prompt. Calls are serialised
because both CLIs rewrite whole config files.
"""
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings

_lock = threading.Lock()
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
        configured = {"claude": self.settings.cli.claude_bin, "codex": self.settings.cli.codex_bin,
                      "tmux": self.settings.cli.tmux_bin}[tool]
        found = configured or shutil.which(tool)
        if not found:
            raise CliNotFound(f"`{tool}` CLI not found on PATH; set cli.{tool}_bin in eyrie.toml")
        return found

    def run(self, tool: str, args: list[str], cwd: Path | None = None) -> RunResult:
        argv = [self.binary(tool), *args]
        env = {**os.environ, **self.settings.cli.env}
        started = time.perf_counter()
        with _lock:
            try:
                p = subprocess.run(
                    argv, cwd=cwd or self.settings.paths.data_dir, env=env, stdin=subprocess.DEVNULL,
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
