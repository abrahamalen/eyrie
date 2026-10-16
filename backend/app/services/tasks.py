"""Tasks — plain markdown checklist, same file the dashboard version used, so it's still
editable directly from Obsidian."""
import re
from pathlib import Path

TASKS_FILE = Path.home() / "workspace/Obsidian Vault/Tasks.md"
TASK_LINE_RE = re.compile(r"^- \[( |x|X)\] (.*)$")


def list_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    tasks = []
    for line in TASKS_FILE.read_text().splitlines():
        m = TASK_LINE_RE.match(line)
        if m:
            tasks.append({"done": m.group(1).lower() == "x", "text": m.group(2)})
    return tasks


def _write_tasks(tasks: list[dict]) -> None:
    lines = ["# Tasks", ""]
    for t in tasks:
        box = "x" if t["done"] else " "
        lines.append(f"- [{box}] {t['text']}")
    TASKS_FILE.write_text("\n".join(lines) + "\n")


def add_task(text: str) -> list[dict]:
    tasks = list_tasks()
    if text.strip():
        tasks.append({"done": False, "text": text.strip()})
    _write_tasks(tasks)
    return tasks


def toggle_task(index: int) -> list[dict]:
    tasks = list_tasks()
    if 0 <= index < len(tasks):
        tasks[index]["done"] = not tasks[index]["done"]
    _write_tasks(tasks)
    return tasks


def delete_task(index: int) -> list[dict]:
    tasks = list_tasks()
    if 0 <= index < len(tasks):
        tasks.pop(index)
    _write_tasks(tasks)
    return tasks
