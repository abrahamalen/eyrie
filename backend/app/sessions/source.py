from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sessions.dirs import allowed_dirs
from app.sessions.external import ExternalSessions
from app.sessions.tmux import Tmux
from app.sources.base import Availability


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
        managed = self.tmux.list()
        return {"sessions": managed, "external": self.external.list(self.tmux.pane_pids()),
                "dirs": allowed_dirs(self.settings), "error": None}
