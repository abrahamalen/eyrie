from datetime import datetime

from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sessions import idle
from app.sessions.dirs import allowed_dirs
from app.sessions.external import ExternalSessions
from app.sessions.names import display, resume_command
from app.sessions.tmux import Tmux
from app.sources.base import Availability
from app.tools import TOOLS
from app.usage.index import UsageIndex


def name_managed(settings: Settings, sessions: list[dict]) -> list[dict]:
    """Eyrie's sessions with their names (docs/session-names-and-jump.md §3) and when they
    were last active: the tool's own activity for the conversation when it's known, else
    the pane's last output (docs/stop-and-idle.md §3.1)."""
    namers, lookups = {}, {}
    for s in sessions:
        tool = TOOLS.get(s["tool"] or "")
        n = None
        if tool is not None and tool.sessions is not None:
            if tool.id not in namers:
                namers[tool.id] = tool.sessions.names(settings)
                lookups[tool.id] = tool.sessions.activity(settings)
            started = datetime.fromisoformat(s["created"]) if s["created"] else None
            n = namers[tool.id](s.get("pid") if s["alive"] else None, s["cwd"], s["conversation_id"], None, started)
        if n is not None:
            s["display_name"], s["name_source"] = display(n, s["name"])
            s["conversation_id"] = n.conversation_id or s["conversation_id"]
        else:
            s["display_name"], s["name_source"] = s["name"], "none"
        exact = n is None or n.exact
        s["resume_command"] = resume_command(s["tool"], s["cwd"], s["conversation_id"]) if exact else None
        last = None
        if tool is not None and tool.id in lookups and s["conversation_id"]:
            at, conv_exact = lookups[tool.id](s["cwd"], s["conversation_id"])
            last = at.isoformat(timespec="seconds") if at and conv_exact else None
        s["activity_at"] = last or s.get("last_output")
        s["activity_exact"] = True
    return sessions


class SessionsSource:
    id = "sessions"
    title = "Sessions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = Runner(settings)
        self.tmux = Tmux(settings, self.runner)
        self.external = ExternalSessions(settings)
        self.snoozes = idle.Snoozes(settings.paths.data_dir / "suggestions.json")
        # Read-only use of the usage index (the last turn's context size); the usage source scans it.
        self.usage = UsageIndex(settings.paths.data_dir / "usage.db", {}, settings)

    def available(self) -> Availability:
        try:
            self.runner.binary("tmux")
        except CliNotFound as e:
            return Availability(False, str(e))
        return Availability(True)

    def snapshot(self) -> dict:
        if not self.available().available:
            # Without tmux Eyrie can't run sessions, but it can still see the ones in your terminals.
            external = self.external.list()
            idle.annotate(self.settings, [], external, self.external.stats, self.usage, self.snoozes)
            return {"sessions": [], "external": external, "dirs": [], "error": self.available().reason,
                    "idle_hours": self.settings.sessions.idle_hours}
        managed = name_managed(self.settings, self.tmux.list())
        external = self.external.list(self.tmux.pane_pids())
        idle.annotate(self.settings, managed, external, self.external.stats, self.usage, self.snoozes)
        return {"sessions": managed, "external": external, "dirs": allowed_dirs(self.settings), "error": None,
                "idle_hours": self.settings.sessions.idle_hours}
