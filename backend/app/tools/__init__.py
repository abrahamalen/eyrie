"""The AI coding CLIs Eyrie knows. Adding one is a new module here plus a line below;
`ToolId` (used by the API models) follows automatically."""
from typing import Literal

from app.tools import claude, codex
from app.tools.base import Tool

TOOLS: dict[str, Tool] = {t.id: t for t in (claude.TOOL, codex.TOOL)}
TOOL_IDS = tuple(TOOLS)
ToolId = Literal[TOOL_IDS]  # type: ignore[valid-type]


def get(tool_id: str) -> Tool:
    return TOOLS[tool_id]
