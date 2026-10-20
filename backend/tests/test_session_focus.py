"""Jump to a session's terminal (docs/session-names-and-jump.md §5, §7): host detection, the
osascript/tmux argv (built, never executed here), and the action's validation."""
import pytest

from app.actions.runner import RunResult
from app.sessions import external, focus

MAC_PS = """\
    1     0 ??       9-00:00:00 /sbin/launchd
  500     1 ??       1-00:00:00 /Users/me/Library/Application Support/iTerm2/iTermServer-3.7.5 /x/daemon.socket
  501   500 ttys004  1-00:00:00 /usr/bin/login -fpl me /bin/zsh
  502   501 ttys004  1-00:00:00 -zsh
 4242   502 ttys004     07:39:53 claude --resume build-eyrie
  700     1 ??       1-00:00:00 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal
  701   700 ttys009  1-00:00:00 /usr/bin/login -pf me
  702   701 ttys009  1-00:00:00 -zsh
 4343   702 ttys009     00:01:00 claude
  600     1 ??       1-00:00:00 /Applications/Warp.app/Contents/MacOS/stable
  601   600 ttys015  1-00:00:00 /bin/zsh
 7001   601 ttys015     00:10:00 codex
  800     1 ??       1-00:00:00 tmux -L work new -s main
  801   800 ttys021  1-00:00:00 -zsh
 8001   801 ttys021     00:10:00 claude
  802   502 ttys004  1-00:00:00 tmux -L work attach
  900     1 ??       1-00:00:00 /usr/sbin/sshd -D
  901   900 ttys030  1-00:00:00 -zsh
 9001   901 ttys030     00:10:00 claude
"""


def table():
    return external.process_table(MAC_PS)


# --- host detection -----------------------------------------------------------------------

@pytest.mark.parametrize("pid,kind,mode", [(4242, "iterm", "tab"), (4343, "terminal", "tab"), (7001, "warp", "app"),
                                           (8001, "tmux", "pane"), (9001, "ssh", "none")])
def test_detect_hosts_on_macos(pid, kind, mode):
    host = focus.detect(table(), pid, "darwin")
    assert (host.kind, host.focus) == (kind, mode)


def test_tmux_socket_flags_are_kept_and_validated():
    assert focus.detect(table(), 8001, "darwin").tmux_args == ("-L", "work")
    assert focus.classify("tmux new -s x").tmux_args == ()
    assert focus.classify("tmux -S /tmp/../etc/x new").focus == "none"
    assert focus.classify("tmux -L bad;name new").focus == "none"


def test_linux_hosts_have_no_app_focus():
    assert focus.classify("/usr/libexec/gnome-terminal-server", "linux").focus == "none"
    assert focus.classify("/usr/bin/kitty", "linux").focus == "none"
    assert focus.classify("tmux", "linux").focus == "pane"
    assert focus.detect({5: (4, "claude"), 4: (1, "/bin/bash")}, 5, "linux") is focus.UNKNOWN


def test_detect_survives_cycles_and_missing_parents():
    assert focus.detect({10: (11, "a"), 11: (10, "b")}, 10, "darwin") is focus.UNKNOWN
    assert focus.detect({}, 10, "darwin") is focus.UNKNOWN


# --- argv construction (never executed) ---------------------------------------------------

def test_tab_script_takes_the_tty_as_an_argument_not_source():
    host = focus.detect(table(), 4242, "darwin")
    args = focus.tab_args(host, "ttys004")
    assert args[-2:] == ["--", "/dev/ttys004"]
    source = [a for i, a in enumerate(args[:-2]) if args[i - 1] == "-e"] if args else []
    assert all("ttys004" not in line for line in source)
    assert "\n".join(source) == focus.ITERM_TAB
    assert args[:-2] == focus.osascript_args(focus.ITERM_TAB, "x")[:-2]  # the script never varies


@pytest.mark.parametrize("tty", ["../../etc", "ttys004;", "ttys004\" & do shell script \"id", "pts/x", "", "tty" + "1" * 9])
def test_tab_args_refuse_odd_ttys(tty):
    with pytest.raises(ValueError):
        focus.tab_args(focus.Host("terminal", "Terminal", "tab", "Terminal"), tty)


