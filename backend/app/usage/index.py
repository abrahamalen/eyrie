"""Incremental index of token usage, built from each tool's session transcripts.

Tools prune old transcripts (Claude Code does), so this DB is the system of record for
history: rows outlive the files they came from. Each file is read from the last byte offset
seen, only up to its last complete line, so a scan costs a stat() per unchanged file. How a
line becomes a row is the tool adapter's job (app/tools/*.py, `usage`); rows are upserted
keeping the max of each counter, so rereading a file is idempotent.

Schema history:
1. Claude Code only.
2. A `tool` column on messages and files, and per-file parser `state` (Codex sets the model
   on an earlier line than the usage). Migrated in place; the v1 file is kept as usage.db.v1.
"""
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

SCHEMA_VERSION = "2"
TABLES = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, inode INTEGER, size INTEGER, offset INTEGER,
    tool TEXT NOT NULL DEFAULT 'claude', state TEXT
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
    cache_write_1h INTEGER NOT NULL DEFAULT 0,
    tool TEXT NOT NULL DEFAULT 'claude'
);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS messages_ts ON messages (ts);
CREATE INDEX IF NOT EXISTS messages_tool_session ON messages (tool, session_id);
"""
UPSERT = """
INSERT INTO messages (key, ts, session_id, project, model, subagent, input, output,
                      cache_read, cache_write_5m, cache_write_1h, tool)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (key) DO UPDATE SET
    input = max(input, excluded.input),
    output = max(output, excluded.output),
    cache_read = max(cache_read, excluded.cache_read),
    cache_write_5m = max(cache_write_5m, excluded.cache_write_5m),
    cache_write_1h = max(cache_write_1h, excluded.cache_write_1h)
"""
TOTALS = "SELECT count(*), coalesce(sum(input + output + cache_read + cache_write_5m + cache_write_1h), 0) FROM messages"


def _migrate_1_to_2(db_path: Path, con: sqlite3.Connection) -> None:
    """Add the tool and state columns. Every existing row is Claude Code's."""
    backup = db_path.with_name(db_path.name + ".v1")
    if not backup.exists():
        with closing(sqlite3.connect(backup)) as b:
            con.backup(b)
    before = con.execute(TOTALS).fetchone()
    # Explicit BEGIN: sqlite3 would otherwise autocommit each ALTER, and a failed check
    # couldn't roll them back.
    con.execute("BEGIN")
    try:
        con.execute("ALTER TABLE messages ADD COLUMN tool TEXT NOT NULL DEFAULT 'claude'")
        con.execute("ALTER TABLE files ADD COLUMN tool TEXT NOT NULL DEFAULT 'claude'")
        con.execute("ALTER TABLE files ADD COLUMN state TEXT")
        after = con.execute(TOTALS).fetchone()
        if after != before:
            raise RuntimeError(f"usage.db migration changed totals {before} -> {after}; rolled back")
        con.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


