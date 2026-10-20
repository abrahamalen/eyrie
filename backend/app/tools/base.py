"""What Eyrie needs to know about one AI coding CLI (docs/tool-adapters.md §3).

An adapter supplies data and argv; it never runs anything itself (the Runner does). Each
capability is optional: a tool without MCP support has `mcp = None`, and the pages and
actions for it simply don't offer that tool.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.config import Settings
    from app.sessions.names import Name

# (last activity, exact): exact when tied to this very conversation, not just its directory.
Activity = tuple[datetime | None, bool]


class SessionCaps(Protocol):
    modes: tuple[str, ...]  # of "new", "continue", "resume"
    # Resuming only works from the directory the conversation was in (Gemini keys sessions by
    # project), so the UI must fix the directory before offering conversations.
    resume_requires_cwd: bool
    # A first argument that marks a helper process rather than an interactive session.
    helpers: frozenset[str]
    # What shrinks the context inside the session ("/compact"), for the resume-cost hint.
    compact_command: str | None
    # Prompt-cache lifetime in minutes (default, after a 1 h cache write); None: unknown.
    cache_minutes: tuple[int, int] | None

    def argv(self, exe: str, mode: str, cwd: str, resume_id: str | None, conversation_id: str | None) -> list[str]:
        """The program tmux runs for a new Eyrie session (always 2+ items, so no shell)."""

    def wants_conversation_id(self, mode: str) -> bool:
        """Whether Eyrie should pick the conversation id up front (so the preview matches the run)."""

    def activity(self, settings: "Settings") -> Callable[[str | None, str | None], Activity]:
        """A lookup (cwd, resume target) → Activity, built once per listing."""

    def known_dirs(self, settings: "Settings") -> set[Path]:
        """Directories this tool has been used in (where sessions may start)."""

    def names(self, settings: "Settings") -> Callable[..., "Name"]:
        """A lookup (pid, cwd, conversation id, resume target, started) → Name, built once per
        listing: the conversation and the name you (or the tool) gave it, from the tool's own
        files (docs/session-names-and-jump.md §3)."""


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
    scopes: tuple[str, ...]      # of "user", "local", "project"
    transports: tuple[str, ...]  # of "stdio", "http", "sse"
    headers: bool                # can set HTTP headers
    bearer_token_env_var: bool   # can read a bearer token from an env var

    def servers(self, settings: "Settings") -> list[dict]:
        """Configured servers: {name, scope, type, target (masked), project}."""

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
    # The tool's own state folder: when it exists you use the tool, so a missing binary is a
    # problem worth flagging; when it doesn't, the tool just isn't part of your setup.
    home: Callable[["Settings"], Path] | None = None
    sessions: SessionCaps | None = None
    usage: UsageCaps | None = None
    mcp: McpCaps | None = None
    plugins: bool = False
