"""Which terminal a session runs in, and how to bring it to the front
(docs/session-names-and-jump.md §5).

The terminal is found by walking the session's parent processes in the `ps` snapshot that
external detection already takes. Bringing it forward is an argv for the Runner:
`osascript` with a constant script that reads the tty (or app name, or command) from its
arguments, never from its source, or the user's own `tmux`. Nothing here runs anything.
"""
import re
import shlex
import sys
from dataclasses import dataclass, field
from typing import Literal

Focus = Literal["tab", "pane", "app", "none"]
TTY_RE = re.compile(r"^(ttys?\d{1,4}|pts/\d{1,4})$")
TMUX_SOCKET_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
TMUX_SOCKET_PATH = re.compile(r"^/[A-Za-z0-9._/-]{1,255}$")
PANE_ID = re.compile(r"^%\d{1,6}$")


@dataclass(frozen=True)
class Host:
    kind: str
    label: str
    focus: Focus
    app: str | None = None  # the macOS application to talk to
    tmux_args: tuple[str, ...] = field(default_factory=tuple)  # -L name / -S path of your tmux server


UNKNOWN = Host("unknown", "an unknown terminal", "none")

# (kind, label, focus on macOS, macOS app name, substrings of the command, basenames)
_HOSTS = [
    ("terminal", "Terminal", "tab", "Terminal", ("/Terminal.app/",), ()),
    ("iterm", "iTerm2", "tab", "iTerm", ("/iTerm.app/", "/iTermServer"), ()),
    ("ghostty", "Ghostty", "app", "Ghostty", ("/Ghostty.app/",), ("ghostty",)),
    ("warp", "Warp", "app", "Warp", ("/Warp.app/",), ("warp-terminal",)),
    ("wezterm", "WezTerm", "app", "WezTerm", ("/WezTerm.app/",), ("wezterm-gui", "wezterm-mux-server")),
    ("kitty", "kitty", "app", "kitty", ("/kitty.app/",), ("kitty",)),
    ("alacritty", "Alacritty", "app", "Alacritty", ("/Alacritty.app/",), ("alacritty",)),
    ("vscode", "VS Code", "app", "Visual Studio Code", ("/Visual Studio Code.app/",), ("code",)),
    ("cursor", "Cursor", "app", "Cursor", ("/Cursor.app/",), ("cursor",)),
    ("gnome-terminal", "GNOME Terminal", "none", None, (), ("gnome-terminal-server", "gnome-terminal")),
    ("konsole", "Konsole", "none", None, (), ("konsole",)),
    ("ptyxis", "Ptyxis", "none", None, (), ("ptyxis", "ptyxis-agent")),
    ("xterm", "xterm", "none", None, (), ("xterm", "uxterm")),
    ("terminator", "Terminator", "none", None, (), ("terminator",)),
    ("tilix", "Tilix", "none", None, (), ("tilix",)),
    ("xfce4-terminal", "Xfce Terminal", "none", None, (), ("xfce4-terminal",)),
    ("ssh", "an ssh session", "none", None, (), ("sshd", "sshd-session")),
]


def _basename(command: str) -> str:
    first = command.split(None, 1)[0] if command.strip() else ""
    return first.rsplit("/", 1)[-1].lstrip("-")


def _tmux_args(command: str) -> tuple[str, ...] | None:
    """`tmux [-L name | -S path] …` → the socket flags to reach the same server, or None
    when the flags can't be trusted (then the session gets no pane focus)."""
    args = command.split()
    out: tuple[str, ...] = ()
    for flag, pattern in (("-L", TMUX_SOCKET_NAME), ("-S", TMUX_SOCKET_PATH)):
        if flag in args:
            i = args.index(flag)
            value = args[i + 1] if i + 1 < len(args) else ""
            if not pattern.match(value) or ".." in value:
                return None
            out = (flag, value)
    return out


def classify(command: str, platform: str | None = None) -> Host | None:
    """The host a process is, if it's one Eyrie knows; only the classification is kept."""
    base = _basename(command)
    if base == "tmux" or base.startswith("tmux:"):
        sock = _tmux_args(command)
        return Host("tmux", "tmux", "pane" if sock is not None else "none", None, sock or ())
    mac = (platform or sys.platform) == "darwin"
    for kind, label, focus, app, parts, bases in _HOSTS:
        if any(p in command for p in parts) or base in bases:
            if not mac and focus in ("tab", "app"):
                focus, app = "none", None  # raising another app's window isn't portable on Linux
            return Host(kind, label, focus, app)
    return None


