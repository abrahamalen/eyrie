"""Personal tasks: a markdown checklist in the vault, so it stays editable from Obsidian.

Eyrie edits single lines in place and leaves every other line (headings, notes, nested
lists, blank lines, line endings) byte-for-byte untouched. Each write must carry the
etag the client last read; if Obsidian changed the file since, the write is refused.
"""
import hashlib
import re
import threading
from dataclasses import dataclass

from app.config import Settings
from app.fsutil import atomic_write as _atomic_write, etag as _etag, read_text
from app.sources.base import Availability

# Obsidian checklist items: any bullet, any status char ("x" done, " " open, "/" "-" etc.)
TASK_RE = re.compile(r"^(?P<lead>\s*[-*+] \[)(?P<status>.)(?P<mid>\] )(?P<text>.*?)(?P<eol>\r?\n)?$")
NEW_FILE_HEADER = "# Personal tasks\n\n"


class Conflict(Exception):
    """The file changed since the client read it."""


class NotFound(Exception):
    pass


@dataclass
class Task:
    id: str
    done: bool
    text: str
    line: int


def _parse(lines: list[str]) -> list[Task]:
    seen: dict[str, int] = {}
    tasks = []
    for i, line in enumerate(lines):
        m = TASK_RE.match(line)
        if not m:
            continue
        text = m["text"]
        # Keyed on text, not the checkbox, so an id survives toggling.
        base = hashlib.sha1(text.encode()).hexdigest()[:10]
        n = seen.get(base, 0)
        seen[base] = n + 1
        tasks.append(Task(id=base if n == 0 else f"{base}-{n}", done=m["status"] in "xX", text=text, line=i))
    return tasks


class TasksSource:
    id = "tasks"
    title = "Tasks"

    def __init__(self, settings: Settings) -> None:
        self.file = settings.paths.tasks
        self._lock = threading.Lock()

    def available(self) -> Availability:
        if self.file.parent.exists():
            return Availability(True)
        return Availability(False, f"Folder not found: {self.file.parent}")

    def snapshot(self) -> dict:
        content = self._read()
        lines = content.splitlines(keepends=True) if content else []
        return {"etag": _etag(content), "tasks": [t.__dict__ for t in _parse(lines)]}

    def add(self, text: str, etag: str) -> dict:
        text = _clean(text)

        def change(lines: list[str]) -> list[str]:
            tasks = _parse(lines)
            new = f"- [ ] {text}"
            if not lines:
                return [NEW_FILE_HEADER, new + "\n"]
            # New tasks go right after the last task, so notes below the list stay below it.
            at = tasks[-1].line + 1 if tasks else len(lines)
            eol = _eol(lines)
            if not lines[at - 1].endswith("\n"):
                lines[at - 1] += eol
            lines.insert(at, new + eol)
            return lines

        return self._write(etag, change)

    def update(self, task_id: str, etag: str, done: bool | None = None, text: str | None = None) -> dict:
        def change(lines: list[str]) -> list[str]:
            t = _find(lines, task_id)
            m = TASK_RE.match(lines[t.line])
            status = m["status"] if done is None else ("x" if done else " ")
            new_text = m["text"] if text is None else _clean(text)
            lines[t.line] = f"{m['lead']}{status}{m['mid']}{new_text}{m['eol'] or ''}"
            return lines

        return self._write(etag, change)

    def delete(self, task_id: str, etag: str) -> dict:
        def change(lines: list[str]) -> list[str]:
            del lines[_find(lines, task_id).line]
            return lines

        return self._write(etag, change)

    def _read(self) -> str | None:
        return read_text(self.file)

    def _write(self, etag: str, change) -> dict:
        with self._lock:
            content = self._read()
            if etag != _etag(content):
                raise Conflict()
            lines = change(content.splitlines(keepends=True) if content else [])
            _atomic_write(self.file, "".join(lines))
        return self.snapshot()


def _clean(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        raise ValueError("Task text is empty")
    return text


def _eol(lines: list[str]) -> str:
    return "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"


def _find(lines: list[str], task_id: str) -> Task:
    for t in _parse(lines):
        if t.id == task_id:
            return t
    raise NotFound(task_id)
