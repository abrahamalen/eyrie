"""Session names (docs/session-names-and-jump.md §3): the name you gave a session, else the
tool's own title, else a short id. Read-only from the tools' files; each adapter knows its
format (SessionCaps.names) and this module has what they share."""
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Source = Literal["user", "tool", "id", "none"]
MAX_NAME = 80
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TAIL_BYTES = 256 * 1024


@dataclass(frozen=True)
class Name:
    conversation_id: str | None = None
    name: str | None = None
    source: Source = "none"
    # False when the conversation is a best guess (newest in the directory), not known.
    exact: bool = True


def clean(v) -> str | None:
    """A name fit to show: a string, control characters removed, at most 80 characters."""
    if not isinstance(v, str):
        return None
    v = " ".join(CONTROL.sub(" ", v).split())
    return v[:MAX_NAME].rstrip() or None


def short_id(conversation_id: str) -> str:
    """8 hex characters. UUIDv7 ids (Codex) start with a timestamp, so threads started close
    together share a prefix: use their random end instead."""
    if UUID_RE.match(conversation_id):
        return conversation_id[-8:] if conversation_id[14] == "7" else conversation_id[:8]
    return conversation_id[:8]


def display(n: Name, fallback: str) -> tuple[str, Source]:
    if n.name:
        return n.name, n.source if n.source in ("user", "tool") else "tool"
    if n.conversation_id:
        return short_id(n.conversation_id), "id"
    return fallback, "none"


_tails: dict[tuple[Path, int, bytes], tuple[tuple[int, float], list[dict]]] = {}


def tail_records(path: Path, max_bytes: int = TAIL_BYTES, needle: bytes = b"") -> list[dict]:
    """JSON objects on the last `max_bytes` of a JSON Lines file (the first, partial line
    dropped), keeping only lines containing `needle`. Cached on (size, mtime)."""
    try:
        st = path.stat()
    except OSError:
        return []
    key, cache_key = (st.st_size, st.st_mtime), (path, max_bytes, needle)
    hit = _tails.get(cache_key)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with path.open("rb") as f:
            if st.st_size > max_bytes:
                f.seek(st.st_size - max_bytes)
                data = f.read().split(b"\n", 1)[-1]
            else:
                data = f.read()
    except OSError:
        return []
    out = []
    for line in data.splitlines():
        if needle and needle not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    if len(_tails) > 512:
        _tails.clear()
    _tails[cache_key] = (key, out)
    return out


def resume_command(tool: str | None, cwd: str | None, conversation_id: str | None) -> str | None:
    """What to paste in a terminal to pick the conversation up again (shown, never run)."""
    from app.tools import TOOLS  # the adapters import this module

    t = TOOLS.get(tool or "")
    if t is None or t.sessions is None or not conversation_id or not cwd:
        return None
    if not (UUID_RE.match(conversation_id) or NAME_RE.match(conversation_id)):
        return None
    argv = t.sessions.argv(t.binary, "resume", cwd, conversation_id, None)
    return f"cd {shlex.quote(cwd)} && {shlex.join(argv)}"