def detect(table: dict[int, tuple[int, str]], pid: int, platform: str | None = None) -> Host:
    """Walk up from `pid` (table: pid → (ppid, command)) to the first known host."""
    seen = set()
    cur = table.get(pid, (0, ""))[0]
    while cur > 1 and cur not in seen and len(seen) < 32:
        seen.add(cur)
        ppid, command = table.get(cur, (0, ""))
        host = classify(command, platform)
        if host is not None:
            return host
        cur = ppid
    return UNKNOWN


# --- osascript ----------------------------------------------------------------------------
# Constant scripts; the value they act on is `item 1 of argv`, passed after `--`.

TERMINAL_TAB = """on run argv
  set target to item 1 of argv
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        if tty of t is target then
          set selected of t to true
          set index of w to 1
          activate
          return "ok"
        end if
      end repeat
    end repeat
  end tell
  return "missing"
end run"""

ITERM_TAB = """on run argv
  set target to item 1 of argv
  tell application "iTerm"
    repeat with w in windows
      repeat with t in tabs of w
        repeat with s in sessions of t
          if tty of s is target then
            select w
            tell t to select
            tell s to select
            activate
            return "ok"
          end if
        end repeat
      end repeat
    end repeat
  end tell
  return "missing"
end run"""

ACTIVATE_APP = """on run argv
  tell application (item 1 of argv) to activate
  return "ok"
end run"""

TERMINAL_RUN = """on run argv
  tell application "Terminal"
    do script (item 1 of argv)
    activate
  end tell
  return "ok"
end run"""

ITERM_RUN = """on run argv
  tell application "iTerm"
    set w to (create window with default profile)
    tell current session of w to write text (item 1 of argv)
    activate
  end tell
  return "ok"
end run"""

TAB_SCRIPTS = {"terminal": TERMINAL_TAB, "iterm": ITERM_TAB}
RUN_SCRIPTS = {"terminal": TERMINAL_RUN, "iterm": ITERM_RUN}
APP_TITLES = {"terminal": "Terminal", "iterm": "iTerm2"}


def osascript_args(script: str, value: str) -> list[str]:
    """`osascript -e <line> … -- <value>`: the value is an argument, not source."""
    args: list[str] = []
    for line in script.splitlines():
        args += ["-e", line]
    return [*args, "--", value]


def tab_args(host: Host, tty: str) -> list[str]:
    if host.kind not in TAB_SCRIPTS or not TTY_RE.match(tty):
        raise ValueError("No tab script for this terminal")
    return osascript_args(TAB_SCRIPTS[host.kind], f"/dev/{tty}")


def activate_args(host: Host) -> list[str]:
    if not host.app:
        raise ValueError("No application to activate")
    return osascript_args(ACTIVATE_APP, host.app)


def open_terminal_args(app: str, tmux_bin: str, socket: str, name: str) -> list[str]:
    """A new Terminal/iTerm window attached to an Eyrie session."""
    command = shlex.join([tmux_bin, "-L", socket, "attach", "-t", name])
    return osascript_args(RUN_SCRIPTS[app], command)


def tmux_focus_args(host: Host, pane: str) -> list[str]:
    """Show pane `%N` in the client attached to its session, as one tmux invocation."""
    if not PANE_ID.match(pane):
        raise ValueError("Bad pane id")
    return [*host.tmux_args, "switch-client", "-t", pane, ";", "select-window", "-t", pane, ";",
            "select-pane", "-t", pane]


def find_pane(list_panes_out: str, tty: str) -> tuple[str, str, int] | None:
    """`list-panes -a -F '#{pane_tty} #{pane_id} #{session_attached} #{session_name}'` →
    (pane id, session, attached clients) of the pane on /dev/<tty>."""
    for line in list_panes_out.splitlines():
        parts = line.split(" ", 3)
        if len(parts) == 4 and parts[0] == f"/dev/{tty}" and PANE_ID.match(parts[1]) and parts[2].isdigit():
            return parts[1], parts[3], int(parts[2])
    return None


AUTOMATION_DENIED = ("-1743", "Not authorized to send Apple events", "-10004")


def explain(result, success: str, missing: str, app_title: str) -> tuple[bool, str]:
    """osascript's answer → (ok, message for people)."""
    out, err = result.stdout.strip(), result.stderr.strip()
    if result.ok and out == "ok":
        return True, success
    if result.ok and out == "missing":
        return False, missing
    if any(code in err for code in AUTOMATION_DENIED):
        return False, (f"macOS blocked Eyrie from controlling {app_title}. Allow it in System Settings → "
                       "Privacy & Security → Automation, then try again.")
    return False, f"Couldn't switch to {app_title}: {err or out or 'osascript failed'}"