def test_activate_and_open_terminal_args():
    assert focus.activate_args(focus.Host("warp", "Warp", "app", "Warp"))[-2:] == ["--", "Warp"]
    args = focus.open_terminal_args("terminal", "/opt/homebrew/bin/tmux", "eyrie", "eyrie-7f3a")
    assert args[-1] == "/opt/homebrew/bin/tmux -L eyrie attach -t eyrie-7f3a"
    assert "\n".join(a for i, a in enumerate(args[:-2]) if args[i - 1] == "-e") == focus.TERMINAL_RUN
    assert focus.open_terminal_args("iterm", "/a b/tmux", "eyrie", "eyrie-7f3a")[-1] == "'/a b/tmux' -L eyrie attach -t eyrie-7f3a"


def test_tmux_pane_lookup_and_argv():
    out = "/dev/ttys021 %7 1 main\n/dev/ttys022 %8 0 my session\n"
    assert focus.find_pane(out, "ttys021") == ("%7", "main", 1)
    assert focus.find_pane(out, "ttys022") == ("%8", "my session", 0)
    assert focus.find_pane("/dev/ttys021 7 1 main", "ttys021") is None  # not a pane id
    host = focus.Host("tmux", "tmux", "pane", None, ("-L", "work"))
    assert focus.tmux_focus_args(host, "%7") == ["-L", "work", "switch-client", "-t", "%7", ";", "select-window", "-t",
                                                 "%7", ";", "select-pane", "-t", "%7"]
    with pytest.raises(ValueError):
        focus.tmux_focus_args(host, "main:1")


@pytest.mark.parametrize("result,ok,says", [
    (RunResult(0, "ok\n", "", 1), True, "done"),
    (RunResult(0, "missing\n", "", 1), False, "gone"),
    (RunResult(1, "", "execution error: Not authorized to send Apple events to iTerm. (-1743)", 1), False, "Automation"),
    (RunResult(1, "", "boom", 1), False, "boom"),
])
def test_explain(result, ok, says):
    got = focus.explain(result, "done", "gone", "iTerm2")
    assert got[0] is ok and says in got[1]


# --- the actions --------------------------------------------------------------------------

class FakeRunner:
    def __init__(self):
        self.calls = []
        self.osascript = RunResult(0, "ok\n", "", 5)
        self.panes = "/dev/ttys021 %7 1 main\n"
        self.clients = "/dev/ttys004 802 main\n"

    def __call__(self, runner_self, tool, args, cwd=None):
        self.calls.append((tool, list(args)))
        if tool == "osascript":
            return self.osascript
        if tool == "tmux" and args[:2] == ["-L", "eyrie"]:
            return RunResult(1, "", "no server running", 1)  # Eyrie has no sessions here
        if tool == "tmux" and "list-panes" in args:
            return RunResult(0, self.panes, "", 1)
        if tool == "tmux" and "list-clients" in args:
            return RunResult(0, self.clients, "", 1)
        if tool == "tmux" and "switch-client" in args:
            return RunResult(0, "", "", 1)
        raise AssertionError((tool, args))


@pytest.fixture
def run(monkeypatch, settings, home):
    from app.actions import runner
    (home / ".codex").mkdir(exist_ok=True)
    fake = FakeRunner()
    monkeypatch.setattr(runner.Runner, "run", lambda self, tool, args, cwd=None: fake(self, tool, args, cwd))
    monkeypatch.setattr(external, "_ps", lambda: MAC_PS)
    monkeypatch.setattr(external, "_cwds", lambda pids: {})
    monkeypatch.setattr(focus.sys, "platform", "darwin")
    return fake


def post(authed, params, **body):
    return authed.post("/api/v1/actions/sessions.focus", json={"params": params, **body})


