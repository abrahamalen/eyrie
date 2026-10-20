"""Stopping external sessions and idle suggestions (docs/stop-and-idle.md).

Signals only ever reach processes these tests spawn themselves (conftest's `spawn` and its
signal guard): throwaway `sleep`s dressed up as `claude` with `exec -a`.
"""
import json
import os
import signal
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.actions import runner
from app.actions.runner import RunResult
from app.config import Settings
from app.main import create_app
from app.sessions import external, idle, procs
from app.tools.claude import transcript_dir
from app.usage.index import UsageIndex

UUID = "516f62bf-361d-40b5-9698-9d33633899d1"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def real_stats():
    return procs._run_ps(["-axo", "pid=,ppid=,uid=,rss=,lstart="])


# ---------- ps parsing ------------------------------------------------------------------------

MAC_STATS = """\
    1     0     0  13456 Mon Oct 19 08:00:01 2026
 9871  9800   502 402112 Sat Oct 17 21:03:44 2026
 9901  9871   502  51200 Sat Oct 17 21:03:46 2026
 9902  9871   502  20480 Sat Oct 17 21:03:46 2026
 9950  9901   502   4096 Sun Oct 18 09:12:00 2026
 4444     1     0   1024 Tue Oct  6 07:05:09 2026
garbage line
"""
# procs pads single-digit days the same way; uid 1000 is the usual first user.
LINUX_STATS = " 2202  2100  1000 300000 Tue Oct  6 07:05:09 2026\n 2210  2202  1000  1000 Tue Oct  6 07:05:10 2026\n"


def test_parse_stats_mac_and_linux():
    t = procs.parse_stats(MAC_STATS)
    assert set(t) == {1, 9871, 9901, 9902, 9950, 4444}
    assert t[9871] == procs.Proc(9871, 9800, 502, 402112, int(datetime(2026, 10, 17, 21, 3, 44).timestamp()))
    assert t[4444].started == int(datetime(2026, 10, 6, 7, 5, 9).timestamp())
    lx = procs.parse_stats(LINUX_STATS)
    assert lx[2202].uid == 1000 and lx[2210].ppid == 2202


def test_descendants_and_resources():
    t = procs.parse_stats(MAC_STATS)
    assert procs.descendants(t, 9871) == [9901, 9902, 9950]
    assert procs.resources(t, 9871) == {"rss_bytes": (402112 + 51200 + 20480 + 4096) * 1024, "child_processes": 3}
    assert procs.resources(t, 31337) == {"rss_bytes": None, "child_processes": None}
    assert procs.resources(t, None)["rss_bytes"] is None


def test_parse_identity_and_check():
    out = "  502 S+   Sat Oct 17 21:03:44 2026     claude --resume x\n"
    ident = procs.parse_identity(out)
    started = int(datetime(2026, 10, 17, 21, 3, 44).timestamp())
    assert ident == procs.Identity(502, started, "S+", "claude --resume x")
    is_claude = lambda c: external.tool_of(c) == "claude"  # noqa: E731
    assert procs.check(procs.Expect(9871, 502, started, is_claude), ident) is None
    assert procs.check(procs.Expect(9871, 501, started, is_claude), ident) == "reused"  # other uid
    assert procs.check(procs.Expect(9871, 502, started + 1, is_claude), ident) == "reused"  # pid reuse
    assert procs.check(procs.Expect(9871, 502, started, lambda c: False), ident) == "reused"  # not that tool now
    assert procs.check(procs.Expect(9871, 502, started, is_claude), None) == "already_exited"
    zombie = procs.Identity(502, started, "Z", "")
    assert procs.check(procs.Expect(9871, 502, started, is_claude), zombie) == "already_exited"
    assert procs.parse_identity("") is None


def test_tool_of():
    assert external.tool_of("claude --resume x") == "claude"
    assert external.tool_of("/Users/me/.local/bin/claude daemon run") is None  # a helper
    assert external.tool_of("node /opt/gemini/bin/gemini") == "gemini"
    assert external.tool_of("vim") is None and external.tool_of("") is None


def test_never_signals_protected_pids():
    for pid in (0, -1, 1, os.getpid(), os.getppid()):
        assert procs.protected(pid)
    assert not procs.protected(424242)


