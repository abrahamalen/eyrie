import json
import os
import tomllib
from pathlib import Path

import pytest

from app.setup import dump_toml

URL = "/api/v1/setup"


@pytest.fixture
def cfg():
    return Path(os.environ["EYRIE_CONFIG"])


def put(c, body, etag="absent"):
    return c.put(URL, json=body, headers={"If-Match": etag})


def test_first_run_is_unconfigured_and_detects(client, home):
    (home / ".claude/agent-memory/reviewer").mkdir(parents=True)
    meta = client.get("/api/v1/meta").json()
    assert meta["configured"] is False
    s = client.get(URL).json()
    assert s["config"] == {"path": os.environ["EYRIE_CONFIG"], "exists": False, "etag": "absent"}
    assert s["tools_enabled"] == "auto" and s["tasks"] == str(home / "vault/Personal/Tasks.md")
    by_id = {t["id"]: t for t in s["tools"]}
    assert by_id["claude"]["used"] and by_id["claude"]["enabled"] and not by_id["gemini"]["enabled"]
    assert s["agent_memory"]["exists"] is True


def test_suggests_parents_with_several_known_projects(client, home):
    root = home / "personal/projects"
    for name in ("a", "b", "c"):
        (root / name).mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"projects": {str(root / n): {} for n in ("a", "b", "c")}}))
    assert client.get(URL).json()["suggested_roots"] == [{"path": str(root), "projects": 3}]


def test_write_creates_file_and_applies_at_once(authed, home, cfg):
    roots = home / "personal/projects"
    roots.mkdir(parents=True)
    tasks = home / "notes/todo.md"
    tasks.parent.mkdir()
    r = put(authed, {"tools_enabled": ["claude"], "roots": [str(roots)], "tasks": str(tasks)})
    assert r.status_code == 200, r.text
    data = tomllib.loads(cfg.read_text())
    assert data == {"tools": {"enabled": ["claude"]}, "sessions": {"roots": [str(roots.resolve())]},
                    "paths": {"tasks": str(tasks)}}
    # live: no restart needed
    assert authed.get("/api/v1/meta").json()["configured"] is True
    assert authed.get("/api/v1/sources/tasks").status_code == 200
    assert r.json()["config"]["exists"] and authed.get("/api/v1/audit").json()[0]["action"] == "setup.write"


def test_write_keeps_sections_it_doesnt_own(authed, cfg):
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('[pricing."my-model"]\ninput = 1.5\noutput = 3.0\ncache_write_5m = 1.0\ncache_write_1h = 2.0\n'
                   'cache_read = 0.1\n\n[privacy]\nhide_mcp = ["work"]\n')
    etag = authed.get(URL).json()["config"]["etag"]
    assert put(authed, {"tools_enabled": "auto"}, etag).status_code == 200
    data = tomllib.loads(cfg.read_text())
    assert data["pricing"]["my-model"]["input"] == 1.5 and data["privacy"] == {"hide_mcp": ["work"]}
    assert data["tools"] == {"enabled": "auto"} and "tasks" not in data.get("paths", {})


def test_stale_etag_refused(authed, cfg):
    put(authed, {"tools_enabled": "auto"})
    r = put(authed, {"tools_enabled": ["claude"]}, "absent")
    assert r.status_code == 409 and r.json()["current"]["tools_enabled"] == "auto"


@pytest.mark.parametrize("body, msg", [
    ({"tools_enabled": ["nope"]}, "tools_enabled"),
    ({"tools_enabled": "auto", "roots": ["/definitely/not/here"]}, "Not an existing folder"),
    ({"tools_enabled": "auto", "tasks": "relative/todo.md"}, "absolute"),
    ({"tools_enabled": "auto", "tasks": "/definitely/not/here/todo.md"}, "Folder not found"),
])
def test_bad_answers_rejected(authed, cfg, body, msg):
    r = put(authed, body)
    assert r.status_code == 422 and msg in r.text and not cfg.exists()


def test_needs_token(client):
    assert put(client, {"tools_enabled": "auto"}).status_code == 401


def test_disabled_tool_refused_for_actions(authed, fake_cli, home):
    put(authed, {"tools_enabled": ["claude"]})
    r = authed.post("/api/v1/actions/sessions.start", json={"params": {"tool": "codex", "cwd": str(home)}})
    assert r.status_code == 409 and "isn't enabled" in r.text


def test_toml_writer_round_trips_awkward_values():
    data = {"a": {"b c": "quote \" and \\ and \n", "list": [1, 2.5, True]}, "x": {"y": {"z": "deep"}}}
    assert tomllib.loads(dump_toml(data)) == data
