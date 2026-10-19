"""Where sessions may start: under a configured sessions.roots entry, or in a directory
one of the tools has already been used in."""
from pathlib import Path

from app.config import Settings
from app.tools import TOOLS


def _known(settings: Settings) -> set[Path]:
    return {d for t in TOOLS.values() if t.sessions for d in t.sessions.known_dirs(settings)}


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