def test_the_guard_refuses_pids_tests_didnt_spawn():
    with pytest.raises(AssertionError, match="didn't spawn"):
        procs._kill(os.getppid(), 0)


# ---------- signalling a real throwaway process -------------------------------------------

def fake_claude(spawn, ignore_term=False, child=False):
    script = ("trap '' TERM; " if ignore_term else "") + ("sleep 3 & " if child else "") + "exec -a claude sleep 60"
    p = spawn(["/bin/bash", "-c", script])
    for _ in range(50):
        ident = procs.identity(p.pid)
        if ident and ident.command.startswith("claude"):
            return p, ident
        time.sleep(0.05)
    raise AssertionError("fake claude didn't start")


def expect(p, ident):
    return procs.Expect(p.pid, os.getuid(), ident.started, lambda c: external.tool_of(c) == "claude")


def test_sigterm_stops_it(spawn):
    p, ident = fake_claude(spawn)
    o = procs.stop(expect(p, ident), signal.SIGTERM, 3, {})
    assert o.state == "exited" and o.seconds < 3
    assert p.wait(timeout=2) == -signal.SIGTERM


def test_ignores_sigterm_then_force(spawn):
    p, ident = fake_claude(spawn, ignore_term=True)
    o = procs.stop(expect(p, ident), signal.SIGTERM, 0.6, {})
    assert o.state == "still_running" and p.poll() is None
    o = procs.stop(expect(p, ident), signal.SIGKILL, 3, {})
    assert o.state == "exited" and p.wait(timeout=2) == -signal.SIGKILL


def test_already_exited_is_not_signalled(spawn):
    p, ident = fake_claude(spawn)
    p.kill()
    p.wait()
    assert procs.stop(expect(p, ident), signal.SIGTERM, 1, {}).state == "already_exited"


def test_pid_reuse_mismatch_is_not_signalled(spawn):
    p, ident = fake_claude(spawn)
    wrong = procs.Expect(p.pid, os.getuid(), ident.started - 60, lambda c: True)
    assert procs.stop(wrong, signal.SIGTERM, 1, {}).state == "reused"
    assert p.poll() is None  # untouched


def test_children_outliving_it_are_reported_not_signalled(spawn, monkeypatch):
    monkeypatch.setattr(procs, "_stats", real_stats)
    p, ident = fake_claude(spawn, child=True)
    table = procs.stats()
    kids = {c: table[c].started for c in procs.descendants(table, p.pid)}
    assert len(kids) == 1
    o = procs.stop(expect(p, ident), signal.SIGTERM, 3, kids)
    assert o.state == "exited" and o.survivors == list(kids)


def test_permission_denied(spawn, monkeypatch):
    p, ident = fake_claude(spawn)

    def denied(pid, sig, pidfd=None):
        raise PermissionError()

    monkeypatch.setattr(procs, "_kill", denied)
    assert procs.stop(expect(p, ident), signal.SIGTERM, 1, {}).state == "denied"


# ---------- the action ------------------------------------------------------------------------

def no_tmux(self, tool, args, cwd=None):
    if args in (["-V"], ["--version"]):
        return RunResult(0, "1.0", "", 1)
    return RunResult(1, "", "no server running", 1)


@pytest.fixture
def listed(spawn, settings, monkeypatch, home):
    """A throwaway `claude` listed as an external session on ttys012, idle for two days."""
    p, ident = fake_claude(spawn)
    proj = str(home / "proj")
    tdir = transcript_dir(settings.paths.claude_home, proj)
    tdir.mkdir(parents=True)
    t = tdir / f"{UUID}.jsonl"
    t.write_text("{}\n")
    old = time.time() - 2 * 86400
    os.utime(t, (old, old))
    monkeypatch.setattr(external, "_ps", lambda: f"{p.pid} 1 ttys012 2-00:00:00 claude --resume {UUID}\n")
    monkeypatch.setattr(external, "_cwds", lambda pids: {p.pid: proj})
    monkeypatch.setattr(procs, "_stats", real_stats)
    monkeypatch.setattr(runner.Runner, "run", no_tmux)
    settings.sessions.stop_wait_seconds = 1
    app = create_app(settings)
    c = TestClient(app, base_url="http://localhost", headers={"X-Eyrie-Token": app.state.token})
    started = datetime.fromtimestamp(ident.started, tz=timezone.utc).isoformat()
    return c, p, {"pid": p.pid, "tool": "claude", "tty": "ttys012", "started": started}


