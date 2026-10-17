from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sessions.dirs import allowed_dirs
from app.sessions.tmux import Tmux
from app.sources.base import Availability


class SessionsSource:
    id = "sessions"
    title = "Sessions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = Runner(settings)
        self.tmux = Tmux(settings, self.runner)

    def available(self) -> Availability:
        try:
            self.runner.binary("tmux")
        except CliNotFound as e:
            return Availability(False, str(e))
        return Availability(True)

    def snapshot(self) -> dict:
        if not self.available().available:
            return {"sessions": [], "dirs": [], "error": self.available().reason}
        return {"sessions": self.tmux.list(), "dirs": allowed_dirs(self.settings), "error": None}
