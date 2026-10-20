"""First-run setup and the Settings page (docs/tool-adapters.md §5): what Eyrie detects on
this machine, and writing the answers to ~/.eyrie/eyrie.toml.

Writing merges into the existing file, so sections setup doesn't own ([pricing], [privacy],
...) survive; comments don't (the file is regenerated). The new values are applied to the
running app at once, so nothing needs a restart. EYRIE_* env vars still win at startup.
"""
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

from app import tools as tool_registry
from app.config import Settings, Tools, config_path
from app.fsutil import atomic_write, etag, read_text
from app.sources.claude import safe_read_json
from app.tools import TOOL_IDS, TOOLS, enabled, used

BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


class Conflict(Exception):
    pass


def _obsidian_vaults() -> list[str]:
    """Vaults Obsidian knows, from its own app config (never required)."""
    cfg = (Path.home() / "Library/Application Support/obsidian/obsidian.json" if sys.platform == "darwin"
           else Path.home() / ".config/obsidian/obsidian.json")
    vaults = (safe_read_json(cfg) or {}).get("vaults") or {}
    paths = [v.get("path") for v in vaults.values() if isinstance(v, dict)]
    return sorted(p for p in paths if isinstance(p, str) and Path(p).is_dir())


def suggest_roots(settings: Settings, limit: int = 6) -> list[dict]:
    """Parent folders holding several projects the tools already know, e.g. ~/personal/projects."""
    known = {d for t in TOOLS.values() if t.sessions for d in t.sessions.known_dirs(settings)}
    home = Path.home()
    parents = Counter(str(d.parent) for d in known if d.parent not in (home, Path("/")) and d.parent.is_dir())
    return [{"path": p, "projects": n} for p, n in parents.most_common() if n >= 2][:limit]


def detect(settings: Settings, versions) -> dict:
    path = config_path()
    text = read_text(path)
    on = enabled(settings)
    tools = []
    for t in TOOLS.values():
        v = versions.get(t.id) if tool_registry.installed(settings, t.id) else {"found": False, "version": None, "path": None}
        tools.append({"id": t.id, "title": t.title, "installed": v["found"], "version": v["version"], "path": v["path"],
                      "home": str(t.home(settings)) if t.home else None, "used": used(settings, t.id),
                      "enabled": t.id in on})
    return {
        "config": {"path": str(path), "exists": text is not None, "etag": etag(text)},
        "tools_enabled": settings.tools.enabled,
        "tools": tools,
        "roots": [str(r) for r in settings.sessions.roots],
        "suggested_roots": suggest_roots(settings),
        "tasks": str(settings.paths.tasks) if settings.paths.tasks else None,
        "obsidian_vaults": _obsidian_vaults(),
        "agent_memory": {"path": str(settings.paths.memory), "exists": settings.paths.memory.is_dir()},
    }


def validate(body) -> tuple[str | list[str], list[Path], Path | None]:
    tools = body.tools_enabled
    if tools != "auto":
        unknown = [t for t in tools if t not in TOOL_IDS]
        if unknown or not isinstance(tools, list):
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
    roots = []
    for r in body.roots:
        p = Path(r).expanduser()
        if not p.is_absolute() or not p.is_dir():
            raise ValueError(f"Not an existing folder: {r}")
        roots.append(p.resolve())
    tasks = None
    if body.tasks:
        tasks = Path(body.tasks).expanduser()
        if not tasks.is_absolute() or tasks.suffix != ".md":
            raise ValueError("The tasks file must be an absolute path to a .md file")
        if not tasks.parent.is_dir():
            raise ValueError(f"Folder not found: {tasks.parent}")
        if tasks.exists() and not tasks.is_file():
            raise ValueError(f"Not a file: {tasks}")
    return tools, roots, tasks


def write(settings: Settings, body, if_match: str) -> Settings:
    """Merge the answers into the config file and return the settings to run with."""
    tools, roots, tasks = validate(body)
    path = config_path()
    current = read_text(path)
    if etag(current) != if_match:
        raise Conflict()
    try:
        data = tomllib.loads(current) if current else {}
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path} isn't valid TOML ({e}); fix or remove it first") from e
    data.setdefault("tools", {})["enabled"] = tools
    data.setdefault("sessions", {})["roots"] = [str(r) for r in roots]
    if tasks:
        data.setdefault("paths", {})["tasks"] = str(tasks)
    else:
        data.get("paths", {}).pop("tasks", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, dump_toml(data, header=True))
    return settings.model_copy(update={
        "tools": Tools(enabled=tools),
        "sessions": settings.sessions.model_copy(update={"roots": roots}),
        "paths": settings.paths.model_copy(update={"tasks": tasks}),
    })


# --- a small TOML writer: tables, strings, numbers, bools and arrays of those ---------------

def _key(k: str) -> str:
    return k if BARE_KEY.match(k) else json.dumps(k)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)  # JSON string escapes are valid TOML basic-string escapes
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise TypeError(f"Can't write {type(v).__name__} to TOML")


def dump_toml(data: dict, header: bool = False) -> str:
    out = ["# Written by Eyrie (first-run setup / Settings). Edits here are kept, comments aren't.\n"] if header else []

    def table(prefix: list[str], d: dict) -> None:
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        if prefix and (scalars or not any(isinstance(v, dict) for v in d.values())):
            out.append(f"\n[{'.'.join(_key(p) for p in prefix)}]\n")
        for k, v in scalars.items():
            out.append(f"{_key(k)} = {_value(v)}\n")
        for k, v in d.items():
            if isinstance(v, dict):
                table([*prefix, k], v)

    table([], data)
    return "".join(out).lstrip("\n")