def stop(c, params, **body):
    return c.post("/api/v1/actions/sessions.stop_external", json={"params": params, **body})


def test_listing_has_identity_cost_and_idle(listed):
    c, p, params = listed
    x = c.get("/api/v1/sources/sessions").json()["external"][0]
    assert x["pid"] == p.pid and x["process_started"] == params["started"] and x["uid_ok"] is True
    assert x["resume_command"].endswith(f"claude --resume {UUID}")
    assert x["resources"]["rss_bytes"] > 0 and x["resources"]["child_processes"] == 0
    assert x["idle"]["idle"] is True and x["idle"]["suggested"] is True and x["idle"]["key"] == f"claude:{UUID}"
    assert x["idle"]["attached"] is None


def test_preview_then_confirm_then_stop(listed):
    c, p, params = listed
    r = stop(c, params, dry_run=True)
    assert r.status_code == 200 and r.json()["argv"] == ["kill", "-TERM", str(p.pid)] and r.json()["destructive"]
    assert stop(c, params).status_code == 428  # destructive: needs confirm
    assert p.poll() is None
    r = stop(c, params, confirm=True).json()
    assert r["ok"] is True and r["state"] == "exited" and r["message"].startswith(f"Stopped. Claude Code (pid {p.pid}) exited")
    assert p.wait(timeout=2) == -signal.SIGTERM
    entry = c.get("/api/v1/audit?limit=1").json()[0]
    assert entry["action"] == "sessions.stop_external" and entry["argv"] == ["kill", "-TERM", str(p.pid)]
    assert entry["params"]["started"] == params["started"].replace("+00:00", "Z")


@pytest.mark.parametrize("change", [{"pid": 31337}, {"tty": "ttys013"}, {"tool": "codex"}])
def test_only_the_listed_process(listed, change):
    c, p, params = listed
    r = stop(c, {**params, **change}, confirm=True)
    # (Codex isn't enabled in this home, so that one is refused even earlier.)
    assert r.status_code == 409 and ("isn't running any more" in r.json()["detail"] or "enabled" in r.json()["detail"])
    assert p.poll() is None


def test_pid_reuse_is_refused(listed):
    c, p, params = listed
    other = (datetime.fromisoformat(params["started"]) - timedelta(seconds=5)).isoformat()
    r = stop(c, {**params, "started": other}, confirm=True)
    assert r.status_code == 409 and "different process now" in r.json()["detail"]
    assert stop(c, {**params, "started": other}, dry_run=True).status_code == 409  # also before any preview
    assert p.poll() is None


def test_other_users_process_is_refused(listed, monkeypatch):
    c, p, params = listed
    monkeypatch.setattr(os, "getuid", lambda: os.geteuid() + 4242)
    r = stop(c, params, confirm=True)
    assert r.status_code == 409 and "belongs to another user" in r.json()["detail"]
    assert p.poll() is None


@pytest.mark.parametrize("bad", [{"pid": 1}, {"pid": -5}, {"tty": "ttys012;"}, {"started": "yesterday"},
                                 {"started": "2026-10-20T10:00:00"}, {"tool": "vim"}])
def test_bad_params(listed, bad):
    c, p, params = listed
    assert stop(c, {**params, **bad}, confirm=True).status_code == 422
    assert p.poll() is None


def test_force_sends_sigkill(spawn, listed, monkeypatch):
    c, p, params = listed
    r = stop(c, {**params, "force": True}, dry_run=True)
    assert r.json()["argv"] == ["kill", "-KILL", str(p.pid)]
    r = stop(c, {**params, "force": True}, confirm=True).json()
    assert r["state"] == "exited" and "after SIGKILL" in r["message"]
    assert p.wait(timeout=2) == -signal.SIGKILL


