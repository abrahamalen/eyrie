from datetime import datetime

from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sessions.dirs import allowed_dirs
from app.sessions.external import ExternalSessions
from app.sessions.names import display, resume_command
from app.sessions.tmux import Tmux
from app.sources.base import Availability
from app.tools import TOOLS


def name_managed(settings: Settings, sessions: list[dict]) -> list[dict]:
    """Eyrie's sessions with their names (docs/session-names-and-jump.md §3)."""
    namers = {}
    for s in sessions:
        tool = TOOLS.get(s["tool"] or "")
        n = None
        if tool is not None and tool.sessions is not None:
            if tool.id not in namers:
                namers[tool.id] = tool.sessions.names(settings)
            started = datetime.fromisoformat(s["created"]) if s["created"] else None
            n = namers[tool.id](s.get("pid") if s["alive"] else None, s["cwd"], s["conversation_id"], None, started)
        if n is not None:
            s["display_name"], s["name_source"] = display(n, s["name"])
            s["conversation_id"] = n.conversation_id or s["conversation_id"]
        else:
            s["display_name"], s["name_source"] = s["name"], "none"
        exact = n is None or n.exact
        s["resume_command"] = resume_command(s["tool"], s["cwd"], s["conversation_id"]) if exact else None
    return sessions


class SessionsSource:
    id = "sessions"
    title = "Sessions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = Runner(settings)
        self.tmux = Tmux(settings, self.runner)
        self.external = ExternalSessions(settings)

    def available(self) -> Availability:
        try:
            self.runner.binary("tmux")
        except CliNotFound as e:
            return Availability(False, str(e))
        return Availability(True)

    def snapshot(self) -> dict:
        if not self.available().available:
            # Without tmux Eyrie can't run sessions, but it can still see the ones in your terminals.
            return {"sessions": [], "external": self.external.list(), "dirs": [], "error": self.available().reason}
        managed = name_managed(self.settings, self.tmux.list())
        return {"sessions": managed, "external": self.external.list(self.tmux.pane_pids()),
                "dirs": allowed_dirs(self.settings), "error": None}
