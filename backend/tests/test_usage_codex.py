import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_usage import NOW, assistant, iso, report, write

SID = "01a13480-5390-7ed3-85c3-0e32b8d04c8e"


def meta(ts=NOW, cwd="/p/agent"):
    return {"timestamp": iso(ts), "type": "session_meta", "payload": {"id": SID, "cwd": cwd}}


def turn(model, ts=NOW, cwd="/p/agent"):
    return {"timestamp": iso(ts), "type": "turn_context", "payload": {"model": model, "cwd": cwd}}


def usage(input=0, cached=0, output=0):
    return {"input_tokens": input, "cached_input_tokens": cached, "cache_write_input_tokens": 0,
            "output_tokens": output, "reasoning_output_tokens": 0, "total_tokens": input + output}


def record(resp, ts=NOW, **u):
    return {"timestamp": iso(ts), "type": "token_usage_record", "payload": {"response_id": resp, "usage": usage(**u)}}


def count(total, ts=NOW, **u):
    return {"timestamp": iso(ts), "type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": usage(**u), "total_token_usage": {"total_tokens": total}}}}


@pytest.fixture
def rollouts(home):
    day = NOW.astimezone()
    return home / f".codex/sessions/{day:%Y/%m/%d}"


def codex_models(client):
    return {m["model"]: m for m in report(client)["by_model"] if m["tool"] == "codex"}


def test_records_priced_with_cached_input_split_out(client, rollouts):
    write(rollouts / f"rollout-a-{SID}.jsonl", [
        meta(), turn("gpt-5.4"),
        record("resp_1", input=1_000_000, cached=400_000, output=100_000),
        count(1_100_000, input=1_000_000, cached=400_000, output=100_000),  # same call: ignored
    ])
    m = codex_models(client)["gpt-5.4"]
    assert (m["messages"], m["input"], m["cache_read"], m["output"]) == (1, 600_000, 400_000, 100_000)
    # 0.6M x $2.50 + 0.4M x $0.25 + 0.1M x $15
    assert m["cost"] == pytest.approx(1.5 + 0.1 + 1.5)


def test_old_rollouts_use_token_count_deduped_on_running_total(client, rollouts):
    write(rollouts / f"rollout-b-{SID}.jsonl", [
        meta(), turn("gpt-5.5"),
        count(110, input=100, output=10),
        count(110, input=100, output=10),  # repeated when nothing changed
        count(330, input=200, output=20),
    ])
    m = codex_models(client)["gpt-5.5"]
    assert (m["messages"], m["input"], m["output"]) == (2, 300, 30)


def test_model_from_earlier_line_survives_incremental_scans(app, rollouts):
    from fastapi.testclient import TestClient
    path = rollouts / f"rollout-c-{SID}.jsonl"
    write(path, [meta(), turn("gpt-6-sol"), record("r1", input=10, output=1)])
    c = TestClient(app, base_url="http://localhost")
    report(c)
    with open(path, "a") as f:
        f.write(json.dumps(record("r2", input=20, output=2)) + "\n")
    app.state.registry["usage"].index.scan(force=True)
    m = codex_models(c)["gpt-6-sol"]
    assert (m["messages"], m["input"]) == (2, 30)


def test_codex_spread_across_days_and_tools_split(client, rollouts, home):
    yesterday = NOW - timedelta(days=1)
    write(rollouts / f"rollout-d-{SID}.jsonl", [meta(), turn("gpt-5.4"), record("r1", ts=yesterday, input=10, output=1),
                                                 record("r2", input=10, output=1)])
    write(home / ".claude/projects/-p/s1.jsonl", [assistant("m1", input_tokens=5)])
    r = report(client)
    days_with_codex = [d["day"] for d in r["days"] if "gpt-5.4" in d["models"]]
    assert len(days_with_codex) == 2
    assert {t["tool"] for t in r["by_tool"]} == {"claude", "codex"}
    assert next(t for t in r["by_tool"] if t["tool"] == "codex")["sessions"] == 1


def test_resume_list_stays_claude_only(client, rollouts, home):
    write(rollouts / f"rollout-e-{SID}.jsonl", [meta(), turn("gpt-5.4"), record("r1", input=1)])
    write(home / ".claude/projects/-p/s1.jsonl", [assistant("m1", input_tokens=5)])
    convs = client.get("/api/v1/sessions/conversations").json()
    assert [c["id"] for c in convs] == ["s1"]


def test_v1_db_migrates_in_place_with_backup(settings, home):
    from app.usage.index import UsageIndex
    db = home / ".eyrie/usage.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE files (path TEXT PRIMARY KEY, inode INTEGER, size INTEGER, offset INTEGER);
            CREATE TABLE messages (key TEXT PRIMARY KEY, ts TEXT NOT NULL, session_id TEXT, project TEXT,
                model TEXT NOT NULL, subagent INTEGER NOT NULL DEFAULT 0, input INTEGER NOT NULL DEFAULT 0,
                output INTEGER NOT NULL DEFAULT 0, cache_read INTEGER NOT NULL DEFAULT 0,
                cache_write_5m INTEGER NOT NULL DEFAULT 0, cache_write_1h INTEGER NOT NULL DEFAULT 0);
            INSERT INTO meta VALUES ('schema_version', '1');
        """)
        con.execute("INSERT INTO messages VALUES ('m|r', ?, 's', '/p', 'claude-opus-5-5', 0, 7, 3, 0, 0, 0)", (iso(NOW),))
    idx = UsageIndex(db, {}, settings)
    rows = idx.rows_since("2000-01-01")
    assert [(r["key"], r["tool"], r["input"]) for r in rows] == [("m|r", "claude", 7)]
    assert (db.parent / "usage.db.v1").exists()
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT value FROM meta").fetchone() == ("2",)


def test_newer_schema_refused(settings, home):
    from app.usage.index import UsageIndex
    db = home / ".eyrie/usage.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO meta VALUES ('schema_version', '9')")
    with pytest.raises(RuntimeError, match="newer"):
        UsageIndex(db, {}, settings).stats()
