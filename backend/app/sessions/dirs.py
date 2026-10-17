"""Where sessions may start: under a configured sessions.roots entry, or in a directory
Claude Code or Codex has already been used in."""
import sqlite3
from contextlib import closing
from pathlib import Path

from app.config import Settings
from app.sources.claude import safe_read_json


def _known(settings: Settings) -> set[Path]:
    known = {Path(p) for p in ((safe_read_json(settings.paths.claude_json) or {}).get("projects") or {})}
    db = settings.paths.codex_home / "state_5.sqlite"
    if db.exists():
        try:
            with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                known |= {Path(r[0]) for r in con.execute("SELECT DISTINCT cwd FROM threads WHERE cwd IS NOT NULL")}
        except sqlite3.Error:
            pass
    return known


def allowed_dirs(settings: Settings) -> list[str]:
    candidates = set(_known(settings))
    for root in settings.sessions.roots:
        if root.is_dir():
            candidates.add(root)
            candidates |= {c for c in root.iterdir() if c.is_dir() and not c.name.startswith(".")}
    return sorted(str(p) for p in candidates if p.is_dir())


def is_allowed(settings: Settings, path: str) -> bool:
    p = Path(path)
    if not p.is_absolute() or not p.is_dir():
        return False
    p = p.resolve()
    if any(p == r.resolve() or r.resolve() in p.parents for r in settings.sessions.roots if r.is_dir()):
        return True
    return p in {k.resolve() for k in _known(settings) if k.is_dir()}
