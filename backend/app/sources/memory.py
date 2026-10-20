"""Agent memory: what Claude Code subagents remember, <claude_home>/agent-memory/<agent>/*.md
(paths.agent_memory to point elsewhere).

Eyrie reads and edits files only inside that folder: names are restricted, paths are
resolved and must stay inside it, and symlinks below it are refused (the folder itself may
be a symlink, e.g. into a notes vault). Writes need the etag the editor loaded (so an edit
an agent made in between isn't lost), and deleting moves the file to ~/.eyrie/trash
instead of removing it.
"""
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.fsutil import atomic_write, etag, read_text
from app.sources.base import Availability, path_availability

AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,100}\.md$")
MAX_BYTES = 1_000_000


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class MemorySource:
    id = "memory"
    title = "Agent memory"

    def __init__(self, settings: Settings) -> None:
        self.dir = settings.paths.memory
        self.trash = settings.paths.data_dir / "trash"
        self._lock = threading.Lock()

    def available(self) -> Availability:
        return path_availability(self.dir, "Agent memory folder")

    def snapshot(self) -> dict:
        agents = []
        if self.dir.exists():
            for sub in sorted(self.dir.iterdir()):
                if not sub.is_dir() or sub.is_symlink() or not AGENT_RE.match(sub.name):
                    continue
                files = sorted((f for f in sub.glob("*.md") if f.is_file() and not f.is_symlink()), key=lambda f: f.name)
                mtime = max((f.stat().st_mtime for f in files), default=sub.stat().st_mtime)
                agents.append({
                    "agent": sub.name,
                    "file_count": len(files),
                    "last_used": _iso(mtime),
                    "files": [{"name": f.name, "size": f.stat().st_size, "modified": _iso(f.stat().st_mtime)} for f in files],
                })
        return {"agents": agents}

    def path(self, agent: str, name: str) -> Path:
        """The file's path, or ValueError if it isn't a plain .md file directly in an agent folder."""
        if not AGENT_RE.match(agent) or not FILE_RE.match(name):
            raise ValueError("Unsupported agent or file name")
        folder = self.dir / agent
        if folder.is_symlink() or not folder.is_dir():
            raise NotFound(agent)
        p = folder / name
        if p.is_symlink() or p.resolve().parent != folder.resolve() or self.dir.resolve() not in p.resolve().parents:
            raise ValueError("Path is outside the agent memory folder")
        return p

    def read(self, agent: str, name: str) -> dict:
        p = self.path(agent, name)
        content = read_text(p)
        if content is None:
            raise NotFound(name)
        return {"agent": agent, "name": name, "content": content, "etag": etag(content),
                "modified": _iso(p.stat().st_mtime), "linked_from": self._links_to(agent, name)}

    def write(self, agent: str, name: str, content: str, if_match: str) -> dict:
        if len(content.encode()) > MAX_BYTES:
            raise ValueError("File is larger than 1 MB")
        p = self.path(agent, name)
        with self._lock:
            if etag(read_text(p)) != if_match:
                raise Conflict()
            atomic_write(p, content)
        return self.read(agent, name)

    def delete(self, agent: str, name: str, if_match: str) -> Path:
        p = self.path(agent, name)
        with self._lock:
            current = read_text(p)
            if current is None:
                raise NotFound(name)
            if etag(current) != if_match:
                raise Conflict()
            dest_dir = self.trash / "agent-memory" / agent
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            if dest.exists():
                dest = dest_dir / f"{p.stem} {datetime.now().strftime('%Y-%m-%d %H%M%S')}{p.suffix}"
            shutil.move(p, dest)
        return dest

    def _links_to(self, agent: str, name: str) -> list[str]:
        """Other files in the agent folder that mention this one (e.g. its MEMORY.md index)."""
        stem = name.removesuffix(".md")
        out = []
        for f in sorted((self.dir / agent).glob("*.md")):
            if f.name == name or f.is_symlink():
                continue
            text = read_text(f) or ""
            if name in text or f"[[{stem}]]" in text or f"[[{stem}|" in text:
                out.append(f.name)
        return out

