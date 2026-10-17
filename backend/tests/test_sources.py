from fastapi.testclient import TestClient

from app.config import Privacy, Settings, Sources
from app.main import create_app


def test_lists_sources_with_availability(client):
    by_id = {s["id"]: s for s in client.get("/api/v1/sources").json()}
    assert list(by_id) == ["claude", "codex", "mcp", "nexus", "tasks", "usage"]
    assert by_id["claude"]["available"] is True
    assert by_id["codex"]["available"] is False
    assert "Codex state DB not found" in by_id["codex"]["reason"]


def test_disabled_source_is_absent(settings):
    s = settings.model_copy(update={"sources": Sources(enabled=["claude"])})
    c = TestClient(create_app(s), base_url="http://localhost")
    assert [x["id"] for x in c.get("/api/v1/sources").json()] == ["claude"]
    assert c.get("/api/v1/sources/codex").status_code == 404


def test_claude_snapshot_shape(client):
    d = client.get("/api/v1/sources/claude").json()
    assert d["totals"]["cost_usd"] == 1.5
    assert d["projects"][0]["path"] == "/p/eyrie"
    assert d["by_model"]["claude-opus-5-5"]["input_tokens"] == 10


def test_codex_missing_db_degrades(client):
    assert client.get("/api/v1/sources/codex").json()["available"] is False


def test_nexus_snapshot(client):
    agents = client.get("/api/v1/sources/nexus").json()["agents"]
    assert agents[0]["agent"] == "nexus-debugging" and agents[0]["file_count"] == 1


def test_hide_mcp(settings):
    s = settings.model_copy(update={"privacy": Privacy(hide_mcp=["work-thing"])})
    c = TestClient(create_app(s), base_url="http://localhost")
    names = [m["name"] for m in c.get("/api/v1/sources/mcp").json()["configured"]]
    assert names == ["obsidian"]
    claude_names = [m["name"] for m in c.get("/api/v1/sources/claude").json()["configured_mcp"]]
    assert claude_names == ["obsidian"]


def test_tasks_use_personal_file_and_leave_work_file_alone(authed, home):
    work_before = (home / "vault/Tasks.md").read_text()
    r = authed.post("/api/v1/tasks", json={"text": "renew passport"}, headers={"If-Match": "absent"})
    assert [t["text"] for t in r.json()["tasks"]] == ["renew passport"]
    assert "renew passport" in (home / "vault/Personal/Tasks.md").read_text()
    assert (home / "vault/Tasks.md").read_text() == work_before
