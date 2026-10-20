"""Eyrie's tmux server: a private socket (-L eyrie) so `list-sessions` only ever shows
Eyrie's sessions and your own tmux is untouched. Sessions survive Eyrie restarts; on boot
they're rediscovered from tmux itself, using the @eyrie_* options set at start.

Commands are always passed to tmux as two or more arguments, so tmux execs them directly;
a single argument would be run through `sh -c`.
"""
import re
from datetime import datetime, timezone
from pathlib import Path

from app.actions.runner import Runner
from app.config import Settings

NAME_RE = re.compile(r"^eyrie-[a-z0-9]{4,16}$")
CONF = """# Written by Eyrie; read when Eyrie's tmux server starts.
set -g remain-on-exit on
set -g history-limit 50000
set -g mouse on
# The default status-right is the pane title, which shows the machine's hostname.
set -g status-left ""
set -g status-right " #{session_name} · %H:%M "
# Windows follow the newest client, so the status line spans the terminal you're looking at.
set -g window-size latest
"""
FIELDS = ["session_name", "@eyrie_tool", "@eyrie_cwd", "@eyrie_mode", "@eyrie_conv", "session_created",
          "session_activity", "session_attached", "pane_dead", "pane_dead_status", "pane_current_command", "pane_pid"]


def conf_path(settings: Settings) -> Path:
    path = settings.paths.data_dir / "tmux.conf"
    if not path.exists() or path.read_text() != CONF:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CONF)
    return path


def base_args(settings: Settings) -> list[str]:
    return ["-L", settings.sessions.socket, "-f", str(conf_path(settings))]


def attach_command(settings: Settings, name: str) -> str:
    return f"tmux -L {settings.sessions.socket} attach -t {name}"


def _ts(v: str) -> str | None:
    return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat() if v.isdigit() else None


class Tmux:
    def __init__(self, settings: Settings, runner: Runner) -> None:
        self.settings = settings
        self.runner = runner

    def _run(self, *args: str):
        return self.runner.run("tmux", [*base_args(self.settings), *args])

    def list(self) -> list[dict]:
        r = self._run("list-sessions", "-F", "\t".join(f"#{{{f}}}" for f in FIELDS))
        if not r.ok:
            return []  # no server yet means no sessions
        out = []
        for line in r.stdout.splitlines():
            v = dict(zip(FIELDS, line.split("\t"), strict=False))
            if not NAME_RE.match(v.get("session_name", "")):
                continue
            dead = v.get("pane_dead") == "1"
            out.append({
                "name": v["session_name"],
                "tool": v.get("@eyrie_tool") or None,
                "cwd": v.get("@eyrie_cwd") or None,
                "mode": v.get("@eyrie_mode") or None,
                "conversation_id": v.get("@eyrie_conv") or None,
                "created": _ts(v.get("session_created", "")),
                "last_output": _ts(v.get("session_activity", "")),
                "attached": int(v.get("session_attached") or 0),
                "alive": not dead,
                "exit_status": int(v["pane_dead_status"]) if dead and v.get("pane_dead_status", "").lstrip("-").isdigit() else None,
                "command": v.get("pane_current_command") or None,
                "attach": attach_command(self.settings, v["session_name"]),
                "pid": int(v["pane_pid"]) if v.get("pane_pid", "").isdigit() else None,
            })
        out.sort(key=lambda s: s["created"] or "", reverse=True)
        return out

    def pane_pids(self) -> set[int]:
        """PIDs of the programs running in Eyrie's sessions (tmux execs them directly)."""
        r = self._run("list-panes", "-a", "-F", "#{pane_pid}")
        return {int(x) for x in r.stdout.split() if x.isdigit()} if r.ok else set()

    def exists(self, name: str) -> bool:
        return any(s["name"] == name for s in self.list())

    def capture(self, name: str, lines: int) -> str | None:
        r = self._run("capture-pane", "-p", "-J", "-t", name, "-S", f"-{lines}")
        return r.stdout.rstrip() if r.ok else None
