"""Gemini CLI adapter, against files laid out the way gemini-cli writes them
(config/projectRegistry.ts, services/chatRecordingService.ts). Real-install validation is
separate; these pin the format we read."""
import hashlib
import json
import os

import pytest

from app.sessions import external
from app.sessions.external import ExternalSessions, parse_ps
from app.tools import TOOLS
from tests.test_usage import NOW, iso, report

SID = "7f3c2a10-1b2c-4d5e-8f90-a1b2c3d4e5f6"
ROOT = "/Users/me/personal/projects/eyrie"


def gemini_line(mid, ts=NOW, model="gemini-3.8-flash", **tokens):
    t = {"input": 0, "output": 0, "cached": 0, "thoughts": 0, "tool": 0, "total": 0} | tokens
    return {"id": mid, "timestamp": iso(ts), "type": "gemini", "content": "…", "model": model, "tokens": t}


@pytest.fixture
def gemini(home):
    g = home / ".gemini"
    data = g / "tmp/eyrie"
    (data / "chats").mkdir(parents=True)
    (data / ".project_root").write_text(ROOT)
    (g / "projects.json").write_text(json.dumps({"projects": {ROOT: "eyrie"}}))
    return g


def write_session(gemini, lines, name=f"session-2026-10-20T09-00-{SID[:8]}.jsonl"):
    path = gemini / "tmp/eyrie/chats" / name
    head = {"sessionId": SID, "projectHash": "x", "startTime": iso(NOW), "lastUpdated": iso(NOW),
            "kind": "main", "directories": [ROOT]}
    path.write_text("".join(json.dumps(x) + "\n" for x in [head, *lines]))
    return path


def gemini_models(client):
    return {m["model"]: m for m in report(client)["by_model"] if m["tool"] == "gemini"}


def test_usage_splits_cached_and_counts_thoughts_and_tool_tokens(client, gemini):
    write_session(gemini, [
        {"id": "u1", "timestamp": iso(NOW), "type": "user", "content": "hi"},
        gemini_line("g1", input=1_000_000, cached=200_000, output=100_000, thoughts=50_000, tool=10_000),
    ])
    m = gemini_models(client)["gemini-3.8-flash"]
    assert (m["input"], m["cache_read"], m["output"]) == (810_000, 200_000, 150_000)
    # 0.81M x $0.75 + 0.2M x $0.075 + 0.15M x $3.75
    assert m["cost"] == pytest.approx(0.6075 + 0.015 + 0.5625)


def test_message_rewritten_as_it_grows_counts_once(client, gemini):
    write_session(gemini, [gemini_line("g1", input=10, output=1), gemini_line("g1", input=10, output=40),
                           {"$patch": {"updates": {"g1": gemini_line("g1", input=10, output=55)}}},
                           {"$rewindTo": "g1"}, {"$set": {"lastUpdated": iso(NOW)}}])
    m = gemini_models(client)["gemini-3.8-flash"]
    assert (m["messages"], m["output"]) == (1, 55)


def test_session_and_project_from_metadata(client, gemini):
    write_session(gemini, [gemini_line("g1", input=5)])
    r = report(client)
    assert any(p["project"] == ROOT for p in r["by_project"])
    assert next(t for t in r["by_tool"] if t["tool"] == "gemini")["sessions"] == 1


def test_subagent_files_indexed_as_subagents(settings, gemini):
    (gemini / f"tmp/eyrie/chats/{SID}").mkdir()
    (gemini / f"tmp/eyrie/chats/{SID}/agent-1.jsonl").write_text(json.dumps(gemini_line("s1", input=1)) + "\n")
    files = TOOLS["gemini"].usage.files(settings)
    assert sorted((p.name, sub) for p, sub in files if p.suffix == ".jsonl") == [("agent-1.jsonl", True)]


def test_known_dirs_from_registry_markers_and_legacy_hash(settings, gemini):
    other = "/Users/me/old-project"
    legacy = gemini / "tmp" / hashlib.sha256(other.encode()).hexdigest()
    (legacy / "chats").mkdir(parents=True)
    from app.tools.gemini import data_dir
    assert data_dir(settings, other) == legacy
    assert {str(d) for d in TOOLS["gemini"].sessions.known_dirs(settings)} == {ROOT}


