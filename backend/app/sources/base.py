from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings


@dataclass
class Availability:
    available: bool
    reason: str | None = None


class Source(Protocol):
    id: str
    title: str

    def available(self) -> Availability: ...

    def snapshot(self) -> dict[str, Any]: ...


def build_registry(settings: Settings) -> dict[str, Source]:
    from app.sources import claude, codex, mcp, memory, plugins, tasks
    from app.sessions.source import SessionsSource
    from app.usage.source import UsageSource

    known: dict[str, Source] = {
        "sessions": SessionsSource(settings),
        "claude": claude.ClaudeSource(settings),
        "codex": codex.CodexSource(settings),
        "mcp": mcp.McpSource(settings),
        "memory": memory.MemorySource(settings),
        "plugins": plugins.PluginsSource(settings),
        "tasks": tasks.TasksSource(settings),
        "usage": UsageSource(settings),
    }
    return {sid: known[sid] for sid in settings.sources.enabled if sid in known}


def path_availability(path, what: str) -> Availability:
    if path.exists():
        return Availability(True)
    return Availability(False, f"{what} not found at {path}")