def test_still_running_offers_force(listed, monkeypatch):
    c, p, params = listed
    monkeypatch.setattr(procs, "_kill", lambda pid, sig, pidfd=None: None)  # it "ignores" SIGTERM
    r = stop(c, params, confirm=True).json()
    assert r["ok"] is False and r["state"] == "still_running" and "Still running 1 s after SIGTERM" in r["message"]
    r = stop(c, {**params, "force": True}, confirm=True).json()
    assert r["state"] == "stuck" and "after SIGKILL" in r["message"]


def test_needs_the_token(listed):
    c, p, params = listed
    plain = TestClient(c.app, base_url="http://localhost")
    assert plain.post("/api/v1/actions/sessions.stop_external",
                      json={"params": params, "confirm": True}).status_code in (401, 403)
    assert p.poll() is None


# ---------- snoozes -----------------------------------------------------------------------------

def test_snooze_endpoints(listed):
    c, p, params = listed
    key = f"claude:{UUID}"
    assert c.get("/api/v1/summary").json()["suggestions"]["count"] == 1
    r = c.put(f"/api/v1/suggestions/{key}", json={"snooze": "1d"})
    assert r.status_code == 200 and r.json()["until"]
    x = c.get("/api/v1/sources/sessions").json()["external"][0]["idle"]
    assert x["suggested"] is False and x["snoozed_until"] == r.json()["until"]
    assert c.get("/api/v1/summary").json()["suggestions"]["count"] == 0
    assert c.delete(f"/api/v1/suggestions/{key}").json() == {"status": "ok"}
    assert c.delete(f"/api/v1/suggestions/{key}").status_code == 404
    assert c.put("/api/v1/suggestions/claude:..%2F", json={"snooze": "1d"}).status_code in (404, 422)
    assert c.put("/api/v1/suggestions/rm -rf", json={"snooze": "1d"}).status_code == 422
    assert c.put("/api/v1/suggestions/claude:nope", json={"snooze": "1d"}).status_code == 404
    assert c.put(f"/api/v1/suggestions/{key}", json={"snooze": "forever"}).status_code == 422
    plain = TestClient(c.app, base_url="http://localhost")
    assert plain.put(f"/api/v1/suggestions/{key}", json={"snooze": "1d"}).status_code in (401, 403)


def test_snooze_store(tmp_path):
    s = idle.Snoozes(tmp_path / "eyrie" / "suggestions.json")
    seen = NOW - timedelta(days=2)
    s.set("eyrie:eyrie-7f3a", "7d", seen.isoformat(), NOW)
    s.set("pid:4242:1792000000", "dismiss", seen.isoformat(), NOW)
    items = s.load()
    assert idle.Snoozes.state(items["eyrie:eyrie-7f3a"], seen, NOW + timedelta(days=1))[0]  # snoozed
    assert idle.Snoozes.state(items["eyrie:eyrie-7f3a"], seen, NOW + timedelta(days=8)) == (None, False)  # expired
    assert idle.Snoozes.state(items["pid:4242:1792000000"], seen, NOW) == (None, True)  # dismissed
    assert idle.Snoozes.state(items["pid:4242:1792000000"], NOW, NOW) == (None, False)  # used again since
    assert idle.Snoozes.state(None, seen, NOW) == (None, False)
    with pytest.raises(ValueError):
        s.set("../../etc", "1d", None, NOW)
    with pytest.raises(ValueError):
        s.set("eyrie:eyrie-7f3a", "1y", None, NOW)
    # Expired snoozes set more than 30 days ago are dropped on the next write.
    s.set("codex:abc", "1d", None, NOW + timedelta(days=40))
    assert "eyrie:eyrie-7f3a" not in s.load() and "pid:4242:1792000000" in s.load()
    assert s.clear("codex:abc") and not s.clear("codex:abc")


def test_snooze_store_tolerates_a_bad_file(tmp_path):
    path = tmp_path / "suggestions.json"
    s = idle.Snoozes(path)
    assert s.load() == {}
    path.write_text("{not json")
    assert s.load() == {}
    path.write_text(json.dumps({"items": {"../x": {}, "eyrie:eyrie-7f3a": "no", "codex:a": {"until": None}}}))
    assert s.load() == {"codex:a": {"until": None}}


