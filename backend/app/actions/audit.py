"""Append-only record of every action Eyrie runs: <data_dir>/audit.jsonl."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, action: str, argv: list[str], params: dict, ok: bool, exit_code: int,
               duration_ms: float, message: str) -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action": action,
            "argv": argv,
            "params": params,
            "ok": ok,
            "exit_code": exit_code,
            "duration_ms": round(duration_ms),
            "message": message[-500:],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def recent(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-limit:]
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
