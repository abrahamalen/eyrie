import json

from fastapi.testclient import TestClient

from app.config import Privacy
from app.main import create_app


def test_reads_all_claude_scopes_and_codex(client, home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"shared": {"type": "http", "url": "https://s/mcp"}}}))
    d = json.loads((home / ".claude.json").read_text())
    d["projects"][str(proj)] = {"mcpServers": {"mine": {"command": "npx", "args": ["-y", "srv"]}}}
    (home / ".claude.json").write_text(json.dumps(d))
    (home / ".codex").mkdir()
    (home / ".codex/config.toml").write_text(
        '[mcp_servers.docs]\nurl = "https://d/mcp"\n\n[mcp_servers.fs]\ncommand = "fs"\nargs = ["--ro"]\n')
    got = {(m["client"], m["scope"], m["name"]): (m["type"], m["target"], m["project"])
           for m in client.get("/api/v1/sources/mcp").json()["configured"]}
    assert got[("claude", "user", "obsidian")][0] == "stdio"
    assert got[("claude", "local", "mine")] == ("stdio", "npx -y srv", str(proj))
    assert got[("claude", "project", "shared")] == ("http", "https://s/mcp", str(proj))
    assert got[("codex", "user", "docs")] == ("http", "https://d/mcp", None)
    assert got[("codex", "user", "fs")] == ("stdio", "fs --ro", None)


def test_hide_mcp_applies_to_every_client(settings, home):
    (home / ".codex").mkdir()
    (home / ".codex/config.toml").write_text('[mcp_servers.work-thing]\ncommand = "x"\n')
    s = settings.model_copy(update={"privacy": Privacy(hide_mcp=["work-thing"])})
    c = TestClient(create_app(s), base_url="http://localhost")
    assert {m["name"] for m in c.get("/api/v1/sources/mcp").json()["configured"]} == {"obsidian"}


PLUGIN_LIST = json.dumps([
    {"id": "nexus@nexus-agent-kit", "version": "1.2.0", "scope": "user", "enabled": True,
     "mcpServers": {"x": {"headers": {"DD_API_KEY": "${DD_API_KEY}"}}}, "installPath": "/secret/path"},
    {"id": "archify@archify", "version": "0.3.1", "scope": "user", "enabled": False},
])


def test_plugins_listed_with_known_fields_only(client, fake_cli):
    fake_cli.stdout = PLUGIN_LIST
    plugins = client.get("/api/v1/sources/plugins").json()["plugins"]
    assert [(p["name"], p["marketplace"], p["enabled"]) for p in plugins] == [
        ("archify", "archify", False), ("nexus", "nexus-agent-kit", True)]
    assert "mcpServers" not in plugins[1] and "installPath" not in plugins[1]


def test_plugin_list_cached_until_state_changes(client, fake_cli, home):
    fake_cli.stdout = PLUGIN_LIST
    client.get("/api/v1/sources/plugins")
    client.get("/api/v1/sources/plugins")
    assert len(fake_cli.calls) == 1
    (home / ".claude/settings.json").write_text('{"enabledPlugins": {}}')
    client.get("/api/v1/sources/plugins")
    assert len(fake_cli.calls) == 2


def _enabled_after_toggle(fake_cli, enabled_after):
    """Fake CLI: `plugin list` reflects state; toggles succeed (or silently don't)."""
    state = {"archify@archify": False, "nexus@nexus-agent-kit": True}

    def run(self, tool, args, cwd=None):
        from app.actions.runner import RunResult
        fake_cli.calls.append((tool, list(args), cwd))
        if args[:2] == ["plugin", "list"]:
            return RunResult(0, json.dumps([{"id": k, "enabled": v} for k, v in state.items()]), "", 5)
        if enabled_after is not None:
            state[args[2]] = enabled_after
        return RunResult(0, '{"outcome":"ok"}', "", 5)
    return run


def test_plugin_toggle_verified_and_cache_refreshed(authed, fake_cli, monkeypatch):
    from app.actions import runner
    monkeypatch.setattr(runner.Runner, "run", _enabled_after_toggle(fake_cli, True))
    r = authed.post("/api/v1/actions/plugins.enable", json={"params": {"plugin": "archify@archify"}}).json()
    assert r["ok"] is True
    plugins = {p["id"]: p["enabled"] for p in authed.get("/api/v1/sources/plugins").json()["plugins"]}
    assert plugins["archify@archify"] is True


def test_plugin_toggle_without_effect_reported(authed, fake_cli, monkeypatch):
    from app.actions import runner
    monkeypatch.setattr(runner.Runner, "run", _enabled_after_toggle(fake_cli, None))
    r = authed.post("/api/v1/actions/plugins.enable", json={"params": {"plugin": "archify@archify"}}).json()
    assert r["ok"] is False and "still disabled" in r["message"]


def test_toggling_uninstalled_plugin_refused(authed, fake_cli, monkeypatch):
    from app.actions import runner
    monkeypatch.setattr(runner.Runner, "run", _enabled_after_toggle(fake_cli, True))
    r = authed.post("/api/v1/actions/plugins.enable", json={"params": {"plugin": "nope@nowhere"}})
    assert r.status_code == 409 and "isn't installed" in r.json()["detail"]
    assert not any(c[1][:2] == ["plugin", "enable"] for c in fake_cli.calls)


def test_plugin_cli_failure_reported(client, fake_cli):
    fake_cli.exit_code, fake_cli.stderr = 1, "boom"
    assert client.get("/api/v1/sources/plugins").json() == {"plugins": [], "error": "boom"}


def test_large_plugin_list_parses_through_the_real_runner(settings, tmp_path, monkeypatch):
    from app.actions import runner
    from app.config import Cli
    from tests.conftest import REAL_BINARY, REAL_RUN

    monkeypatch.setattr(runner.Runner, "run", REAL_RUN)
    monkeypatch.setattr(runner.Runner, "binary", REAL_BINARY)
    plugins = [{"id": f"plugin{i}@market", "version": "1.0.0", "scope": "user", "enabled": True,
                "description": "x" * 200} for i in range(60)]
    out = tmp_path / "plugins.json"
    out.write_text(json.dumps(plugins))
    assert out.stat().st_size > 10_000
    fake_claude = tmp_path / "claude"
    fake_claude.write_text(f'#!/bin/sh\ncat "{out}"\n')
    fake_claude.chmod(0o755)
    c = TestClient(create_app(settings.model_copy(update={"cli": Cli(claude_bin=str(fake_claude))})),
                   base_url="http://localhost")
    body = c.get("/api/v1/sources/plugins").json()
    assert "error" not in body or not body["error"], body.get("error")
    assert len(body["plugins"]) == 60
