import json
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.actions import runner as _runner
from app.config import Paths, Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_repo_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EYRIE_CONFIG", str(tmp_path / "absent.toml"))


REAL_RUN, REAL_BINARY = _runner.Runner.run, _runner.Runner.binary


@pytest.fixture(autouse=True)
def _never_run_real_cli(monkeypatch):
    """Tests must never touch the real claude/codex config. Use the fake_cli fixture."""
    from app.actions import runner

    def refuse(self, tool, args, cwd=None):
        raise AssertionError(f"test tried to run the real `{tool}` CLI: {args}")

    monkeypatch.setattr(runner.Runner, "run", refuse)
    monkeypatch.setattr(runner.Runner, "binary", lambda self, tool: f"/fake/bin/{tool}")


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    """Never read (or let setup write) the real ~/.eyrie/eyrie.toml, and don't let whatever
    this machine has on PATH decide which tools are enabled."""
    import app.tools

    monkeypatch.setenv("EYRIE_CONFIG", str(tmp_path / "eyrie-config" / "eyrie.toml"))
    monkeypatch.setattr(app.tools, "installed", lambda settings, tool: bool(getattr(settings.cli, f"{tool}_bin", None)))


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """Session detection reads `ps`; tests must not see the machine's real sessions."""
    from app.sessions import external
    monkeypatch.setattr(external, "_ps", lambda: "")
    monkeypatch.setattr(external, "_cwds", lambda pids: {})
    from app.sessions import procs
    monkeypatch.setattr(procs, "_stats", lambda: "")


# Pids a test spawned itself; the only ones any test may signal.
SPAWNED: set[int] = set()


@pytest.fixture(autouse=True)
def _signal_guard(monkeypatch):
    """Tests must never signal a real process: only ones they spawned (see `spawn`)."""
    from app.sessions import procs

    real = procs._kill

    def guarded(pid, sig, pidfd=None):
        if pid not in SPAWNED:
            raise AssertionError(f"test tried to signal pid {pid}, which it didn't spawn")
        return real(pid, sig, pidfd)

    monkeypatch.setattr(procs, "_kill", guarded)


@pytest.fixture
def spawn():
    """Start throwaway processes (argv lists), registered so they may be signalled; all are
    killed and reaped afterwards."""
    import subprocess

    procs_ = []

    def start(argv, **kw):
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, **kw)
        SPAWNED.add(p.pid)
        procs_.append(p)
        return p

    yield start
    for p in procs_:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=5)
        SPAWNED.discard(p.pid)


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
    import app.tools
    monkeypatch.setattr(app.tools, "installed", lambda settings, tool: True)  # the fake CLIs are "on PATH"
    return fake


@pytest.fixture
def home(tmp_path):
    vault = tmp_path / "vault"
    (vault / "Personal").mkdir(parents=True)
    (vault / "Tasks.md").write_text("# Work tasks\n\n- [ ] work item\n")
    (tmp_path / ".claude/agent-memory/code-reviewer").mkdir(parents=True)
    (tmp_path / ".claude/agent-memory/code-reviewer/notes.md").write_text("# notes\n")
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
        gemini_home=home / ".gemini",
        tasks=home / "vault/Personal/Tasks.md",
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
