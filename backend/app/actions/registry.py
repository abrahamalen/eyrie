"""The only things Eyrie can change. Each action validates its params, builds an argv for
the tool's own CLI (Eyrie never edits another tool's config files), and says whether it
is destructive (needs an explicit confirm after the user has seen the command).

There is deliberately no generic "run a command" action.
"""
import os
import re
import secrets
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.masking import mask_args
from app.tools import TOOLS, ToolId

if TYPE_CHECKING:
    from app.actions.runner import Runner, RunResult
    from app.config import Settings

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PLUGIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(@[A-Za-z0-9][A-Za-z0-9._-]*)?$")
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
ENV_FLAGS = {"-e", "--env"}
HEADER_FLAGS = {"-H", "--header"}

Scope = Literal["user", "local", "project"]


def _name(v: str) -> str:
    if not NAME.match(v):
        raise ValueError("Use letters, digits, '.', '_' or '-', starting with a letter or digit (max 64)")
    return v


def _project_dir(scope: str, project_dir: str | None) -> Path | None:
    if scope == "user":
        if project_dir:
            raise ValueError("project_dir only applies to local or project scope")
        return None
    if not project_dir:
        raise ValueError(f"{scope} scope needs project_dir")
    p = Path(project_dir).expanduser()
    if not p.is_absolute() or not p.is_dir():
        raise ValueError(f"project_dir must be an existing absolute directory: {project_dir}")
    return p.resolve()


def _mcp_tool(client: str, scope: str, transport: str | None = None):
    """The tool's MCP capability, checked against what it declares it supports."""
    title, mcp = TOOLS[client].title, TOOLS[client].mcp
    if mcp is None:
        raise ValueError(f"{title} has no MCP support")
    if scope not in mcp.scopes:
        if mcp.scopes == ("user",):
            raise ValueError(f"{title} servers are global; use scope 'user'")
        raise ValueError(f"{title} servers can't use scope '{scope}'; use {' or '.join(map(repr, mcp.scopes))}")
    if transport is not None and transport not in mcp.transports:
        raise ValueError(f"{title} supports {' and '.join(mcp.transports)} servers only")
    return mcp


class McpAdd(BaseModel):
    client: ToolId
    name: str
    transport: Literal["stdio", "http", "sse"]
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    scope: Scope = "user"
    project_dir: str | None = None
    env: dict[str, str] = {}
    headers: dict[str, str] = {}
    bearer_token_env_var: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        return _name(v)

    @model_validator(mode="after")
    def _check(self):
        if self.transport == "stdio":
            if not (self.command or "").strip():
                raise ValueError("stdio servers need a command")
            if self.url or self.headers or self.bearer_token_env_var:
                raise ValueError("url, headers and bearer token only apply to http/sse servers")
        else:
            if not self.url or not re.match(r"^https?://\S+$", self.url):
                raise ValueError("http/sse servers need an http(s):// URL")
            if self.command or self.args or self.env:
                raise ValueError("command, args and env only apply to stdio servers")
        for k in self.env:
            if not ENV_KEY.match(k):
                raise ValueError(f"Bad env var name: {k}")
        for k, v in self.headers.items():
            if not HEADER_NAME.match(k) or "\n" in v or "\r" in v:
                raise ValueError(f"Bad header: {k}")
        mcp = _mcp_tool(self.client, self.scope, self.transport)
        title = TOOLS[self.client].title
        if self.headers and not mcp.headers:
            raise ValueError(f"{title} can't set headers; use bearer_token_env_var")
        if self.bearer_token_env_var and not mcp.bearer_token_env_var:
            raise ValueError(f"{title} can't read a bearer token from an env var; use headers")
        if self.bearer_token_env_var and not ENV_KEY.match(self.bearer_token_env_var):
            raise ValueError("Bad bearer_token_env_var")
        self.project_dir = str(_project_dir(self.scope, self.project_dir) or "") or None
        return self


class McpRemove(BaseModel):
    client: ToolId
    name: str
    scope: Scope = "user"
    project_dir: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        return _name(v)

    @model_validator(mode="after")
    def _check(self):
        _mcp_tool(self.client, self.scope)
        self.project_dir = str(_project_dir(self.scope, self.project_dir) or "") or None
        return self


class PluginToggle(BaseModel):
    plugin: str
    scope: Scope | None = None

    @field_validator("plugin")
    @classmethod
    def _id(cls, v: str) -> str:
        if not PLUGIN_ID.match(v):
            raise ValueError("Expected a plugin id like name@marketplace")
        return v


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SESSION_NAME = re.compile(r"^eyrie-[a-z0-9]{4,16}$")


