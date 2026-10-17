"""File helpers shared by everything Eyrie writes inside the vault."""
import hashlib
import os
import tempfile
from pathlib import Path

ABSENT = "absent"


def etag(content: str | None) -> str:
    """Content hash used for optimistic concurrency (If-Match). Not fooled by mtime granularity."""
    if content is None:
        return ABSENT
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def read_text(path: Path) -> str | None:
    try:
        with open(path, newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None


def atomic_write(path: Path, content: str) -> None:
    """Write via a temp file + rename, keeping the file's mode; never leaves a partial file."""
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            f.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
