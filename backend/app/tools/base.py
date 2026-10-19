"""What Eyrie needs to know about one AI coding CLI (docs/tool-adapters.md §3).

An adapter supplies data and argv; it never runs anything itself (the Runner does). Each
capability is optional: a tool without MCP support has `mcp = None`, and the pages and
actions for it simply don't offer that tool.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from app.config import Settings

# (last activity, exact): exact when tied to this very conversation, not just its directory.
Activity = tuple[datetime | None, bool]


class SessionCaps(Protocol):
    modes: tuple[str, ...]  # of "new", "continue", "resume"
    # A first argument that marks a helper process rather than an interactive session.
    helpers: frozenset[str]

    def argv(self, exe: str, mode: str, cwd: str, resume_id: str | None, conversation_id: str | None) -> list[str]:
        """The program tmux runs for a new Eyrie session (always 2+ items, so no shell)."""

    def wants_conversation_id(self, mode: str) -> bool:
        """Whether Eyrie should pick the conversation id up front (so the preview matches the run)."""

    def activity(self, settings: "Settings") -> Callable[[str | None, str | None], Activity]:
        """A lookup (cwd, resume target) → Activity, built once per listing."""

    def known_dirs(self, settings: "Settings") -> set[Path]:
        """Directories this tool has been used in (where sessions may start)."""


# A usage row as the index stores it, minus the tool column:
# (key, ts, session_id, project, model, subagent, input, output, cache_read, cache_write_5m, cache_write_1h)
UsageRow = tuple


class UsageCaps(Protocol):
    # Only lines containing one of these are parsed (a cheap filter before json.loads).
    needles: tuple[bytes, ...]

    def files(self, settings: "Settings") -> list[tuple[Path, bool]]:
        """Transcript files to index, each with whether it's a subagent's."""

    def parse(self, record: dict, subagent: bool, state: dict) -> UsageRow | None:
        """One JSON line → a row, or None. `state` persists per file across scans, for formats
        where a value (the model, the session) is set by an earlier line."""


class McpCaps(Protocol):
    def servers(self, settings: "Settings") -> list[dict]:
        """Configured servers: {name, scope, type, target (masked), project}."""

    def validate(self, p) -> None:
        """Raise ValueError for options this tool's CLI doesn't support."""

    def add(self, p) -> tuple[list[str], Path | None]:
        """argv after the binary, and the cwd to run it in."""

    def remove(self, p) -> tuple[list[str], Path | None]:
        ...


@dataclass(frozen=True)
class Tool:
    id: str
    title: str
    binary: str
    version_args: tuple[str, ...] = ("--version",)
    # Shown when the binary isn't found: what stops working.
    needs: str = ""
    sessions: SessionCaps | None = None
    usage: UsageCaps | None = None
    mcp: McpCaps | None = None
    plugins: bool = False
