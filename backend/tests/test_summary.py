import json
from datetime import datetime, timedelta, timezone

import pytest

from app import tools as app_tools
from app.actions import runner
from app.actions.runner import CliNotFound, RunResult
from tests.test_usage import assistant, iso, write

NOW = datetime.now(timezone.utc)
CONV = "0f3c9a52-8d1e-4b7a-9c2f-1a2b3c4d5e6f"


class FakeTools:
    """Answers `tool --version` and tmux list-sessions; records calls."""

    def __init__(self):
        self.calls = []
        self.sessions = []  # (name, tool, cwd, last_output_minutes_ago, dead, exit_status)
        self.missing = set()

    def run(self, _self, tool, args, cwd=None):
        self.calls.append((tool, list(args)))
        if args in (["-V"], ["--version"]):
            return RunResult(0, {"tmux": "tmux 3.6a", "claude": "2.1.302 (Claude Code)", "codex": "codex-cli 0.162.1",
                                 "gemini": "0.45.2"}[tool], "", 1)
        if tool == "tmux" and "list-panes" in args:
            return RunResult(0, "", "", 1)
        if tool == "tmux" and "list-sessions" in args:
            if not self.sessions:
                return RunResult(1, "", "no server running", 1)
            rows = []
            for name, t, cwd_, ago, dead, code in self.sessions:
                ts = int((NOW - timedelta(minutes=ago)).timestamp())
                rows.append("\t".join([name, t, cwd_, "new", "", str(ts), str(ts), "0", "1" if dead else "0",
                                       str(code) if dead else "", "node"]))
            return RunResult(0, "\n".join(rows) + "\n", "", 1)
        raise AssertionError((tool, args))

    def binary(self, _self, tool):
        if tool in self.missing:
            raise CliNotFound(f"`{tool}` CLI not found")
        return f"/fake/bin/{tool}"


@pytest.fixture
def tools(monkeypatch):
    fake = FakeTools()
    monkeypatch.setattr(runner.Runner, "run", lambda self, tool, args, cwd=None: fake.run(self, tool, args, cwd))
    monkeypatch.setattr(runner.Runner, "binary", lambda self, tool: fake.binary(self, tool))
    monkeypatch.setattr(app_tools, "installed", lambda settings, tool: tool not in fake.missing)
    return fake


def summary(client):
    r = client.get("/api/v1/summary")
    assert r.status_code == 200, r.text
    return r.json()


def kinds(s):
    return [a["kind"] for a in s["attention"]]


def test_all_fine(client, tools):
    s = summary(client)
    assert s["state"] == "ok" and s["attention"] == []
    assert {k: v["version"] for k, v in s["health"].items() if k != "usage_index"} == {
        "tmux": "3.6a", "claude": "2.1.302", "codex": "0.162.1", "gemini": "0.45.2"}


def test_missing_cli_is_a_problem_and_sorted_first(client, tools, home):
    (home / ".codex").mkdir()  # you use Codex
    tools.missing = {"codex", "gemini"}  # no ~/.gemini: not part of your setup
    tools.sessions = [("eyrie-idle1", "claude", "/p", 30, False, None)]
    s = summary(client)
    assert s["state"] == "problem"
    assert kinds(s)[0] == "cli_missing" and "codex isn't installed" in s["attention"][0]["title"]
    assert [a for a in s["attention"] if "gemini" in a["title"]] == []
    assert s["health"]["codex"] == {"found": False, "version": None, "path": None, "used": True}
    assert s["health"]["gemini"] is None  # neither installed nor used: not enabled


def test_session_states(client, tools):
    tools.sessions = [
        ("eyrie-idle1", "claude", "/p/eyrie", 25, False, None),
        ("eyrie-busy1", "codex", "/p/dot", 2, False, None),
        ("eyrie-fail1", "claude", "/p/blog", 60, True, 1),
        ("eyrie-done1", "claude", "/p/blog", 60, True, 0),
    ]
    s = summary(client)
    by = {a["kind"]: a for a in s["attention"]}
    assert set(kinds(s)) == {"session_exited_error", "session_idle"}
    assert by["session_idle"]["title"].startswith("eyrie-idle1 has been idle 2")
    assert by["session_idle"]["href"] == "/sessions?open=eyrie-idle1"
    assert "code 1" in by["session_exited_error"]["title"]
    assert kinds(s)[0] == "session_exited_error"  # problems before attention
    idle = {x["name"]: x["idle_minutes"] for x in s["sessions"]}
    assert idle["eyrie-busy1"] in (1, 2) and idle["eyrie-fail1"] is None


