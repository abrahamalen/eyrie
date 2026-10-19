import json
import os
import time

import pytest

from app.sessions import external
from app.sessions.external import ExternalSessions, parse_ps, transcript_dir

UUID = "516f62bf-361d-40b5-9698-9d33633899d1"

MAC_PS = f"""\
 9422 ??       7-14:51:59 /Users/me/.local/bin/claude daemon run --json-path /Users/me/.claude/daemon.json
11080 ??          07:39:10 claude bg-pty-host --bg-pty-host /tmp/cc/722.pty.sock 200 50 -- /x/claude
21016 ttys014  3-07:16:43 claude bg-spare --bg-spare /tmp/cc/15c.claim.sock
16675 ??       6-08:23:32 /Users/me/.codex/packages/codex app-server daemon pid-update-loop
10351 ttys000     07:39:38 claude --resume datadog
 9871 ttys004     07:39:53 claude --resume {UUID}
20387 ttys001  6-08:16:22 codex resume --all
33912 ttys015  6-04:35:41 codex
55555 ttys016        00:42 claude -p summarise the secret plan for me
44444 ttys017        01:00 vim notes.md
"""

LINUX_PS = """\
 1201 ?              2-01:00:00 /home/me/.local/bin/claude daemon run
 2202 pts/3              05:12 claude
 3303 pts/4           01:02:03 /usr/local/bin/codex resume 019a2f00-0000-0000-0000-000000000000
"""


def test_parse_mac_ps_keeps_interactive_sessions_only():
    got = [(p["pid"], p["tool"], p["tty"], p["resume"]) for p in parse_ps(MAC_PS)]
    assert got == [(10351, "claude", "ttys000", "datadog"), (9871, "claude", "ttys004", UUID),
                   (20387, "codex", "ttys001", None), (33912, "codex", "ttys015", None),
                   (55555, "claude", "ttys016", None)]


def test_prompt_text_is_never_captured():
    p = next(x for x in parse_ps(MAC_PS) if x["pid"] == 55555)
    assert "secret" not in json.dumps(p)


def test_parse_linux_ps_and_etime():
    got = {p["pid"]: p for p in parse_ps(LINUX_PS)}
    assert set(got) == {2202, 3303}
    assert got[2202]["age_seconds"] == 5 * 60 + 12 and got[3303]["age_seconds"] == 3723
    assert got[3303]["resume"] == "019a2f00-0000-0000-0000-000000000000"
    assert parse_ps(MAC_PS)[0]["age_seconds"] == 7 * 3600 + 39 * 60 + 38


def test_transcript_dir_matches_claude_naming(tmp_path):
    assert transcript_dir(tmp_path, "/Users/me/workspace/Obsidian Vault").name == "-Users-me-workspace-Obsidian-Vault"


@pytest.fixture
def machine(settings, monkeypatch, home):
    """A fake process table + cwds + transcripts."""
    proj = "/Users/me/workspace/repos/qureai"
    tdir = transcript_dir(settings.paths.claude_home, proj)
    tdir.mkdir(parents=True)
    exact = tdir / f"{UUID}.jsonl"
    exact.write_text("{}\n")
    other = tdir / "zzzz.jsonl"
    other.write_text("{}\n")
    old = time.time() - 3600
    os.utime(exact, (old, old))  # this conversation was last active an hour ago
    monkeypatch.setattr(external, "_ps", lambda: MAC_PS)
    monkeypatch.setattr(external, "_cwds", lambda pids: {9871: proj, 10351: proj, 20387: "/Users/me", 33912: "/x"})
    return settings


def test_activity_exact_by_resume_id_else_newest_in_project(machine):
    by = {s["pid"]: s for s in ExternalSessions(machine).list()}
    assert by[9871]["activity_exact"] is True and 59 <= by[9871]["idle_minutes"] <= 61
    assert by[10351]["activity_exact"] is False and by[10351]["idle_minutes"] == 0  # newest file in the project
    assert by[33912]["last_activity"] is None


def test_eyrie_managed_panes_excluded(machine):
    pids = {s["pid"] for s in ExternalSessions(machine).list(exclude_pids={9871})}
    assert 9871 not in pids and 10351 in pids


def test_summary_lists_terminal_sessions_but_never_flags_them_idle(machine, monkeypatch):
    from fastapi.testclient import TestClient
    from app.actions import runner
    from app.actions.runner import RunResult
    from app.main import create_app

    def run(self, tool, args, cwd=None):
        if args in (["-V"], ["--version"]):
            return RunResult(0, "1.0", "", 1)
        return RunResult(1, "", "no server running", 1)  # no Eyrie sessions

    monkeypatch.setattr(runner.Runner, "run", run)
    c = TestClient(create_app(machine), base_url="http://localhost")
    s = c.get("/api/v1/summary").json()
    ext = [x for x in s["sessions"] if not x["managed"]]
    assert len(ext) == 5 and {x["tty"] for x in ext} >= {"ttys000", "ttys004"}
    assert not any(a["kind"] == "session_idle" for a in s["attention"])
    snap = c.get("/api/v1/sources/sessions").json()
    assert len(snap["external"]) == 5
