"""The AI coding CLIs Eyrie knows. Adding one is a new module here plus a line below;
`ToolId` (used by the API models) follows automatically. `enabled()` is the subset this
machine uses (config `tools.enabled`)."""
import shutil
from typing import TYPE_CHECKING, Literal

from app.tools import claude, codex, gemini
from app.tools.base import Tool

if TYPE_CHECKING:
    from app.config import Settings

TOOLS: dict[str, Tool] = {t.id: t for t in (claude.TOOL, codex.TOOL, gemini.TOOL)}
TOOL_IDS = tuple(TOOLS)
ToolId = Literal[TOOL_IDS]  # type: ignore[valid-type]


def get(tool_id: str) -> Tool:
    return TOOLS[tool_id]


def installed(settings: "Settings", tool_id: str) -> bool:
    configured = getattr(settings.cli, f"{tool_id}_bin", None)
    return bool(configured or shutil.which(TOOLS[tool_id].binary))


def used(settings: "Settings", tool_id: str) -> bool:
    """Its state folder exists: you've run it here."""
    t = TOOLS.get(tool_id)
    return t is None or t.home is None or t.home(settings).exists()


def enabled(settings: "Settings") -> dict[str, Tool]:
    want = settings.tools.enabled
    if want == "auto":
        return {k: t for k, t in TOOLS.items() if installed(settings, k) or used(settings, k)}
    return {k: TOOLS[k] for k in want if k in TOOLS}