def test_idle_threshold_configurable(settings, tools):
    from fastapi.testclient import TestClient

    from app.config import Sessions
    from app.main import create_app
    tools.sessions = [("eyrie-idle1", "claude", "/p", 25, False, None)]
    app = create_app(settings.model_copy(update={"sessions": Sessions(idle_minutes=60)}))
    assert kinds(summary(TestClient(app, base_url="http://localhost"))) == []


def test_mcp_failures_only_for_configured_servers(client, tools, home):
    fail = {"failedMcpServers": [{"name": "obsidian", "errorCode": "CONNECT_TIMEOUT", "error": "x"},
                                 {"name": "plugin:datadog:mcp", "errorCode": "ENOTFOUND", "error": "y"}]}
    f = home / ".claude/projects/-p/s1.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"type": "system", **fail}, separators=(",", ":")) + "\n")  # compact, as Claude Code writes
    s = summary(client)
    assert [a["title"] for a in s["attention"]] == ["MCP server obsidian failed to connect"]
    assert "user scope" in s["attention"][0]["detail"]


def test_mcp_transcripts_reread_only_when_changed(client, tools, home, monkeypatch):
    from pathlib import Path
    f = home / ".claude/projects/-p/s1.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"failedMcpServers": [{"name": "obsidian", "errorCode": "E", "error": ""}]}, separators=(",", ":")) + "\n")
    reads = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (reads.append(self.name), real(self, *a, **k))[1])
    summary(client)
    summary(client)
    assert reads.count("s1.jsonl") == 1


def test_spend_today_yesterday_and_change(client, tools, home):
    write(home / ".claude/projects/-p/s1.jsonl", [
        assistant("a", model="claude-sonnet-5-5", output_tokens=1_000_000, ts=NOW, cwd="/p/eyrie", session="s1"),
        assistant("b", model="claude-sonnet-5-5", output_tokens=500_000, ts=NOW - timedelta(days=1), session="s1"),
        assistant("c", model="claude-sonnet-5-5", output_tokens=500_000, ts=NOW - timedelta(days=9), session="s1"),
    ])
    sp = summary(client)["spend"]
    assert (sp["today"], sp["yesterday"]) == (10.0, 5.0)
    assert len(sp["last_7_days"]) == 7 and sp["last_7_days"][-1]["cost"] == 10.0
    assert sp["change_vs_prev_7_pct"] == 200.0  # 15 vs 5
    assert sp["top_project_today"] == "/p/eyrie"


def test_no_previous_week_means_no_change_figure(client, tools, home):
    write(home / ".claude/projects/-p/s1.jsonl", [assistant("a", output_tokens=1000, ts=NOW)])
    assert summary(client)["spend"]["change_vs_prev_7_pct"] is None


def test_unpriced_model_flagged(client, tools, home):
    write(home / ".claude/projects/-p/s1.jsonl", [assistant("a", model="claude-future-9", output_tokens=5, ts=NOW)])
    assert "unpriced_model" in kinds(summary(client))


def test_next_open_tasks(client, tools, home):
    (home / "vault/Personal/Tasks.md").write_text("- [x] done\n- [ ] one\n- [ ] two\n- [ ] three\n- [ ] four\n")
    t = summary(client)["tasks"]
    assert t["open_count"] == 4 and [x["text"] for x in t["next"]] == ["one", "two", "three"]


def test_recent_projects_allowed_and_newest_first(client, tools, home, tmp_path):
    eyrie, gone = tmp_path / "eyrie", tmp_path / "gone"
    eyrie.mkdir()
    cj = json.loads((home / ".claude.json").read_text())
    cj["projects"][str(eyrie)] = {}
    (home / ".claude.json").write_text(json.dumps(cj))
    write(home / ".claude/projects/-p/s1.jsonl", [
        assistant("a", ts=NOW - timedelta(hours=3), cwd=str(eyrie), session="s1"),
        assistant("b", ts=NOW - timedelta(hours=1), cwd=str(gone), session="s2"),
    ])
    rollout = home / ".codex/sessions/2026/10/20/rollout-x.jsonl"
    write(rollout, [{"timestamp": iso(NOW), "type": "session_meta", "payload": {"id": CONV, "cwd": str(eyrie)}},
                    {"timestamp": iso(NOW), "type": "turn_context", "payload": {"model": "gpt-5.4", "cwd": str(eyrie)}},
                    {"timestamp": iso(NOW - timedelta(minutes=5)), "type": "token_usage_record",
                     "payload": {"response_id": "r1", "usage": {"input_tokens": 1, "output_tokens": 1}}}])
    rp = summary(client)["recent_projects"]
    assert [(p["path"], p["tool"]) for p in rp] == [(str(eyrie), "codex")]  # newest use wins; "gone" isn't allowed


def test_versions_cached(client, tools):
    summary(client)
    summary(client)
    assert sum(1 for t, a in tools.calls if a == ["--version"] and t == "claude") == 1
