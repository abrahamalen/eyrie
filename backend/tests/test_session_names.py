"""Session names per tool (docs/session-names-and-jump.md §3), from fixture files shaped like
each tool's real ones."""
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.sessions import external
from app.sessions.external import ExternalSessions, session_href
from app.sessions.names import Name, clean, display, resume_command, short_id, tail_records
from app.sessions.source import name_managed
from app.tools import TOOLS
from app.tools.claude import transcript_dir

CLAUDE_ID = "6636c681-a73f-4aa7-a8cb-c8e1f313d9ee"
CODEX_ID = "01a13480-5390-7ed3-85c3-0e32b8d04c8e"  # UUIDv7
GEMINI_ID = "5f2c9a1e-0b6d-4c1e-9f3a-2d4b6c8e0a1b"
PROJ = "/Users/me/work/eyrie"
NOW = datetime.now(timezone.utc)


def claude_names(settings):
    return TOOLS["claude"].sessions.names(settings)


def write_pid_file(settings, pid, **fields):
    d = settings.paths.claude_home / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps({"pid": pid, "sessionId": CLAUDE_ID, "cwd": PROJ, "kind": "interactive", **fields}))


def write_transcript(settings, lines, conv=CLAUDE_ID):
    d = transcript_dir(settings.paths.claude_home, PROJ)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{conv}.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" if isinstance(x, dict) else x + "\n" for x in lines))
    return path


# --- shared rules -------------------------------------------------------------------------

def test_short_id_uses_the_random_end_of_uuid7():
    assert short_id(CLAUDE_ID) == "6636c681"
    assert short_id(CODEX_ID) == CODEX_ID[-8:]
    assert short_id("not-a-uuid-at-all") == "not-a-uu"


def test_clean_strips_control_characters_and_caps_length():
    assert clean("build\x1b[31m-eyrie\n") == "build [31m-eyrie"
    assert clean("a b") == "a b"
    assert len(clean("x" * 500)) == 80
    assert clean("   ") is None and clean(42) is None


def test_fallback_order():
    assert display(Name(CLAUDE_ID, "build-eyrie", "user"), "eyrie-7f3a") == ("build-eyrie", "user")
    assert display(Name(CLAUDE_ID, "Repo run", "tool"), "eyrie-7f3a") == ("Repo run", "tool")
    assert display(Name(CLAUDE_ID), "eyrie-7f3a") == ("6636c681", "id")
    assert display(Name(), "eyrie-7f3a") == ("eyrie-7f3a", "none")


def test_tail_reads_only_the_end_and_skips_bad_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    early = json.dumps({"type": "custom-title", "customTitle": "early"})
    p.write_text(early + "\n" + "x" * 2000 + "\n{bad json\n" + json.dumps({"type": "custom-title", "customTitle": "late"}) + "\n")
    got = tail_records(p, max_bytes=500)
    assert [r["customTitle"] for r in got] == ["late"]
    assert [r["customTitle"] for r in tail_records(p, max_bytes=10**6, needle=b"Title")] == ["early", "late"]


def test_resume_command_is_quoted_and_per_tool():
    assert resume_command("claude", "/Users/me/My Work", CLAUDE_ID) == f"cd '/Users/me/My Work' && claude --resume {CLAUDE_ID}"
    assert resume_command("codex", PROJ, CODEX_ID) == f"cd {PROJ} && codex --cd {PROJ} resume {CODEX_ID}"
    assert resume_command("gemini", PROJ, GEMINI_ID) == f"cd {PROJ} && gemini --resume {GEMINI_ID}"
    assert resume_command("claude", PROJ, "$(rm -rf ~)") is None
    assert resume_command("claude", None, CLAUDE_ID) is None


# --- Claude Code --------------------------------------------------------------------------

@pytest.mark.parametrize("source,want", [("user", "user"), ("auto", "tool"), ("derived", "tool")])
def test_claude_pid_file_name(settings, source, want):
    write_pid_file(settings, 4242, name="build-eyrie", nameSource=source)
    assert claude_names(settings)(4242, PROJ, None, None, NOW) == Name(CLAUDE_ID, "build-eyrie", want)


def test_claude_pid_file_without_a_name_falls_back_to_the_transcript(settings):
    write_pid_file(settings, 4242, name=CLAUDE_ID[:8])  # no nameSource: the id prefix isn't a name
    write_transcript(settings, [{"type": "ai-title", "aiTitle": "Repo run"}])
    assert claude_names(settings)(4242, PROJ, None, None, NOW) == Name(CLAUDE_ID, "Repo run", "tool")


