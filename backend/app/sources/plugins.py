"""Claude Code plugins, via `claude plugin list --json` (the supported interface; the files
under ~/.claude/plugins are internal). That call takes ~0.7s, so its result is cached until
the plugin state files change or a plugin action runs."""
import json
import threading

from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sources.base import Availability

FIELDS = ("id", "version", "scope", "enabled", "projectEnabled", "installedAt", "lastUpdated")


class PluginsSource:
    id = "plugins"
    title = "Plugins"

    def __init__(self, settings: Settings) -> None:
        self.runner = Runner(settings)
        home = settings.paths.claude_home
        self.watch = [home / "plugins/installed_plugins.json", home / "settings.json", home / "settings.local.json"]
        self._lock = threading.Lock()
        self._key = None
        self._cache: dict | None = None

    def available(self) -> Availability:
        try:
            self.runner.binary("claude")
        except CliNotFound as e:
            return Availability(False, str(e))
        return Availability(True)

    def invalidate(self) -> None:
        with self._lock:
            self._key = None

    def snapshot(self) -> dict:
        key = tuple(p.stat().st_mtime_ns if p.exists() else None for p in self.watch)
        with self._lock:
            if self._cache is not None and key == self._key:
                return self._cache
        try:
            r = self.runner.run("claude", ["plugin", "list", "--json"])
        except CliNotFound as e:
            return {"plugins": [], "error": str(e)}
        if not r.ok:
            return {"plugins": [], "error": (r.stderr or r.stdout).strip()[-500:]}
        try:
            raw = json.loads(r.stdout)
        except ValueError:
            return {"plugins": [], "error": "Couldn't parse `claude plugin list --json` output"}
        plugins = []
        for p in raw:
            # Only known fields: the CLI output also carries plugin MCP configs, which can
            # hold header templates and env references.
            item = {k: p.get(k) for k in FIELDS}
            item["name"], _, item["marketplace"] = (p.get("id") or "").partition("@")
            plugins.append(item)
        plugins.sort(key=lambda p: p["id"] or "")
        result = {"plugins": plugins, "error": None}
        with self._lock:
            self._cache, self._key = result, key
        return result