def test_terminal_session_detected_through_node_and_resume_is_exact(settings, gemini, monkeypatch):
    path = write_session(gemini, [gemini_line("g1", input=1)])
    old = path.stat().st_mtime - 3600
    os.utime(path, (old, old))
    monkeypatch.setattr(external, "_ps", lambda: (
        f" 4242 ttys009    01:00 node /opt/homebrew/bin/gemini --resume {SID}\n"
        " 4343 ttys010    00:10 /opt/homebrew/bin/gemini mcp list\n"))
    monkeypatch.setattr(external, "_cwds", lambda pids: {4242: ROOT})
    assert [(p["pid"], p["tool"], p["resume"]) for p in parse_ps(external._ps())] == [(4242, "gemini", SID)]
    s = ExternalSessions(settings).list()[0]
    assert s["activity_exact"] is True and 59 <= s["idle_minutes"] <= 61


def test_mcp_servers_read_from_user_and_project_settings(client, gemini, tmp_path, monkeypatch):
    (gemini / "settings.json").write_text(json.dumps({"mcpServers": {
        "fs": {"command": "npx", "args": ["-y", "@x/fs", "--token", "ghp_" + "a" * 36]},
        "remote": {"httpUrl": "https://mcp.example/mcp?key=secret"},
        "legacy-sse": {"url": "https://mcp.example/sse"}}}))
    proj = tmp_path / "proj"
    (proj / ".gemini").mkdir(parents=True)
    (proj / ".gemini/settings.json").write_text(json.dumps({"mcpServers": {"db": {"command": "db-mcp"}}}))
    (gemini / "projects.json").write_text(json.dumps({"projects": {ROOT: "eyrie", str(proj): "proj"}}))
    (gemini / "tmp/proj").mkdir()
    got = {(e["name"], e["scope"], e["type"]): e["target"] for e in client.get("/api/v1/sources/mcp").json()["configured"]
           if e["client"] == "gemini"}
    assert got[("remote", "user", "http")] == "https://mcp.example/mcp?key=***"
    assert got[("legacy-sse", "user", "sse")] == "https://mcp.example/sse"
    assert "ghp_" not in got[("fs", "user", "stdio")]
    assert ("db", "project", "stdio") in got


def test_mcp_add_argv_and_scope_rules(authed, fake_cli):
    r = authed.post("/api/v1/actions/mcp.add", json={"dry_run": True, "params": {
        "client": "gemini", "name": "fs", "transport": "stdio", "command": "npx", "args": ["-y", "@x/fs"],
        "env": {"KEY": "v"}}}).json()
    assert r["argv"] == ["gemini", "mcp", "add", "-s", "user", "-t", "stdio", "-e", "KEY=***", "--", "fs", "npx", "-y", "@x/fs"]
    bad = authed.post("/api/v1/actions/mcp.add", json={"dry_run": True, "params": {
        "client": "gemini", "name": "fs", "transport": "stdio", "command": "x", "scope": "local", "project_dir": "/tmp"}})
    assert bad.status_code == 422 and "user" in bad.text and "project" in bad.text


def test_session_argv(fake_cli, authed):
    new = authed.post("/api/v1/actions/sessions.start", json={"dry_run": True, "params": {
        "tool": "gemini", "cwd": "/tmp", "name": "eyrie-abc123"}}).json()["argv"]
    assert new[new.index("/tmp") + 1:][:2] == ["/usr/bin/env", "/fake/bin/gemini"]
    resume = authed.post("/api/v1/actions/sessions.start", json={"dry_run": True, "params": {
        "tool": "gemini", "cwd": "/tmp", "mode": "resume", "resume_id": SID, "name": "eyrie-abc124"}}).json()["argv"]
    assert resume[resume.index("/tmp") + 1:][:3] == ["/fake/bin/gemini", "--resume", SID]


def test_meta_describes_each_tool(client, fake_cli):
    tools = {t["id"]: t for t in client.get("/api/v1/meta").json()["tools"]}
    assert tools["gemini"]["resume_requires_cwd"] is True and tools["claude"]["resume_requires_cwd"] is False
    assert tools["gemini"]["mcp"]["scopes"] == ["user", "project"] and tools["codex"]["mcp"]["headers"] is False
    assert tools["claude"]["plugins"] and not tools["gemini"]["plugins"]
