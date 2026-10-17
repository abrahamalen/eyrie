"""Incremental index of Claude Code token usage, built from session transcripts.

Claude Code prunes old transcripts, so this DB is the system of record for history:
rows outlive the files they came from. Each file is read from the last byte offset seen,
only up to its last complete line, so a scan costs a stat() per unchanged file.

Transcript quirks this handles:
- One API response is written as several lines (one per content block), each repeating
  its usage; streaming lines can carry partial output counts. Rows are keyed on
  (message.id, requestId) and keep the max of each counter.
- Subagent runs live in <session>/subagents/*.jsonl and are billed to the parent session.
- Model ids may carry suffixes ([1m], -YYYYMMDD); "<synthetic>" rows aren't API calls.
"""
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from app.usage.prices import normalize_model

SCHEMA_VERSION = "1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, inode INTEGER, size INTEGER, offset INTEGER
);
CREATE TABLE IF NOT EXISTS messages (
    key TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    session_id TEXT,
    project TEXT,
    model TEXT NOT NULL,
    subagent INTEGER NOT NULL DEFAULT 0,
    input INTEGER NOT NULL DEFAULT 0,
    output INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write_5m INTEGER NOT NULL DEFAULT 0,
    cache_write_1h INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_ts ON messages (ts);
"""
UPSERT = """
INSERT INTO messages (key, ts, session_id, project, model, subagent, input, output,
                      cache_read, cache_write_5m, cache_write_1h)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (key) DO UPDATE SET
    input = max(input, excluded.input),
    output = max(output, excluded.output),
    cache_read = max(cache_read, excluded.cache_read),
    cache_write_5m = max(cache_write_5m, excluded.cache_write_5m),
    cache_write_1h = max(cache_write_1h, excluded.cache_write_1h)
"""


def _row(d: dict, subagent: bool) -> tuple | None:
    if d.get("type") != "assistant":
        return None
    m = d.get("message")
    if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
        return None
    model = m.get("model") or ""
    if not model or model == "<synthetic>" or not d.get("timestamp"):
        return None
    u = m["usage"]
    split = u.get("cache_creation")
    if isinstance(split, dict):
        w5, w1 = split.get("ephemeral_5m_input_tokens") or 0, split.get("ephemeral_1h_input_tokens") or 0
    else:
        w5, w1 = u.get("cache_creation_input_tokens") or 0, 0
    key = f"{m.get('id') or d.get('uuid')}|{d.get('requestId') or ''}"
    return (key, d["timestamp"], d.get("sessionId"), d.get("cwd"), normalize_model(model), int(subagent),
            u.get("input_tokens") or 0, u.get("output_tokens") or 0, u.get("cache_read_input_tokens") or 0, w5, w1)


class UsageIndex:
    def __init__(self, db_path: Path, projects_dir: Path, min_interval: float = 10.0) -> None:
        self.db_path = db_path
        self.projects_dir = projects_dir
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_scan = 0.0
        self.last_scan_ms = 0.0

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        version = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if version is None:
            con.execute("INSERT INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            con.commit()
        elif version[0] != SCHEMA_VERSION:
            raise RuntimeError(f"usage.db schema {version[0]} != {SCHEMA_VERSION}; needs a migration")
        return con

    def transcript_files(self) -> list[tuple[Path, bool]]:
        if not self.projects_dir.exists():
            return []
        top = [(p, False) for p in self.projects_dir.glob("*/*.jsonl")]
        sub = [(p, True) for p in self.projects_dir.glob("*/*/subagents/*.jsonl")]
        return top + sub

    def scan(self, force: bool = False) -> None:
        with self._lock:
            if not force and time.monotonic() - self._last_scan < self.min_interval:
                return
            started = time.perf_counter()
            with closing(self.connect()) as con:
                known = {p: (i, s, o) for p, i, s, o in con.execute("SELECT path, inode, size, offset FROM files")}
                for path, subagent in self.transcript_files():
                    self._scan_file(con, path, subagent, known.get(str(path)))
            self._last_scan = time.monotonic()
            self.last_scan_ms = (time.perf_counter() - started) * 1000

    def _scan_file(self, con: sqlite3.Connection, path: Path, subagent: bool, known) -> None:
        try:
            st = path.stat()
        except FileNotFoundError:
            return
        offset = 0
        if known:
            inode, _, prev_offset = known
            # Same file grown (or unchanged): continue. Replaced or truncated: reread; the
            # upsert keeps that idempotent.
            if inode == st.st_ino and st.st_size >= prev_offset:
                offset = prev_offset
        if known and offset == st.st_size:
            return
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(st.st_size - offset)
        end = chunk.rfind(b"\n") + 1  # only complete lines; a partial tail waits for the next scan
        rows = []
        for line in chunk[:end].splitlines():
            if b'"usage"' not in line:
                continue
            try:
                row = _row(json.loads(line), subagent)
            except (ValueError, TypeError, AttributeError):
                continue
            if row:
                rows.append(row)
        with con:
            con.executemany(UPSERT, rows)
            con.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?) ON CONFLICT (path) DO UPDATE SET "
                "inode = excluded.inode, size = excluded.size, offset = excluded.offset",
                (str(path), st.st_ino, st.st_size, offset + end),
            )

    def rows_since(self, since_iso: str) -> list[sqlite3.Row]:
        with closing(self.connect()) as con:
            con.row_factory = sqlite3.Row
            return con.execute("SELECT * FROM messages WHERE ts >= ? ORDER BY ts", (since_iso,)).fetchall()

    def stats(self) -> dict:
        with closing(self.connect()) as con:
            files, = con.execute("SELECT count(*) FROM files").fetchone()
            messages, oldest = con.execute("SELECT count(*), min(ts) FROM messages").fetchone()
        return {"files": files, "messages": messages, "oldest": oldest, "last_scan_ms": round(self.last_scan_ms, 1)}
