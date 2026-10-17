"""The only things Eyrie can change. Each action validates its params, builds an argv for
the tool's own CLI (Eyrie never edits another tool's config files), and says whether it
is destructive (needs an explicit confirm after the user has seen the command).

There is deliberately no generic "run a command" action.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, field_validator, model_validator

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


@dataclass
class Planned:
    tool: str
    args: list[str]
    cwd: Path | None = None


@dataclass
class Action:
    id: str
    params: type[BaseModel]
    plan: Callable[[BaseModel], Planned]
    destructive: bool = False
    # Name of the source whose cached state this action changes.
    invalidates: str | None = None


def _mcp_add(p: McpAdd) -> Planned:
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


def _mcp_remove(p: McpRemove) -> Planned:
    if p.client == "codex":
        return Planned("codex", ["mcp", "remove", p.name])
    return Planned("claude", ["mcp", "remove", "-s", p.scope, p.name], Path(p.project_dir) if p.project_dir else None)


def _plugin(verb: str):
    def plan(p: PluginToggle) -> Planned:
        args = ["plugin", verb, p.plugin, "--json"]
        if p.scope:
            args += ["-s", p.scope]
        return Planned("claude", args)
    return plan


ACTIONS: dict[str, Action] = {a.id: a for a in [
    Action("mcp.add", McpAdd, _mcp_add, invalidates="mcp"),
    Action("mcp.remove", McpRemove, _mcp_remove, destructive=True, invalidates="mcp"),
    Action("plugins.enable", PluginToggle, _plugin("enable"), invalidates="plugins"),
    Action("plugins.disable", PluginToggle, _plugin("disable"), invalidates="plugins"),
]}


def redact(tool: str, args: list[str]) -> list[str]:
    """The argv as shown to people and written to the audit log: env and header values
    are masked, their names kept."""
    out = [tool]
    prev = None
    for a in args:
        if prev in ENV_FLAGS:
            out.append(a.partition("=")[0] + "=***")
        elif prev in HEADER_FLAGS:
            out.append(a.partition(":")[0] + ": ***")
        else:
            out.append(a)
        prev = a
    return out