# ---------- idle computation -----------------------------------------------------------------

class FakeIndex:
    def __init__(self, turns):
        self.turns = turns

    def last_turns(self, keys):
        return {k: v for k, v in self.turns.items() if k in keys}


def ext(minutes, conv="c1", tool="claude", exact=True, pid=4242):
    return {"pid": pid, "tool": tool, "name_exact": exact, "conversation_id": conv,
            "activity_at": (NOW - timedelta(minutes=minutes)).isoformat(), "activity_exact": exact,
            "process_started": "2026-10-01T00:00:00+00:00", "started": "2026-10-01T00:00:00+00:00"}


def run_idle(settings, tmp_path, sessions, turns=None, managed=()):
    idle.annotate(settings, list(managed), sessions, procs.parse_stats(MAC_STATS), FakeIndex(turns or {}),
                  idle.Snoozes(tmp_path / "s.json"), NOW)
    return sessions


def test_idle_threshold_boundaries(settings, tmp_path):
    a, b, c = run_idle(settings, tmp_path, [ext(24 * 60 - 1), ext(24 * 60), ext(5, pid=9871)])
    assert a["idle"]["idle"] is False and b["idle"]["idle"] is True and b["idle"]["suggested"] is True
    assert c["resources"]["child_processes"] == 3 and c["idle"]["minutes"] == 5
    settings.sessions.idle_hours = 2
    (d,) = run_idle(settings, tmp_path, [ext(130)])
    assert d["idle"]["suggested"] is True


def test_unknown_activity_is_never_idle(settings, tmp_path):
    s = ext(5000)
    s["activity_at"] = None
    (s,) = run_idle(settings, tmp_path, [s])
    assert s["idle"] is None


def test_eyrie_sessions_and_attached(settings, tmp_path):
    m = {"name": "eyrie-7f3a", "tool": "claude", "alive": True, "attached": 1, "pid": 9871, "conversation_id": "c9",
         "activity_at": (NOW - timedelta(days=3)).isoformat()}
    dead = {**m, "name": "eyrie-dead0", "alive": False}
    run_idle(settings, tmp_path, [], managed=[m, dead])
    assert m["idle"]["key"] == "eyrie:eyrie-7f3a" and m["idle"]["attached"] is True and m["idle"]["suggested"] is True
    assert dead["idle"] is None and dead["resources"]["rss_bytes"] is None
    settings.sessions.idle_requires_detached = True
    run_idle(settings, tmp_path, [], managed=[m])
    assert m["idle"]["idle"] is True and m["idle"]["suggested"] is False
    (x,) = run_idle(settings, tmp_path, [ext(3000)])  # attachment unknown: doesn't block
    assert x["idle"]["suggested"] is True


def turn(minutes_ago, tokens, wrote_1h=False):
    return {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "context_tokens": tokens, "wrote_1h": wrote_1h}


def test_context_hint(settings, tmp_path):
    day = 24 * 60
    rows = run_idle(settings, tmp_path, [
        ext(2 * day, "big"), ext(2 * day, "small"), ext(2 * day, "guess", exact=False),
        ext(2 * day, "cx", tool="codex"), ext(2 * day, "gm", tool="gemini"), ext(30, "fresh"), ext(2 * day, "none"),
    ], {("claude", "big"): turn(2 * day, 142_000), ("claude", "small"): turn(2 * day, 40_000),
        ("claude", "guess"): turn(2 * day, 300_000), ("codex", "cx"): turn(2 * day, 150_000),
        ("gemini", "gm"): turn(2 * day, 150_000), ("claude", "fresh"): turn(30, 150_000, wrote_1h=True)})
    big, small, guess, cx, gm, fresh, none = (r["idle"] for r in rows)
    assert (big["context_tokens"], big["cache_expired"], big["compact_command"]) == (142_000, True, "/compact")
    assert small["compact_command"] is None and small["context_tokens"] == 40_000
    assert guess["context_tokens"] is None  # an approximate conversation: no numbers at all
    assert cx["compact_command"] == "/compact"
    assert gm["context_tokens"] == 150_000 and gm["cache_expired"] is None and gm["compact_command"] is None
    assert fresh["cache_expired"] is False and fresh["compact_command"] is None  # within the 1 h cache
    assert none["context_tokens"] is None and none["compact_command"] is None