def test_claude_pid_file_for_another_pid_is_ignored(settings):
    write_pid_file(settings, 4242, name="stale", nameSource="user")
    (settings.paths.claude_home / "sessions" / "5151.json").write_text(
        (settings.paths.claude_home / "sessions" / "4242.json").read_text())
    assert claude_names(settings)(5151, PROJ, None, None, NOW) == Name()


def test_claude_transcript_custom_title_beats_ai_title_and_last_wins(settings):
    write_transcript(settings, [
        {"type": "custom-title", "customTitle": "first-name", "sessionId": CLAUDE_ID},
        {"type": "user", "message": {"content": "hello"}},
        {"type": "ai-title", "aiTitle": "Repo run", "sessionId": CLAUDE_ID},
        {"type": "custom-title", "customTitle": "build-eyrie", "sessionId": CLAUDE_ID},
        "{truncated",
    ])
    assert claude_names(settings)(None, PROJ, CLAUDE_ID, None, NOW) == Name(CLAUDE_ID, "build-eyrie", "user")


def test_claude_resume_by_name_or_id(settings):
    look = claude_names(settings)
    assert look(None, PROJ, None, "datadog", NOW) == Name(None, "datadog", "user")
    assert look(None, PROJ, None, CLAUDE_ID, NOW) == Name(CLAUDE_ID)


def test_claude_title_outside_the_tail_window_is_not_read(settings):
    write_transcript(settings, [{"type": "custom-title", "customTitle": "too-early"}, "{}" * 200_000])
    assert claude_names(settings)(None, PROJ, CLAUDE_ID, None, NOW) == Name(CLAUDE_ID)


# --- Codex --------------------------------------------------------------------------------

def codex_home(settings, threads=(), index=()):
    home = settings.paths.codex_home
    home.mkdir(parents=True, exist_ok=True)
    (home / "session_index.jsonl").write_text("".join(json.dumps(x) + "\n" for x in index) + "not json\n")
    con = sqlite3.connect(home / "state_5.sqlite")
    con.execute("CREATE TABLE threads (id TEXT, cwd TEXT, updated_at INTEGER, title TEXT)")
    con.executemany("INSERT INTO threads VALUES (?, ?, ?, ?)", threads)
    con.commit()
    con.close()


def test_codex_name_from_session_index_last_line_wins(settings):
    codex_home(settings, index=[{"id": CODEX_ID, "thread_name": "Old"}, {"id": CODEX_ID, "thread_name": "deploy-app"}])
    look = TOOLS["codex"].sessions.names(settings)
    assert look(1, PROJ, None, CODEX_ID, NOW) == Name(CODEX_ID, "deploy-app", "tool")
    assert look(1, PROJ, None, "deploy-app", NOW) == Name(CODEX_ID, "deploy-app", "tool")


def test_codex_guesses_newest_thread_in_cwd_since_start_and_never_shows_prompts(settings):
    started = NOW - timedelta(minutes=10)
    other = "01a0f6aa-d133-7102-979a-7c982c57aea8"
    codex_home(settings, threads=[
        (other, PROJ, int((NOW - timedelta(days=1)).timestamp()), "old prompt"),
        (CODEX_ID, PROJ, int(NOW.timestamp()), "secret first prompt"),
    ])
    look = TOOLS["codex"].sessions.names(settings)
    got = look(1, PROJ, None, None, started)
    assert got == Name(CODEX_ID, None, "id", False)
    assert "secret" not in repr(got)
    assert look(1, PROJ, None, None, NOW + timedelta(minutes=1)) == Name()  # nothing touched since it started


# --- Gemini -------------------------------------------------------------------------------

def gemini_chats(settings):
    root = settings.paths.gemini_home
    chats = root / "tmp" / "eyrie" / "chats"
    chats.mkdir(parents=True)
    (root / "projects.json").write_text(json.dumps({"projects": {PROJ: "eyrie"}}))
    f = chats / f"session-2026-10-20T10-00-{GEMINI_ID[:8]}.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in [
        {"sessionId": GEMINI_ID, "projectHash": "h", "startTime": "2026-10-20T10:00:00Z", "kind": "main"},
        {"id": "m1", "type": "user", "content": "a prompt"},
        {"$set": {"summary": "Fix the flaky test"}},
        {"$set": {"lastUpdated": "2026-10-20T10:05:00Z"}},
    ]) + "\n")
    return f


