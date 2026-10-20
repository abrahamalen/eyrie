import json
import sqlite3

import pytest

from app.actions.runner import RunResult

CONV = "0f3c9a52-8d1e-4b7a-9c2f-1a2b3c4d5e6f"


@pytest.fixture
def project(home):
    """A directory Claude Code already knows (from ~/.claude.json projects)."""
    d = home / "work" / "eyrie"
    d.mkdir(parents=True)
    cj = json.loads((home / ".claude.json").read_text())
    cj["projects"][str(d)] = {}
    (home / ".claude.json").write_text(json.dumps(cj))
    return d


class FakeTmux:
    """Minimal stand-in for Eyrie's tmux server: tracks sessions created/killed via argv."""

    def __init__(self):
        self.sessions = {}
        self.calls = []

    def __call__(self, runner_self, tool, args, cwd=None):
        self.calls.append((tool, list(args)))
        assert tool == "tmux"
        a = args[4:]  # strip -L eyrie -f conf
        if a[0] == "list-sessions":
            if not self.sessions:
                return RunResult(1, "", "no server running", 1)
            rows = ["\t".join([n, s["tool"], s["cwd"], s["mode"], s["conv"], "1792257873", "1792257900", "0", "0", "", "node"])
                    for n, s in self.sessions.items()]
            return RunResult(0, "\n".join(rows) + "\n", "", 1)
        if a[0] == "new-session":
            name = a[a.index("-s") + 1]
            opts = {a[i + 4]: a[i + 5] for i, x in enumerate(a) if x == ";"}
            self.sessions[name] = {"tool": opts["@eyrie_tool"], "cwd": opts["@eyrie_cwd"], "mode": opts["@eyrie_mode"],
                                   "conv": opts["@eyrie_conv"], "argv": a}
            return RunResult(0, "", "", 5)
        if a[0] == "list-panes":
            return RunResult(0, "".join(f"{1000 + i}\n" for i, _ in enumerate(self.sessions)), "", 1)
        if a[0] == "kill-session":
            self.sessions.pop(a[a.index("-t") + 1], None)
            return RunResult(0, "", "", 1)
        if a[0] == "capture-pane":
            name = a[a.index("-t") + 1]
            return RunResult(0, f"screen of {name}\n\n", "", 1) if name in self.sessions else RunResult(1, "", "can't find", 1)
        raise AssertionError(a)


@pytest.fixture
def tmux(monkeypatch):
    from app.actions import runner
    fake = FakeTmux()
    monkeypatch.setattr(runner.Runner, "run", lambda self, tool, args, cwd=None: fake(self, tool, args, cwd))
    return fake


def start(authed, **params):
    return authed.post("/api/v1/actions/sessions.start", json={"params": params})


def test_start_claude_with_known_conversation_id(authed, tmux, project):
    r = start(authed, tool="claude", cwd=str(project), name="eyrie-abc123", conversation_id=CONV).json()
    assert r["ok"] is True
    argv = tmux.sessions["eyrie-abc123"]["argv"]
    i = argv.index("-c")
    # command goes in as separate args (tmux execs it directly, no shell)
    assert argv[i + 1:i + 4] == [str(project), "/fake/bin/claude", "--session-id"] and argv[i + 4] == CONV
    s = authed.get("/api/v1/sources/sessions").json()["sessions"][0]
    assert (s["name"], s["tool"], s["cwd"], s["conversation_id"], s["alive"]) == ("eyrie-abc123", "claude", str(project), CONV, True)
    assert s["attach"] == "tmux -L eyrie attach -t eyrie-abc123"


def test_eyrie_uses_private_socket_and_conf(authed, tmux, project, settings):
    start(authed, tool="claude", cwd=str(project))
    tool, args = tmux.calls[-2]  # new-session, then verify's list-sessions
    assert args[:4] == ["-L", "eyrie", "-f", str(settings.paths.data_dir / "tmux.conf")]
    conf = (settings.paths.data_dir / "tmux.conf").read_text()
    assert "remain-on-exit on" in conf
    assert "set -g status-right \" #{session_name} · %H:%M \"" in conf  # not the default: the hostname


@pytest.mark.parametrize("params,argv_tail", [
    ({"tool": "claude", "mode": "continue"}, ["/fake/bin/claude", "--continue"]),
    ({"tool": "claude", "mode": "resume", "resume_id": CONV}, ["/fake/bin/claude", "--resume", CONV]),
    ({"tool": "codex"}, ["/fake/bin/codex", "--cd", "{cwd}"]),
    ({"tool": "codex", "mode": "continue"}, ["/fake/bin/codex", "--cd", "{cwd}", "resume", "--last"]),
    ({"tool": "codex", "mode": "resume", "resume_id": CONV}, ["/fake/bin/codex", "--cd", "{cwd}", "resume", CONV]),
])
def test_modes(authed, tmux, project, params, argv_tail):
    r = authed.post("/api/v1/actions/sessions.start",
                    json={"params": {**params, "cwd": str(project), "name": "eyrie-m0de"}, "dry_run": True}).json()
    cmd_start = r["argv"].index("-c") + 2
    expected = [a.replace("{cwd}", str(project)) for a in argv_tail]
    assert r["argv"][cmd_start:cmd_start + len(expected)] == expected
    assert tmux.sessions == {}  # dry run ran nothing