def test_cache_lifetime_5m_vs_1h(settings):
    t5, t1 = {("claude", "a"): turn(30, 200_000)}, {("claude", "a"): turn(30, 200_000, wrote_1h=True)}
    assert idle.context_hint("claude", "a", True, t5, NOW, settings, True)["cache_expired"] is True
    assert idle.context_hint("claude", "a", True, t1, NOW, settings, True)["cache_expired"] is False


def test_last_turns_from_the_usage_index(settings, tmp_path):
    ix = UsageIndex(tmp_path / "usage.db", {}, settings)
    assert ix.last_turns([("claude", "s1")]) == {}  # no DB yet: nothing, and none created
    assert not (tmp_path / "usage.db").exists()
    with closing(ix.connect()) as con, con:
        con.executemany("INSERT INTO messages (key, ts, session_id, project, model, subagent, input, output, cache_read, "
                        "cache_write_5m, cache_write_1h, tool) VALUES (?, ?, 's1', '/p', 'm', ?, ?, 9, ?, ?, ?, 'claude')", [
                            ("a", "2026-10-18T10:00:00Z", 0, 10, 1000, 0, 0),
                            ("b", "2026-10-18T11:00:00Z", 0, 20, 140_000, 500, 100),
                            ("c", "2026-10-18T12:00:00Z", 1, 5, 9, 0, 0),  # a subagent's turn doesn't count
                        ])
    got = ix.last_turns([("claude", "s1"), ("claude", "s2")])
    assert got == {("claude", "s1"): {"ts": "2026-10-18T11:00:00Z", "context_tokens": 140_620, "wrote_1h": True}}
    with closing(sqlite3.connect(tmp_path / "usage.db")) as con:
        assert con.execute("SELECT count(*) FROM messages").fetchone()[0] == 3


def test_suggestion_keys():
    assert idle.session_key({"name": "eyrie-7f3a"}, True) == "eyrie:eyrie-7f3a"
    assert idle.session_key(ext(1, UUID), False) == f"claude:{UUID}"
    guess = idle.session_key(ext(1, UUID, exact=False), False)
    assert guess == f"pid:4242:{int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())}"
    assert all(idle.KEY_RE.match(k) for k in (guess, f"claude:{UUID}", "eyrie:eyrie-7f3a"))


# ---------- config and settings ----------------------------------------------------------------

def test_threshold_from_toml(tmp_path, monkeypatch):
    cfg = tmp_path / "eyrie.toml"
    cfg.write_text("[sessions]\nidle_hours = 6\nlarge_context_tokens = 50000\nstop_wait_seconds = 2\n")
    monkeypatch.setenv("EYRIE_CONFIG", str(cfg))
    s = Settings()
    assert (s.sessions.idle_hours, s.sessions.large_context_tokens, s.sessions.stop_wait_seconds) == (6, 50000, 2)
    cfg.write_text("[sessions]\nidle_hours = 0\n")
    with pytest.raises(ValueError):
        Settings()


def test_settings_page_saves_the_threshold(authed, monkeypatch, tmp_path):
    state = authed.get("/api/v1/setup").json()
    assert state["idle_hours"] == 24
    body = {"tools_enabled": "auto", "roots": [], "idle_hours": 48}
    r = authed.put("/api/v1/setup", json=body, headers={"If-Match": state["config"]["etag"]})
    assert r.status_code == 200 and r.json()["idle_hours"] == 48
    assert "idle_hours = 48" in open(r.json()["config"]["path"]).read()
    bad = authed.put("/api/v1/setup", json={**body, "idle_hours": 0}, headers={"If-Match": r.json()["config"]["etag"]})
    assert bad.status_code == 422
    # Leaving it out keeps the current value.
    r2 = authed.put("/api/v1/setup", json={"tools_enabled": "auto", "roots": []}, headers={"If-Match": r.json()["config"]["etag"]})
    assert r2.json()["idle_hours"] == 48
