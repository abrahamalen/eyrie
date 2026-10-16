"""Live Codex usage — reads ~/.codex/state_5.sqlite fresh on every call (read-only connection,
safe to open even while a Codex session is actively writing to it)."""
import sqlite3
from pathlib import Path

HOME = Path.home()
DB_PATH = HOME / ".codex/state_5.sqlite"


def get_usage() -> dict:
    rows = []
    totals = {"tokens_used": 0}
    by_model: dict[str, int] = {}
    by_cwd: dict[str, int] = {}

    if not DB_PATH.exists():
        return {"threads": [], "totals": totals, "by_model": {}, "by_cwd": {}, "available": False}

    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("""
            SELECT cwd, model, tokens_used, created_at, updated_at, reasoning_effort, title
            FROM threads
            WHERE archived = 0
            ORDER BY updated_at DESC
            LIMIT 200
        """)
        for cwd, model, tokens_used, created_at, updated_at, reasoning_effort, title in cur.fetchall():
            tokens_used = tokens_used or 0
            totals["tokens_used"] += tokens_used
            m = model or "unknown"
            by_model[m] = by_model.get(m, 0) + tokens_used
            by_cwd[cwd] = by_cwd.get(cwd, 0) + tokens_used
            rows.append({
                "cwd": cwd,
                "model": m,
                "tokens_used": tokens_used,
                "updated_at": updated_at,
                "reasoning_effort": reasoning_effort,
                "title": (title or "")[:80],
            })
        con.close()
    except Exception as e:
        return {"error": str(e), "threads": [], "totals": totals, "by_model": {}, "by_cwd": {}, "available": False}

    return {"threads": rows[:50], "totals": totals, "by_model": by_model, "by_cwd": by_cwd, "available": True}
