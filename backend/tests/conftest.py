import json
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.config import Paths, Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_repo_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EYRIE_CONFIG", str(tmp_path / "absent.toml"))


from app.actions import runner as _runner

REAL_RUN, REAL_BINARY = _runner.Runner.run, _runner.Runner.binary


@pytest.fixture(autouse=True)
def _never_run_real_cli(monkeypatch):
    """Tests must never touch the real claude/codex config. Use the fake_cli fixture."""
    from app.actions import runner

    def refuse(self, tool, args, cwd=None):
        raise AssertionError(f"test tried to run the real `{tool}` CLI: {args}")

    monkeypatch.setattr(runner.Runner, "run", refuse)
    monkeypatch.setattr(runner.Runner, "binary", lambda self, tool: f"/fake/bin/{tool}")


@dataclass
class FakeCli:
    calls: list = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    effect: object = None  # callable(tool, args, cwd) simulating what the real CLI writes

    def run(self, runner_self, tool, args, cwd=None):
        from app.actions.runner import RunResult
        self.calls.append((tool, list(args), cwd))
        if self.effect and self.exit_code == 0:
            self.effect(tool, args, cwd)
        return RunResult(self.exit_code, self.stdout, self.stderr, 12.0)


@pytest.fixture
def fake_cli(monkeypatch):
    from app.actions import runner
    fake = FakeCli()
    monkeypatch.setattr(runner.Runner, "run", lambda self, tool, args, cwd=None: fake.run(self, tool, args, cwd))
    return fake


@pytest.fixture
def home(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Personal").mkdir(parents=True)
    (vault / "agent-memory/Nexus/nexus-debugging").mkdir(parents=True)
    (vault / "agent-memory/Nexus/nexus-debugging/notes.md").write_text("# notes\n")
    (vault / "Tasks.md").write_text("# Work tasks\n\n- [ ] work item\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude.json").write_text(json.dumps({
        "projects": {"/p/eyrie": {"lastCost": 1.5, "lastTotalInputTokens": 10, "lastTotalOutputTokens": 20,
                                  "lastModelUsage": {"claude-opus-5-5": {"costUSD": 1.5, "inputTokens": 10, "outputTokens": 20}}}},
        "mcpServers": {"obsidian": {"type": "stdio"}, "work-thing": {"type": "http"}},
    }))
    return tmp_path


@pytest.fixture
def settings(home):
    return Settings(paths=Paths(
        claude_home=home / ".claude",
        claude_json=home / ".claude.json",
        codex_home=home / ".codex",
        vault=home / "vault",
        data_dir=home / ".eyrie",
    ))


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def authed(app):
    return TestClient(app, base_url="http://localhost", headers={"X-Eyrie-Token": app.state.token})
