import json

import pytest

from app.actions import runner


def act(client, action, params, **flags):
    return client.post(f"/api/v1/actions/{action}", json={"params": params, **flags})


def claude_json(home):
    return json.loads((home / ".claude.json").read_text())


def add_to_claude_user(home):
    def effect(tool, args, cwd):
        d = claude_json(home)
        d.setdefault("mcpServers", {})[args[args.index("-t") + 2]] = {"type": args[args.index("-t") + 1]}
        (home / ".claude.json").write_text(json.dumps(d))
    return effect


HTTP = {"client": "claude", "name": "sentry", "transport": "http", "url": "https://mcp.sentry.dev/mcp",
        "headers": {"Authorization": "Bearer s3cret-token"}}


def test_actions_need_token(client, fake_cli):
    assert act(client, "mcp.add", HTTP).status_code == 401
    assert fake_cli.calls == []


def test_dry_run_shows_redacted_command_and_runs_nothing(authed, fake_cli, settings):
    r = act(authed, "mcp.add", HTTP, dry_run=True).json()
    assert r["argv"] == ["claude", "mcp", "add", "-s", "user", "-t", "http", "sentry", "https://mcp.sentry.dev/mcp",
                         "-H", "Authorization: ***"]
    assert fake_cli.calls == []
    assert not (settings.paths.data_dir / "audit.jsonl").exists()


def test_add_runs_cli_with_real_values_and_audits_redacted(authed, fake_cli, home, settings):
    fake_cli.effect = add_to_claude_user(home)
    r = act(authed, "mcp.add", HTTP).json()
    assert r["ok"] is True
    tool, args, _ = fake_cli.calls[0]
    assert tool == "claude" and "Authorization: Bearer s3cret-token" in args
    audit_text = (settings.paths.data_dir / "audit.jsonl").read_text()
    assert "s3cret" not in audit_text
    entry = authed.get("/api/v1/audit").json()[0]
    assert entry["action"] == "mcp.add" and entry["ok"] and entry["params"]["headers"] == {"Authorization": "***"}


def test_stdio_command_goes_after_double_dash(authed, fake_cli):
    act(authed, "mcp.add", {"client": "claude", "name": "fs", "transport": "stdio", "command": "npx",
                            "args": ["-y", "--danger"], "env": {"ROOT": "/tmp"}})
    _, args, _ = fake_cli.calls[0]
    assert args[args.index("--") + 1:] == ["npx", "-y", "--danger"]
    assert args[args.index("-e") + 1] == "ROOT=/tmp"


def test_codex_add_argv(authed, fake_cli):
    act(authed, "mcp.add", {"client": "codex", "name": "docs", "transport": "http", "url": "https://x.dev/mcp",
                            "bearer_token_env_var": "DOCS_TOKEN"})
    assert fake_cli.calls[0][:2] == ("codex", ["mcp", "add", "docs", "--url", "https://x.dev/mcp",
                                               "--bearer-token-env-var", "DOCS_TOKEN"])


@pytest.mark.parametrize("params,needle", [
    ({"client": "claude", "name": "-rf", "transport": "stdio", "command": "x"}, "letters, digits"),
    ({"client": "claude", "name": "a", "transport": "stdio"}, "need a command"),
    ({"client": "claude", "name": "a", "transport": "http", "url": "file:///etc/passwd"}, "http(s)://"),
    ({"client": "codex", "name": "a", "transport": "sse", "url": "https://x"}, "stdio and http"),
    ({"client": "codex", "name": "a", "transport": "stdio", "command": "x", "scope": "local", "project_dir": "/tmp"}, "global"),
    ({"client": "claude", "name": "a", "transport": "http", "url": "https://x", "headers": {"X": "a\r\nInjected: 1"}}, "Bad header"),
    ({"client": "claude", "name": "a", "transport": "stdio", "command": "x", "env": {"BAD-KEY": "1"}}, "env var"),
    ({"client": "claude", "name": "a", "transport": "stdio", "command": "x", "scope": "local"}, "needs project_dir"),
    ({"client": "claude", "name": "a", "transport": "stdio", "command": "x", "scope": "local", "project_dir": "rel/dir"}, "absolute"),
])
def test_invalid_params_rejected_before_running(authed, fake_cli, params, needle):
    r = act(authed, "mcp.add", params)
    assert r.status_code == 422 and needle in r.json()["detail"]
    assert fake_cli.calls == []


def test_destructive_needs_confirm(authed, fake_cli):
    r = act(authed, "mcp.remove", {"client": "claude", "name": "obsidian"})
    assert r.status_code == 428 and r.json()["detail"]["argv"] == ["claude", "mcp", "remove", "-s", "user", "obsidian"]
    assert fake_cli.calls == []


def test_remove_confirmed_and_verified(authed, fake_cli, home):
    def effect(tool, args, cwd):
        d = claude_json(home)
        d["mcpServers"].pop(args[-1])
        (home / ".claude.json").write_text(json.dumps(d))
    fake_cli.effect = effect
    r = act(authed, "mcp.remove", {"client": "claude", "name": "obsidian"}, confirm=True).json()
    assert r["ok"] is True
    names = [m["name"] for m in authed.get("/api/v1/sources/mcp").json()["configured"]]
    assert "obsidian" not in names


def test_exit_zero_without_effect_is_reported_as_failure(authed, fake_cli):
    r = act(authed, "mcp.add", HTTP).json()  # no effect: config unchanged
    assert r["ok"] is False and "isn't in its config" in r["message"]


