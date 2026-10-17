"""Personal tasks: a plain markdown checklist in the vault, so it stays editable from Obsidian.

Writes still rebuild the file; in-place line edits with conflict checks are the next slice.
"""
import re

from app.config import Settings
from app.sources.base import Availability

TASK_LINE_RE = re.compile(r"^- \[( |x|X)\] (.*)$")


class TasksSource:
    id = "tasks"
    title = "Tasks"

    def __init__(self, settings: Settings) -> None:
        self.file = settings.paths.tasks

    def available(self) -> Availability:
        if self.file.parent.exists():
            return Availability(True)
        return Availability(False, f"Folder not found: {self.file.parent}")

    def snapshot(self) -> dict:
        return {"tasks": self.items()}

    def items(self) -> list[dict]:
        if not self.file.exists():
            return []
        tasks = []
        for line in self.file.read_text().splitlines():
            m = TASK_LINE_RE.match(line)
            if m:
                tasks.append({"done": m.group(1).lower() == "x", "text": m.group(2)})
        return tasks

    def _write(self, tasks: list[dict]) -> None:
        lines = ["# Tasks", ""]
        for t in tasks:
            box = "x" if t["done"] else " "
            lines.append(f"- [{box}] {t['text']}")
        self.file.write_text("\n".join(lines) + "\n")

    def add(self, text: str) -> list[dict]:
        tasks = self.items()
        if text.strip():
            tasks.append({"done": False, "text": text.strip()})
        self._write(tasks)
        return tasks

    def toggle(self, index: int) -> list[dict]:
        tasks = self.items()
        if 0 <= index < len(tasks):
            tasks[index]["done"] = not tasks[index]["done"]
        self._write(tasks)
        return tasks

    def delete(self, index: int) -> list[dict]:
        tasks = self.items()
        if 0 <= index < len(tasks):
            tasks.pop(index)
        self._write(tasks)
        return tasks