def test_focus_iterm_tab(authed, run):
    r = post(authed, {"pid": 4242, "tty": "ttys004"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["message"] == "Switched to the iTerm2 tab on ttys004."
    tool, args = run.calls[-1]
    assert tool == "osascript" and args[-2:] == ["--", "/dev/ttys004"]


def test_focus_dry_run_shows_the_argv_and_runs_nothing(authed, run):
    r = post(authed, {"pid": 4343, "tty": "ttys009"}, dry_run=True)
    assert r.status_code == 200 and r.json()["argv"][0] == "osascript" and r.json()["argv"][-1] == "/dev/ttys009"
    assert not [c for c in run.calls if c[0] == "osascript"]


@pytest.mark.parametrize("params", [{"pid": 4242, "tty": "ttys004;"}, {"pid": 4242, "tty": "../ttys004"},
                                    {"pid": 1, "tty": "ttys004"}, {"pid": "4242", "tty": None}, {"tty": "ttys004"}])
def test_focus_rejects_bad_params(authed, run, params):
    assert post(authed, params).status_code == 422
    assert not [c for c in run.calls if c[0] == "osascript"]


@pytest.mark.parametrize("pid,tty", [(500, "ttys004"),    # iTerm's own server process, not a session
                                     (4242, "ttys009"),   # a listed pid on another tty
                                     (31337, "ttys004")])  # no such process
def test_focus_only_listed_sessions(authed, run, pid, tty):
    r = post(authed, {"pid": pid, "tty": tty})
    assert r.status_code == 409 and "isn't running" in r.json()["detail"]
    assert not [c for c in run.calls if c[0] == "osascript"]


def test_focus_needs_the_token(client, run):
    assert client.post("/api/v1/actions/sessions.focus", json={"params": {"pid": 4242, "tty": "ttys004"}}).status_code in (401, 403)


def test_focus_app_only_host(authed, run):
    r = post(authed, {"pid": 7001, "tty": "ttys015"})
    assert r.json()["ok"] is True and r.json()["message"] == "Brought Warp to the front. Eyrie can't pick its tab: look for ttys015."
    assert run.calls[-1][1][-2:] == ["--", "Warp"]


def test_focus_unsupported_host_says_where(authed, run):
    r = post(authed, {"pid": 9001, "tty": "ttys030"})
    assert r.status_code == 409 and "an ssh session on ttys030" in r.json()["detail"]


def test_focus_automation_denied_and_missing_tab(authed, run):
    run.osascript = RunResult(1, "", "Not authorized to send Apple events to iTerm. (-1743)", 5)
    r = post(authed, {"pid": 4242, "tty": "ttys004"}).json()
    assert r["ok"] is False and "Privacy & Security → Automation" in r["message"]
    run.osascript = RunResult(0, "missing\n", "", 5)
    r = post(authed, {"pid": 4242, "tty": "ttys004"}).json()
    assert r["ok"] is False and "Couldn't find the iTerm2 tab on ttys004" in r["message"]


def test_focus_tmux_pane_then_its_clients_terminal(authed, run):
    r = post(authed, {"pid": 8001, "tty": "ttys021"})
    assert r.json()["ok"] is True, r.json()
    tmux_calls = [a for t, a in run.calls if t == "tmux" and "switch-client" in a]
    assert tmux_calls == [focus.tmux_focus_args(focus.Host("tmux", "tmux", "pane", None, ("-L", "work")), "%7")]
    assert run.calls[-1][0] == "osascript" and run.calls[-1][1][-1] == "/dev/ttys004"  # the client is in iTerm2
    assert r.json()["message"].startswith("Selected the tmux pane on ttys021 in iTerm2.")


def test_focus_tmux_unattached_session(authed, run):
    run.panes = "/dev/ttys021 %7 0 main\n"
    r = post(authed, {"pid": 8001, "tty": "ttys021"})
    assert r.status_code == 409 and "tmux attach -t main" in r.json()["detail"]


def test_open_terminal(authed, run, monkeypatch):
    from app.sessions import tmux
    monkeypatch.setattr(tmux.Tmux, "exists", lambda self, name: name == "eyrie-7f3a")
    r = authed.post("/api/v1/actions/sessions.open_terminal", json={"params": {"name": "eyrie-7f3a", "app": "iterm"}})
    assert r.json()["ok"] is True and r.json()["message"] == "Opened a new iTerm2 window attached to eyrie-7f3a."
    assert run.calls[-1][1][-1] == "/fake/bin/tmux -L eyrie attach -t eyrie-7f3a"
    bad = authed.post("/api/v1/actions/sessions.open_terminal", json={"params": {"name": "eyrie-7f3a; rm", "app": "iterm"}})
    assert bad.status_code == 422
    gone = authed.post("/api/v1/actions/sessions.open_terminal", json={"params": {"name": "eyrie-dead", "app": "terminal"}})
    assert gone.status_code == 409
    monkeypatch.setattr(focus.sys, "platform", "linux")
    import app.actions.registry as reg
    monkeypatch.setattr(reg.sys, "platform", "linux")
    assert authed.post("/api/v1/actions/sessions.open_terminal",
                       json={"params": {"name": "eyrie-7f3a"}}).status_code == 409
