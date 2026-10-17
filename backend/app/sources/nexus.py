"""Nexus agent memory from the vault's agent-memory/Nexus folder, read fresh on every call."""
from datetime import datetime, timezone

from app.config import Settings
from app.sources.base import Availability, path_availability


class NexusSource:
    id = "nexus"
    title = "Nexus memory"

    def __init__(self, settings: Settings) -> None:
        self.dir = settings.paths.nexus

    def available(self) -> Availability:
        return path_availability(self.dir, "Nexus memory folder")

    def snapshot(self) -> dict:
        agents = []
        if self.dir.exists():
            for sub in sorted(self.dir.iterdir()):
                if sub.is_dir():
                    files = list(sub.glob("*.md"))
                    mtime = max((f.stat().st_mtime for f in files), default=sub.stat().st_mtime)
                    agents.append({
                        "agent": sub.name,
                        "file_count": len(files),
                        "last_used": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                    })
        return {"agents": agents}