class UsageIndex:
    def __init__(self, db_path: Path, readers, settings, min_interval: float = 10.0) -> None:
        """readers: tool id -> that adapter's UsageCaps, or a callable returning that."""
        self.db_path = db_path
        self.readers = readers
        self.settings = settings
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_scan = 0.0
        self.last_scan_ms = 0.0

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path)
        con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        row = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            con.executescript(TABLES)
            con.execute("INSERT INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
            con.commit()
        elif row[0] == "1":
            _migrate_1_to_2(self.db_path, con)
        elif row[0] != SCHEMA_VERSION:
            raise RuntimeError(f"usage.db schema {row[0]} is newer than this Eyrie ({SCHEMA_VERSION})")
        con.executescript(INDEXES)
        return con

    def _readers(self) -> dict:
        return self.readers() if callable(self.readers) else self.readers

    def transcript_files(self) -> list[tuple[str, Path, bool]]:
        return [(tool, p, sub) for tool, r in self._readers().items() for p, sub in r.files(self.settings)]

    def scan(self, force: bool = False) -> None:
        with self._lock:
            if not force and time.monotonic() - self._last_scan < self.min_interval:
                return
            started = time.perf_counter()
            readers = self._readers()
            with closing(self.connect()) as con:
                known = {p: (i, s, o, st) for p, i, s, o, st in con.execute("SELECT path, inode, size, offset, state FROM files")}
                for tool, r in readers.items():
                    for path, subagent in r.files(self.settings):
                        self._scan_file(con, r, tool, path, subagent, known.get(str(path)))
            self._last_scan = time.monotonic()
            self.last_scan_ms = (time.perf_counter() - started) * 1000

    def _scan_file(self, con: sqlite3.Connection, reader, tool: str, path: Path, subagent: bool, known) -> None:
        try:
            st = path.stat()
        except FileNotFoundError:
            return
        offset, state = 0, {}
        if known:
            inode, _, prev_offset, prev_state = known
            # Same file grown (or unchanged): continue, with the parser state it had. Replaced
            # or truncated: reread from the start; the upsert keeps that idempotent.
            if inode == st.st_ino and st.st_size >= prev_offset:
                offset, state = prev_offset, json.loads(prev_state) if prev_state else {}
        if known and offset == st.st_size:
            return
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(st.st_size - offset)
        end = chunk.rfind(b"\n") + 1  # only complete lines; a partial tail waits for the next scan
        rows = []
        for line in chunk[:end].splitlines():
            if not any(n in line for n in reader.needles):
                continue
            try:
                row = reader.parse(json.loads(line), subagent, state)
            except (ValueError, TypeError, AttributeError):
                continue
            if row:
                rows.append((*row, tool))
        with con:
            con.executemany(UPSERT, rows)
            con.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (path) DO UPDATE SET "
                "inode = excluded.inode, size = excluded.size, offset = excluded.offset, "
                "tool = excluded.tool, state = excluded.state",
                (str(path), st.st_ino, st.st_size, offset + end, tool, json.dumps(state) if state else None),
            )

    def rows_since(self, since_iso: str, tools: list[str] | None = None) -> list[sqlite3.Row]:
        """Rows from since_iso on, optionally only these tools' (history of a tool you've
        turned off stays in the DB but out of reports)."""
        q, args = "SELECT * FROM messages WHERE ts >= ?", [since_iso]
        if tools is not None:
            q += f" AND tool IN ({','.join('?' * len(tools))})"
            args += tools
        with closing(self.connect()) as con:
            con.row_factory = sqlite3.Row
            return con.execute(q + " ORDER BY ts", args).fetchall()

    def stats(self) -> dict:
        with closing(self.connect()) as con:
            files, = con.execute("SELECT count(*) FROM files").fetchone()
            messages, oldest = con.execute("SELECT count(*), min(ts) FROM messages").fetchone()
        return {"files": files, "messages": messages, "oldest": oldest, "last_scan_ms": round(self.last_scan_ms, 1)}

    def last_turns(self, keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
        """(tool, session id) → its latest top-level turn: when, the prompt size (every adapter
        stores `input` as the uncached part, so input + cache read + cache writes is the whole
        context) and whether it wrote a 1 h cache entry. Read-only; never scans."""
        if not keys or not self.db_path.exists():
            return {}
        out = {}
        with closing(self.connect()) as con:
            for tool, sid in keys:
                row = con.execute(
                    "SELECT ts, input + cache_read + cache_write_5m + cache_write_1h, cache_write_1h FROM messages "
                    "WHERE tool = ? AND session_id = ? AND subagent = 0 ORDER BY ts DESC LIMIT 1", (tool, sid),
                ).fetchone()
                if row:
                    out[(tool, sid)] = {"ts": row[0], "context_tokens": row[1], "wrote_1h": row[2] > 0}
        return out

    def recent_sessions(self, limit: int = 20, tool: str = "claude") -> list[dict]:
        """Most recent top-level conversations of one tool, newest first."""
        with closing(self.connect()) as con:
            rows = con.execute(
                "SELECT session_id, min(ts), max(ts), count(*), "
                "(SELECT project FROM messages m2 WHERE m2.tool = m.tool AND m2.session_id = m.session_id "
                " ORDER BY ts LIMIT 1) "
                "FROM messages m WHERE tool = ? AND subagent = 0 AND session_id IS NOT NULL "
                "GROUP BY session_id ORDER BY max(ts) DESC LIMIT ?", (tool, limit),
            ).fetchall()
        return [{"id": sid, "started": a, "last": b, "messages": n, "project": proj} for sid, a, b, n, proj in rows]
