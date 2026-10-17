import json

import pytest
from fastapi.testclient import TestClient

from app.config import Paths, Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_repo_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EYRIE_CONFIG", str(tmp_path / "absent.toml"))


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