def _uuid(v: str | None, what: str) -> str | None:
    if v is not None and not UUID_RE.match(v):
        raise ValueError(f"{what} must be a lowercase UUID")
    return v


class SessionStart(BaseModel):
    tool: ToolId
    cwd: str
    # new: fresh conversation; continue: latest conversation in cwd; resume: resume_id
    mode: Literal["new", "continue", "resume"] = "new"
    resume_id: str | None = None
    # Optional so API callers can omit them; the UI sends them so the preview matches the run.
    name: str | None = None
    conversation_id: str | None = None

    @model_validator(mode="after")
    def _check(self):
        _uuid(self.resume_id, "resume_id")
        _uuid(self.conversation_id, "conversation_id")
        if self.name is not None and not SESSION_NAME.match(self.name):
            raise ValueError("name must look like eyrie-<4-16 lowercase letters/digits>")
        if (self.mode == "resume") != (self.resume_id is not None):
            raise ValueError("resume_id is required for mode 'resume' and only allowed there")
        sessions = TOOLS[self.tool].sessions
        if sessions is None or self.mode not in sessions.modes:
            raise ValueError(f"{TOOLS[self.tool].title} can't start a '{self.mode}' session")
        wants_id = sessions.wants_conversation_id(self.mode)
        if self.conversation_id and not wants_id:
            raise ValueError(f"conversation_id only applies where Eyrie picks the id, not a {self.mode} "
                             f"{TOOLS[self.tool].title} session")
        self.name = self.name or f"eyrie-{secrets.token_hex(3)}"
        if wants_id:
            self.conversation_id = self.conversation_id or str(uuid.uuid4())
        return self


