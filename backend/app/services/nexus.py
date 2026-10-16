"""Live Nexus agent memory — reads the vault's Nexus/ folder fresh on every call."""
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
NEXUS_DIR = HOME / "workspace/Obsidian Vault/agent-memory/Nexus"


def get_agents() -> list[dict]:
    agents = []
    if not NEXUS_DIR.exists():
        return agents
    for sub in sorted(NEXUS_DIR.iterdir()):
        if sub.is_dir():
            files = list(sub.glob("*.md"))
            mtime = max((f.stat().st_mtime for f in files), default=sub.stat().st_mtime)
            agents.append({
                "agent": sub.name,
                "file_count": len(files),
                "last_used": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            })
    return agents
