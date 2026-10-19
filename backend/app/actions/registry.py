"""The only things Eyrie can change. Each action validates its params, builds an argv for
the tool's own CLI (Eyrie never edits another tool's config files), and says whether it
is destructive (needs an explicit confirm after the user has seen the command).

There is deliberately no generic "run a command" action.
"""
import re
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

from pydantic import BaseModel, field_validator, model_validator

from app.masking import mask_args

if TYPE_CHECKING:
    from app.actions.runner import Runner
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


class McpAdd(BaseModel):
    client: Literal["claude", "codex"]
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
        if self.client == "codex":
            if self.transport == "sse":
                raise ValueError("Codex supports stdio and http servers only")
            if self.scope != "user":
                raise ValueError("Codex servers are global; use scope 'user'")
            if self.headers:
                raise ValueError("Codex can't set headers; use bearer_token_env_var")
        elif self.bearer_token_env_var:
            raise ValueError("bearer_token_env_var is Codex-only; use headers for Claude Code")
        if self.bearer_token_env_var and not ENV_KEY.match(self.bearer_token_env_var):
            raise ValueError("Bad bearer_token_env_var")
        self.project_dir = str(_project_dir(self.scope, self.project_dir) or "") or None
        return self


class McpRemove(BaseModel):
    client: Literal["claude", "codex"]
    name: str
    scope: Scope = "user"
    project_dir: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        return _name(v)

    @model_validator(mode="after")
    def _check(self):
        if self.client == "codex" and self.scope != "user":
            raise ValueError("Codex servers are global; use scope 'user'")
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
    tool: Literal["claude", "codex"]
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
        if self.conversation_id and not (self.tool == "claude" and self.mode == "new"):
            raise ValueError("conversation_id only applies to a new Claude Code session")
        self.name = self.name or f"eyrie-{secrets.token_hex(3)}"
        if self.tool == "claude" and self.mode == "new":
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


@dataclass
class Context:
    settings: "Settings"
    runner: "Runner"


@dataclass
class Planned:
    tool: str
    args: list[str]
    cwd: Path | None = None


@dataclass
class Action:
    id: str
    params: type[BaseModel]
    plan: Callable[[BaseModel, Context], Planned]
    destructive: bool = False
    # Name of the source whose cached state this action changes.
    invalidates: str | None = None


def _mcp_add(p: McpAdd, ctx: Context) -> Planned:
    cwd = Path(p.project_dir) if p.project_dir else None
    if p.client == "codex":
        args = ["mcp", "add", p.name]
        if p.transport == "stdio":
            for k, v in p.env.items():
                args += ["--env", f"{k}={v}"]
            return Planned("codex", args + ["--", p.command, *p.args])
        args += ["--url", p.url]
        if p.bearer_token_env_var:
            args += ["--bearer-token-env-var", p.bearer_token_env_var]
        return Planned("codex", args)
    args = ["mcp", "add", "-s", p.scope, "-t", p.transport, p.name]
    if p.transport == "stdio":
        for k, v in p.env.items():
            args += ["-e", f"{k}={v}"]
        return Planned("claude", args + ["--", p.command, *p.args], cwd)
    args.append(p.url)
    for k, v in p.headers.items():
        args += ["-H", f"{k}: {v}"]
    return Planned("claude", args, cwd)


def _mcp_remove(p: McpRemove, ctx: Context) -> Planned:
    if p.client == "codex":
        return Planned("codex", ["mcp", "remove", p.name])
    return Planned("claude", ["mcp", "remove", "-s", p.scope, p.name], Path(p.project_dir) if p.project_dir else None)


def _plugin(verb: str):
    def plan(p: PluginToggle, ctx: Context) -> Planned:
        args = ["plugin", verb, p.plugin, "--json"]
        if p.scope:
            args += ["-s", p.scope]
        return Planned("claude", args)
    return plan


def _session_start(p: SessionStart, ctx: Context) -> Planned:
    from app.sessions.tmux import base_args

    exe = ctx.runner.binary(p.tool)
    if p.tool == "claude":
        cmd = {"new": [exe, "--session-id", p.conversation_id], "continue": [exe, "--continue"],
               "resume": [exe, "--resume", p.resume_id]}[p.mode]
    else:
        cmd = {"new": [exe, "--cd", p.cwd], "continue": [exe, "--cd", p.cwd, "resume", "--last"],
               "resume": [exe, "--cd", p.cwd, "resume", p.resume_id]}[p.mode]
    tags = {"@eyrie_tool": p.tool, "@eyrie_cwd": p.cwd, "@eyrie_mode": p.mode,
            "@eyrie_conv": p.conversation_id or p.resume_id or ""}
    args = [*base_args(ctx.settings), "new-session", "-d", "-s", p.name, "-x", "200", "-y", "50", "-c", p.cwd, *cmd]
    for k, v in tags.items():
        args += [";", "set-option", "-t", p.name, k, v]
    return Planned("tmux", args)


def _session_stop(p: SessionStop, ctx: Context) -> Planned:
    from app.sessions.tmux import base_args

    return Planned("tmux", [*base_args(ctx.settings), "kill-session", "-t", p.name])


ACTIONS: dict[str, Action] = {a.id: a for a in [
    Action("mcp.add", McpAdd, _mcp_add, invalidates="mcp"),
    Action("mcp.remove", McpRemove, _mcp_remove, destructive=True, invalidates="mcp"),
    Action("plugins.enable", PluginToggle, _plugin("enable"), invalidates="plugins"),
    Action("plugins.disable", PluginToggle, _plugin("disable"), invalidates="plugins"),
    Action("sessions.start", SessionStart, _session_start),
    Action("sessions.stop", SessionStop, _session_stop, destructive=True),
]}


def redact(tool: str, args: list[str]) -> list[str]:
    """The argv as shown to people and written to the audit log: env and header values
    are masked (names kept), and so is anything else that looks like a secret."""
    out = [tool]
    prev = None
    masked = mask_args(args)
    for a, m in zip(args, masked):
        if prev in ENV_FLAGS:
            out.append(a.partition("=")[0] + "=***")
        elif prev in HEADER_FLAGS:
            out.append(a.partition(":")[0] + ": ***")
        else:
            out.append(m)
        prev = a
    return out