class SessionStop(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not SESSION_NAME.match(v):
            raise ValueError("Not an Eyrie session name")
        return v


class SessionFocus(BaseModel):
    """Bring the terminal of one of your own sessions to the front (docs/session-names-and-jump.md §5)."""
    pid: int = Field(ge=2, le=99_999_999)
    tty: str

    @field_validator("tty")
    @classmethod
    def _tty(cls, v: str) -> str:
        from app.sessions.focus import TTY_RE

        if not TTY_RE.match(v):
            raise ValueError("tty must look like ttys004 or pts/3")
        return v


class SessionStopExternal(BaseModel):
    """Stop one of your own sessions running in a terminal (docs/stop-and-idle.md §4)."""
    pid: int = Field(ge=2, le=99_999_999)
    tool: ToolId
    tty: str
    # The process's exact start time as the listing showed it (process_started): a reused pid can't match.
    started: datetime
    # SIGKILL instead of SIGTERM. Only ever sent when asked for, after its own confirm.
    force: bool = False

    @field_validator("tty")
    @classmethod
    def _tty(cls, v: str) -> str:
        from app.sessions.focus import TTY_RE

        if not TTY_RE.match(v):
            raise ValueError("tty must look like ttys004 or pts/3")
        return v

    @field_validator("started")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("started needs a time zone")
        return v


class SessionOpenTerminal(BaseModel):
    """A new Terminal/iTerm2 window attached to an Eyrie session (macOS)."""
    name: str
    app: Literal["terminal", "iterm"] = "terminal"

    @field_validator("name")
    @classmethod
    def _valid(cls, v: str) -> str:
        if not SESSION_NAME.match(v):
            raise ValueError("Not an Eyrie session name")
        return v


class Blocked(Exception):
    """The action can't go ahead; the message says why and what to do instead (HTTP 409)."""


@dataclass
class Context:
    settings: "Settings"
    runner: "Runner"
    registry: dict | None = None


@dataclass
class Planned:
    tool: str
    args: list[str]
    cwd: Path | None = None
    # Run after this one succeeds (e.g. the tmux pane, then the terminal holding its client).
    then: list["Planned"] = field(default_factory=list)
    # The run's result → (ok, message for people), when exit code + output aren't enough.
    explain: Callable[["RunResult"], tuple[bool, str]] | None = None
    # Done in-process instead of running `tool args` (which is then only what's shown and audited).
    call: Callable[[], "RunResult"] | None = None
    # A machine-readable outcome for the UI, read after the run.
    state: Callable[[], str | None] | None = None


@dataclass
class Action:
    id: str
    params: type[BaseModel]
    plan: Callable[[BaseModel, Context], Planned]
    destructive: bool = False
    # Name of the source whose cached state this action changes.
    invalidates: str | None = None
    # Check against live state before planning (and on dry runs): the plan inspects processes.
    precheck_first: bool = False


def _mcp_add(p: McpAdd, ctx: Context) -> Planned:
    return Planned(p.client, *TOOLS[p.client].mcp.add(p))


def _mcp_remove(p: McpRemove, ctx: Context) -> Planned:
    return Planned(p.client, *TOOLS[p.client].mcp.remove(p))


def _plugin(verb: str):
    def plan(p: PluginToggle, ctx: Context) -> Planned:
        args = ["plugin", verb, p.plugin, "--json"]
        if p.scope:
            args += ["-s", p.scope]
        return Planned("claude", args)
    return plan


def _session_start(p: SessionStart, ctx: Context) -> Planned:
    from app.sessions.tmux import base_args

    cmd = TOOLS[p.tool].sessions.argv(ctx.runner.binary(p.tool), p.mode, p.cwd, p.resume_id, p.conversation_id)
    tags = {"@eyrie_tool": p.tool, "@eyrie_cwd": p.cwd, "@eyrie_mode": p.mode,
            "@eyrie_conv": p.conversation_id or p.resume_id or ""}
    # Small to start: a client attaching later grows the window (tmux pulls lines back from
    # history), where shrinking a big one would push the first lines out of view.
    args = [*base_args(ctx.settings), "new-session", "-d", "-s", p.name, "-x", "80", "-y", "24", "-c", p.cwd, *cmd]
    for k, v in tags.items():
        args += [";", "set-option", "-t", p.name, k, v]
    return Planned("tmux", args)


def _session_stop(p: SessionStop, ctx: Context) -> Planned:
    from app.sessions.tmux import base_args

    return Planned("tmux", [*base_args(ctx.settings), "kill-session", "-t", p.name])


def _focus_host(host, tty: str, ctx: Context) -> Planned:
    """Select the tab / raise the app holding `tty` (Terminal, iTerm2, or an app-only host)."""
    from app.sessions import focus

    label = host.label
    if host.focus == "tab":
        return Planned("osascript", focus.tab_args(host, tty), explain=lambda r: focus.explain(
            r, f"Switched to the {label} tab on {tty}.", f"Couldn't find the {label} tab on {tty}. It may have just closed.",
            label))
    if host.focus == "app":
        return Planned("osascript", focus.activate_args(host), explain=lambda r: focus.explain(
            r, f"Brought {label} to the front. Eyrie can't pick its tab: look for {tty}.",
            f"Couldn't bring {label} to the front.", label))
    raise Blocked(f"Running in {label} on {tty}. Eyrie can't switch to it; switch to it yourself.")


def _tmux_pane(host, tty: str, ctx: Context) -> Planned:
    """Your own tmux: find the pane on `tty`, show it in its client, then raise that client's terminal."""
    from app.sessions import focus

    r = ctx.runner.run("tmux", [*host.tmux_args, "list-panes", "-a", "-F",
                                "#{pane_tty} #{pane_id} #{session_attached} #{session_name}"])
    found = focus.find_pane(r.stdout, tty) if r.ok else None
    if found is None:
        raise Blocked(f"Couldn't find the tmux pane on {tty}. Is your tmux server on a custom socket?")
    pane, session, attached = found
    if not attached:
        raise Blocked(f"No terminal is attached to tmux session “{session}”. Run: tmux attach -t {session}")
    then, where = [], ""
    clients = ctx.runner.run("tmux", [*host.tmux_args, "list-clients", "-F", "#{client_tty} #{client_pid} #{client_session}"])
    ext = ctx.registry["sessions"].external if ctx.registry else None
    for line in clients.stdout.splitlines() if clients.ok else []:
        ctty, cpid, csession = (line.split(" ", 2) + ["", ""])[:3]
        ctty = ctty.removeprefix("/dev/")
        if csession != session or not cpid.isdigit() or not focus.TTY_RE.match(ctty) or ext is None:
            continue
        chost = focus.detect(ext.table, int(cpid))
        if chost.focus in ("tab", "app"):
            then.append(_focus_host(chost, ctty, ctx))
            where = f" in {chost.label}"
        break
    return Planned("tmux", focus.tmux_focus_args(host, pane), then=then,
                   explain=lambda res: (res.ok, f"Selected the tmux pane on {tty}{where}." if res.ok
                                        else f"tmux couldn't switch to the pane: {res.stderr.strip()}"))


def _session_focus(p: SessionFocus, ctx: Context) -> Planned:
    # The precheck has just listed sessions and confirmed this pid is one, on this tty.
    host = ctx.registry["sessions"].external.hosts.get(p.pid) if ctx.registry else None
    if host is None:
        raise Blocked("That session isn't running any more.")
    if host.focus == "pane":
        return _tmux_pane(host, p.tty, ctx)
    return _focus_host(host, p.tty, ctx)


NOT_LISTED = "That session isn't running any more, or isn't one of your Claude Code, Codex or Gemini sessions."
STOP_MESSAGES = {
    "already_exited": "That session had already exited; nothing was signalled.",
    "reused": "pid {pid} is a different process now; nothing was signalled. Refresh the list.",
    "denied": "The system refused to signal pid {pid} (permission denied). Nothing was stopped.",
    "still_running": "Still running {wait:g} s after SIGTERM. It may be finishing something, or ignoring the signal.",
    "stuck": "Still running after SIGKILL. The process is stuck in the kernel; it will go when that call returns.",
}


def _session_stop_external(p: SessionStopExternal, ctx: Context) -> Planned:
    """One signal to one listed pid, re-verified just before it's sent (procs.stop)."""
    import signal

    from app.actions.runner import RunResult
    from app.sessions import external, procs

    src = ctx.registry["sessions"].external if ctx.registry else None
    listed = src.last.get(p.pid) if src else None  # the precheck has just listed it
    if listed is None or listed["tool"] != p.tool:
        raise Blocked(NOT_LISTED)
    title = TOOLS[p.tool].title
    sig, name = (signal.SIGKILL, "KILL") if p.force else (signal.SIGTERM, "TERM")
    expect = procs.Expect(p.pid, os.getuid(), int(p.started.timestamp()), lambda cmd: external.tool_of(cmd) == p.tool)
    children = {c: src.stats[c].started for c in procs.descendants(src.stats, p.pid)}
    wait = ctx.settings.sessions.stop_wait_seconds
    box: dict = {}

    def call() -> RunResult:
        started = time.perf_counter()
        o = procs.stop(expect, sig, wait, children)
        state = "stuck" if o.state == "still_running" and p.force else o.state
        box.update(outcome=o, state=state)
        code = {"exited": 0, "already_exited": 0, "still_running": 1, "stuck": 1}.get(state, 2)
        return RunResult(code, "", "", (time.perf_counter() - started) * 1000)

    def explain(r: RunResult) -> tuple[bool, str]:
        o, state = box["outcome"], box["state"]
        if state == "exited":
            said = f"Stopped. {title} (pid {p.pid}) exited {o.seconds:.1f} s after SIG{name}."
            if o.survivors:
                n = len(o.survivors)
                said += (f" {n} process{'es' if n > 1 else ''} it started {'are' if n > 1 else 'is'} still running "
                         f"(pid{'s' if n > 1 else ''} {', '.join(map(str, o.survivors))}). Eyrie leaves them alone.")
            return True, said
        return state == "already_exited", STOP_MESSAGES[state].format(pid=p.pid, wait=wait)

    return Planned("kill", [f"-{name}", str(p.pid)], call=call, explain=explain, state=lambda: box.get("state"))


def _session_open_terminal(p: SessionOpenTerminal, ctx: Context) -> Planned:
    from app.sessions import focus

    if sys.platform != "darwin":
        raise Blocked("Opening a terminal window is macOS-only; copy the attach command instead.")
    title = focus.APP_TITLES[p.app]
    args = focus.open_terminal_args(p.app, ctx.runner.binary("tmux"), ctx.settings.sessions.socket, p.name)
    return Planned("osascript", args, explain=lambda r: focus.explain(
        r, f"Opened a new {title} window attached to {p.name}.", f"{title} didn't open a window.", title))


ACTIONS: dict[str, Action] = {a.id: a for a in [
    Action("mcp.add", McpAdd, _mcp_add, invalidates="mcp"),
    Action("mcp.remove", McpRemove, _mcp_remove, destructive=True, invalidates="mcp"),
    Action("plugins.enable", PluginToggle, _plugin("enable"), invalidates="plugins"),
    Action("plugins.disable", PluginToggle, _plugin("disable"), invalidates="plugins"),
    Action("sessions.start", SessionStart, _session_start),
    Action("sessions.stop", SessionStop, _session_stop, destructive=True),
    Action("sessions.stop_external", SessionStopExternal, _session_stop_external, destructive=True,
           precheck_first=True),
    Action("sessions.focus", SessionFocus, _session_focus, precheck_first=True),
    Action("sessions.open_terminal", SessionOpenTerminal, _session_open_terminal, precheck_first=True),
]}


def redact(tool: str, args: list[str]) -> list[str]:
    """The argv as shown to people and written to the audit log: env and header values
    are masked (names kept), and so is anything else that looks like a secret."""
    out = [tool]
    prev = None
    masked = mask_args(args)
    for a, m in zip(args, masked, strict=True):
        if prev in ENV_FLAGS:
            out.append(a.partition("=")[0] + "=***")
        elif prev in HEADER_FLAGS:
            out.append(a.partition(":")[0] + ": ***")
        else:
            out.append(m)
        prev = a
    return out