def test_cli_error_surfaces_message_and_is_audited(authed, fake_cli):
    fake_cli.exit_code, fake_cli.stderr = 1, "MCP server sentry already exists in user config"
    r = act(authed, "mcp.add", HTTP).json()
    assert (r["ok"], r["exit_code"]) == (False, 1) and "already exists" in r["message"]
    assert authed.get("/api/v1/audit").json()[0]["ok"] is False


def test_local_scope_runs_in_project_dir(authed, fake_cli, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    act(authed, "mcp.add", {"client": "claude", "name": "a", "transport": "stdio", "command": "x",
                            "scope": "local", "project_dir": str(proj)})
    assert fake_cli.calls[0][2] == proj.resolve()


def test_cli_missing_is_503(authed, monkeypatch):
    def missing(self, tool, args, cwd=None):
        raise runner.CliNotFound("`claude` CLI not found on PATH")
    monkeypatch.setattr(runner.Runner, "run", missing)
    r = act(authed, "mcp.add", HTTP)
    assert r.status_code == 503 and "not found" in r.json()["detail"]


def test_unknown_action(authed):
    assert act(authed, "shell.exec", {"cmd": "rm -rf /"}).status_code == 404


INSTALLED = json.dumps([{"id": "a@m", "enabled": False}, {"id": "b@m", "enabled": True},
                        {"id": "archify@archify", "enabled": True}])


def test_plugin_toggle_argv(authed, fake_cli):
    fake_cli.stdout = INSTALLED
    r = act(authed, "plugins.disable", {"plugin": "archify@archify", "scope": "user"}, dry_run=True).json()
    assert r["argv"] == ["claude", "plugin", "disable", "archify@archify", "--json", "-s", "user"]
    assert act(authed, "plugins.enable", {"plugin": "--all"}).status_code == 422


def test_audit_newest_first(authed, fake_cli, monkeypatch):
    # Plugin-list output can't reflect toggles here, so audit with MCP actions instead.
    fake_cli.exit_code, fake_cli.stderr = 1, "nope"
    act(authed, "mcp.add", HTTP)
    act(authed, "mcp.remove", {"client": "codex", "name": "x"}, confirm=True)
    assert [e["action"] for e in authed.get("/api/v1/audit").json()] == ["mcp.remove", "mcp.add"]


def test_tmux_calls_dont_wait_on_a_slow_claude_call(settings, monkeypatch):
    import subprocess
    import threading
    import time
    from app.actions import runner

    release = threading.Event()

    def fake_run(argv, **kw):
        if argv[0].endswith("claude"):
            release.wait(5)
        return subprocess.CompletedProcess(argv, 0, "", "")

    from tests.conftest import REAL_BINARY, REAL_RUN
    monkeypatch.setattr(runner.subprocess, "run", fake_run)  # nothing real runs
    monkeypatch.setattr(runner.Runner, "run", REAL_RUN)
    monkeypatch.setattr(runner.Runner, "binary", REAL_BINARY)
    s = settings.model_copy(update={"cli": settings.cli.model_copy(update={"claude_bin": "/x/claude", "tmux_bin": "/x/tmux"})})
    r = runner.Runner(s)
    slow = threading.Thread(target=r.run, args=("claude", ["mcp", "add"]))
    slow.start()
    time.sleep(0.05)
    started = time.perf_counter()
    assert r.run("tmux", ["list-sessions"]).ok
    assert time.perf_counter() - started < 1
    release.set()
    slow.join()


def test_calls_to_one_tool_are_serialised_for_every_tool(settings, monkeypatch):
    # gemini (like claude and codex) rewrites its settings.json, so two calls must not overlap.
    import subprocess
    import threading
    import time
    from app.actions import runner
    from tests.conftest import REAL_BINARY, REAL_RUN

    active, peak = [0], [0]
    gate = threading.Lock()

    def fake_run(argv, **kw):
        with gate:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with gate:
            active[0] -= 1
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner.Runner, "run", REAL_RUN)
    monkeypatch.setattr(runner.Runner, "binary", REAL_BINARY)
    s = settings.model_copy(update={"cli": settings.cli.model_copy(update={"gemini_bin": "/x/gemini"})})
    r = runner.Runner(s)
    threads = [threading.Thread(target=r.run, args=("gemini", ["mcp", "add"])) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 1


def test_long_json_stdout_is_not_cut(settings, monkeypatch):
    # `claude plugin list --json` with a dozen plugins is over 4 KB; cutting it broke parsing.
    import json
    import subprocess
    from app.actions import runner
    from tests.conftest import REAL_BINARY, REAL_RUN

    big = json.dumps([{"id": f"plugin-{i}@market", "enabled": True, "description": "x" * 200} for i in range(40)])
    monkeypatch.setattr(runner.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, big, "e" * 9000))
    monkeypatch.setattr(runner.Runner, "run", REAL_RUN)
    monkeypatch.setattr(runner.Runner, "binary", REAL_BINARY)
    s = settings.model_copy(update={"cli": settings.cli.model_copy(update={"claude_bin": "/x/claude"})})
    r = runner.Runner(s).run("claude", ["plugin", "list", "--json"])
    assert len(big) > 4000 and json.loads(r.stdout) == json.loads(big)
    assert len(r.stderr) == runner.TAIL