def test_directory_must_be_allowed(authed, tmux, tmp_path):
    other = tmp_path / "random"
    other.mkdir()
    r = start(authed, tool="claude", cwd=str(other))
    assert r.status_code == 409 and "isn't an allowed directory" in r.json()["detail"]
    assert not any(a[4] == "new-session" for _, a in tmux.calls)


def test_roots_allow_subdirectories(settings, tmux, tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Sessions
    from app.main import create_app
    root = tmp_path / "projects"
    (root / "blog" / "src").mkdir(parents=True)
    s = settings.model_copy(update={"sessions": Sessions(roots=[root])})
    app = create_app(s)
    c = TestClient(app, base_url="http://localhost", headers={"X-Eyrie-Token": app.state.token})
    assert start(c, tool="claude", cwd=str(root / "blog" / "src")).json()["ok"] is True
    assert str(root / "blog") in c.get("/api/v1/sources/sessions").json()["dirs"]


@pytest.mark.parametrize("params,needle", [
    ({"tool": "claude", "cwd": "/x", "mode": "resume"}, "resume_id is required"),
    ({"tool": "claude", "cwd": "/x", "resume_id": CONV}, "only allowed there"),
    ({"tool": "claude", "cwd": "/x", "mode": "resume", "resume_id": "../../etc"}, "UUID"),
    ({"tool": "claude", "cwd": "/x", "name": "my-session"}, "eyrie-"),
    ({"tool": "codex", "cwd": "/x", "conversation_id": CONV}, "only applies"),
    ({"tool": "bash", "cwd": "/x"}, "claude"),
])
def test_invalid_start_params(authed, tmux, params, needle):
    r = start(authed, **params)
    assert r.status_code == 422 and needle in str(r.json()["detail"])


def test_duplicate_name_refused(authed, tmux, project):
    start(authed, tool="claude", cwd=str(project), name="eyrie-dup1")
    r = start(authed, tool="claude", cwd=str(project), name="eyrie-dup1")
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_stop_needs_confirm_and_kills(authed, tmux, project):
    start(authed, tool="claude", cwd=str(project), name="eyrie-stop1")
    r = authed.post("/api/v1/actions/sessions.stop", json={"params": {"name": "eyrie-stop1"}})
    assert r.status_code == 428 and r.json()["detail"]["argv"][-3:] == ["kill-session", "-t", "eyrie-stop1"]
    r = authed.post("/api/v1/actions/sessions.stop", json={"params": {"name": "eyrie-stop1"}, "confirm": True}).json()
    assert r["ok"] is True and "eyrie-stop1" not in tmux.sessions
    r = authed.post("/api/v1/actions/sessions.stop", json={"params": {"name": "eyrie-stop1"}, "confirm": True})
    assert r.status_code == 409


def test_stop_only_eyrie_sessions(authed, tmux):
    r = authed.post("/api/v1/actions/sessions.stop", json={"params": {"name": "main"}, "confirm": True})
    assert r.status_code == 422


def test_screen(authed, tmux, project):
    start(authed, tool="claude", cwd=str(project), name="eyrie-scr1")
    assert authed.get("/api/v1/sessions/eyrie-scr1/screen").json() == {"name": "eyrie-scr1", "text": "screen of eyrie-scr1"}
    assert authed.get("/api/v1/sessions/eyrie-none/screen").status_code == 404
    assert authed.get("/api/v1/sessions/..%2Fetc/screen").status_code == 404


def test_no_server_means_no_sessions(client, tmux):
    assert client.get("/api/v1/sources/sessions").json()["sessions"] == []


def test_recent_conversations_from_usage_index(client, home):
    from tests.test_usage import assistant, write
    write(home / ".claude/projects/-p/s1.jsonl", [assistant("m1", session=CONV, cwd="/p/eyrie")])
    convs = client.get("/api/v1/sessions/conversations").json()
    assert [(c["id"], c["project"], c["messages"]) for c in convs] == [(CONV, "/p/eyrie", 1)]


def test_codex_threads_include_id(client, home):
    db = home / ".codex/state_5.sqlite"
    db.parent.mkdir()
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE threads (id TEXT, cwd TEXT, model TEXT, tokens_used INT, created_at INT, updated_at INT, "
                    "reasoning_effort TEXT, title TEXT, archived INT)")
        con.execute("INSERT INTO threads VALUES (?, '/p', 'gpt', 1, 1, 2, 'low', 't', 0)", (CONV,))
    assert client.get("/api/v1/sources/codex").json()["threads"][0]["id"] == CONV
