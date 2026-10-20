import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.usage.prices import ModelPrice, normalize_model

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def assistant(mid, model="claude-sonnet-5-5", ts=NOW, session="s1", cwd="/p/eyrie", req="r", **usage):
    u = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    u.update(usage)
    return {"type": "assistant", "timestamp": iso(ts), "sessionId": session, "cwd": cwd, "requestId": req,
            "message": {"id": mid, "model": model, "usage": u}}


def write(path, records, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + tail)


@pytest.fixture
def projects(home):
    return home / ".claude/projects"


def report(client, days=30):
    r = client.get(f"/api/v1/usage?days={days}")
    assert r.status_code == 200, r.text
    return r.json()


def test_dedupes_repeated_blocks_keeping_max(client, projects):
    # One response written as three content-block lines; output grows while streaming.
    write(projects / "-p-eyrie/s1.jsonl", [
        assistant("m1", input_tokens=10, output_tokens=5),
        assistant("m1", input_tokens=10, output_tokens=40),
        assistant("m1", input_tokens=10, output_tokens=40),
    ])
    m = report(client)["by_model"][0]
    assert (m["messages"], m["input"], m["output"]) == (1, 10, 40)


def test_prices_each_token_kind(client, projects):
    write(projects / "-p/s1.jsonl", [assistant(
        "m1", model="claude-sonnet-5-5", input_tokens=1_000_000, output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000, cache_creation_input_tokens=2_000_000,
        cache_creation={"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000})])
    # $2 in + $10 out + $0.20 read + $2.50 5m write + $4 1h write
    assert report(client)["totals"]["cost"] == pytest.approx(18.70)


def test_unsplit_cache_writes_priced_as_5m(client, projects):
    write(projects / "-p/s1.jsonl", [assistant("m1", cache_creation_input_tokens=1_000_000)])
    assert report(client)["totals"]["cost"] == pytest.approx(2.50)


def test_subagents_included_and_synthetic_skipped(client, projects):
    write(projects / "-p/s1.jsonl", [assistant("m1", output_tokens=1), assistant("x", model="<synthetic>", output_tokens=9)])
    write(projects / "-p/s1/subagents/agent-a.jsonl", [assistant("m2", output_tokens=2)])
    r = report(client)
    assert r["totals"]["messages"] == 2 and r["totals"]["tokens"] == 3


def test_model_suffixes_normalised_and_unknown_flagged(client, projects):
    assert normalize_model("claude-opus-4-6[1m]") == "claude-opus-4-6"
    assert normalize_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    write(projects / "-p/s1.jsonl", [assistant("m1", model="claude-opus-5-5[1m]", output_tokens=1_000_000),
                                     assistant("m2", model="claude-future-9", output_tokens=5)])
    r = report(client)
    assert {m["model"]: m["priced"] for m in r["by_model"]} == {"claude-opus-5-5": True, "claude-future-9": False}
    assert r["pricing"]["unpriced_models"] == ["claude-future-9"]
    assert r["totals"]["cost"] == pytest.approx(20.0)


def test_incremental_scan_and_partial_lines(app, projects):
    f = projects / "-p/s1.jsonl"
    write(f, [assistant("m1", output_tokens=1)], tail='{"type": "assistant", "trunc')
    source = app.state.registry["usage"]
    source.index.min_interval = 0
    c = TestClient(app, base_url="http://localhost")
    assert report(c)["totals"]["messages"] == 1
    # The partial line is completed and a new line appended: only the new bytes are read.
    with open(f, "a") as fh:
        fh.write('ated": 1}\n' + json.dumps(assistant("m2", output_tokens=2)) + "\n")
    assert report(c)["totals"]["messages"] == 2


def test_history_survives_transcript_deletion(app, projects):
    f = projects / "-p/s1.jsonl"
    write(f, [assistant("m1", output_tokens=7)])
    source = app.state.registry["usage"]
    source.index.min_interval = 0
    c = TestClient(app, base_url="http://localhost")
    assert report(c)["totals"]["tokens"] == 7
    f.unlink()
    assert report(c)["totals"]["tokens"] == 7


def test_replaced_file_rescanned_without_double_count(app, projects):
    f = projects / "-p/s1.jsonl"
    write(f, [assistant("m1", output_tokens=7), assistant("m2", output_tokens=1)])
    source = app.state.registry["usage"]
    source.index.min_interval = 0
    c = TestClient(app, base_url="http://localhost")
    report(c)
    f.unlink()
    write(f, [assistant("m1", output_tokens=7)])  # new inode, smaller
    totals = report(c)["totals"]
    assert (totals["messages"], totals["tokens"]) == (2, 8)


def test_days_bucketed_and_range_filled(client, projects):
    write(projects / "-p/s1.jsonl", [assistant("old", ts=NOW - timedelta(days=40), output_tokens=1),
                                     assistant("recent", ts=NOW - timedelta(days=2), output_tokens=5)])
    r = report(client, days=7)
    assert len(r["days"]) == 7 and r["days"][-1]["day"] == r["range"]["end"]
    assert r["totals"]["tokens"] == 5
    assert sum(1 for d in r["days"] if d["models"]) == 1
    assert report(client, days=60)["totals"]["tokens"] == 6


def test_session_attributed_to_starting_directory(client, projects):
    write(projects / "-p/s1.jsonl", [assistant("m1", cwd="/p/eyrie", ts=NOW - timedelta(minutes=5), output_tokens=1),
                                     assistant("m2", cwd="/p/eyrie/frontend", output_tokens=1)])
    assert [p["project"] for p in report(client)["by_project"]] == ["/p/eyrie"]


def test_pricing_override_from_config(settings, projects):
    s = settings.model_copy(update={"pricing": {"claude-sonnet-5-5": ModelPrice(
        input=0, output=1, cache_write_5m=0, cache_write_1h=0, cache_read=0)}})
    write(projects / "-p/s1.jsonl", [assistant("m1", output_tokens=1_000_000, input_tokens=1_000_000)])
    c = TestClient(create_app(s), base_url="http://localhost")
    assert report(c)["totals"]["cost"] == pytest.approx(1.0)


def test_days_param_validated(client):
    assert client.get("/api/v1/usage?days=0").status_code == 422
    assert client.get("/api/v1/usage?days=366").status_code == 422


def test_no_transcripts_is_unavailable_not_error(client):
    by_id = {s["id"]: s for s in client.get("/api/v1/sources").json()}
    assert by_id["usage"]["available"] is False
    assert report(client)["totals"]["messages"] == 0