def test_gemini_summary_by_id_and_by_recency(settings):
    gemini_chats(settings)
    look = TOOLS["gemini"].sessions.names(settings)
    assert look(1, PROJ, None, GEMINI_ID, NOW) == Name(GEMINI_ID, "Fix the flaky test", "tool")
    assert look(1, PROJ, None, None, NOW - timedelta(hours=1)) == Name(GEMINI_ID, "Fix the flaky test", "tool", False)
    assert look(1, "/elsewhere", None, None, NOW) == Name()


# --- listings -----------------------------------------------------------------------------

MAC_PS = """\
    1     0 ??       9-00:00:00 /sbin/launchd
  500     1 ??       1-00:00:00 /Applications/iTerm.app/Contents/MacOS/iTerm2
  510     1 ??       1-00:00:00 /Users/me/Library/Application Support/iTerm2/iTermServer-3.7.5 /x/iterm2-daemon-1.socket
  511   510 ttys004  1-00:00:00 /usr/bin/login -fpl me /bin/zsh
  512   511 ttys004  1-00:00:00 -zsh
 4242   512 ttys004     07:39:53 claude --resume build-eyrie
  600     1 ??       1-00:00:00 /Applications/Warp.app/Contents/MacOS/stable
  601   600 ttys015  1-00:00:00 /bin/zsh
 7001   601 ttys015     00:10:00 codex
 7002   601 ttys016     00:10:00 codex
"""


@pytest.fixture
def machine(settings, monkeypatch, home):
    (home / ".codex").mkdir(exist_ok=True)
    write_pid_file(settings, 4242, name="build-eyrie", nameSource="user")
    codex_home(settings, threads=[(CODEX_ID, "/w", int(time.time()), "prompt")])
    monkeypatch.setattr(external, "_ps", lambda: MAC_PS)
    monkeypatch.setattr(external, "_cwds", lambda pids: {4242: PROJ, 7001: "/w", 7002: "/w"})
    monkeypatch.setattr(external.focus.sys, "platform", "darwin")
    return settings


def test_external_listing_has_names_hosts_and_links(machine):
    by = {s["pid"]: s for s in ExternalSessions(machine).list()}
    s = by[4242]
    assert (s["display_name"], s["name_source"], s["conversation_id"]) == ("build-eyrie", "user", CLAUDE_ID)
    assert (s["terminal"], s["focus"]) == ("iTerm2", "tab")
    assert s["href"] == f"/sessions?ext=4242&tool=claude&id={CLAUDE_ID}"
    # Two Codex sessions in one directory would share the same guess: neither gets it.
    for pid, tty in ((7001, "ttys015"), (7002, "ttys016")):
        assert by[pid]["display_name"] == f"Codex · {tty}" and by[pid]["name_source"] == "none"
        assert (by[pid]["terminal"], by[pid]["focus"]) == ("Warp", "app")
        assert by[pid]["href"] == f"/sessions?ext={pid}&tool=codex"


def test_href_is_url_encoded():
    assert session_href(12, "claude", None) == "/sessions?ext=12&tool=claude"
    assert session_href(12, "claude", "a&b=c") == "/sessions?ext=12&tool=claude&id=a%26b%3Dc"


def test_eyrie_sessions_get_names_and_resume_commands(settings):
    write_transcript(settings, [{"type": "custom-title", "customTitle": "build-eyrie"}])
    base = {"cwd": PROJ, "created": NOW.isoformat(), "alive": False, "pid": None}
    got = name_managed(settings, [
        {**base, "name": "eyrie-7f3a", "tool": "claude", "conversation_id": CLAUDE_ID},
        {**base, "name": "eyrie-b40e", "tool": "claude", "conversation_id": "a98e1677-df83-4414-97c4-6ea3fdaf32b9"},
        {**base, "name": "eyrie-91d0", "tool": "gemini", "conversation_id": None},
        {**base, "name": "eyrie-0000", "tool": None, "conversation_id": None},
    ])
    assert [(s["display_name"], s["name_source"]) for s in got] == [
        ("build-eyrie", "user"), ("a98e1677", "id"), ("eyrie-91d0", "none"), ("eyrie-0000", "none")]
    assert got[0]["resume_command"] == f"cd {PROJ} && claude --resume {CLAUDE_ID}"
    assert got[2]["resume_command"] is None


def test_names_are_read_only(settings, tmp_path):
    path = write_transcript(settings, [{"type": "custom-title", "customTitle": "x"}])
    before = (path.stat().st_mtime_ns, path.read_bytes())
    os.chmod(path, 0o444)
    claude_names(settings)(None, PROJ, CLAUDE_ID, None, NOW)
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before
