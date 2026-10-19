"""Codex: `codex`, state in ~/.codex (config.toml, state_5.sqlite)."""
import sqlite3
import tomllib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.tools._mcp import entry
from app.tools.base import Tool


def _db(settings: Settings) -> Path:
    return settings.paths.codex_home / "state_5.sqlite"


class Sessions:
    modes = ("new", "continue", "resume")
    helpers = frozenset({"app-server", "mcp", "mcp-server", "exec-server", "login", "logout", "--version", "-v",
                         "proto", "code-mode-host"})

    def argv(self, exe, mode, cwd, resume_id, conversation_id):
        return {"new": [exe, "--cd", cwd], "continue": [exe, "--cd", cwd, "resume", "--last"],
                "resume": [exe, "--cd", cwd, "resume", resume_id]}[mode]

    def wants_conversation_id(self, mode):
        return False

    def activity(self, settings: Settings):
        # Codex has no per-process conversation file to stat, so: newest thread in that directory.
        last: dict[str, datetime] = {}
        db = _db(settings)
        if db.exists():
            try:
                with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                    rows = con.execute("SELECT cwd, max(updated_at) FROM threads GROUP BY cwd").fetchall()
                last = {cwd: datetime.fromtimestamp(ts, tz=timezone.utc) for cwd, ts in rows if cwd and ts}
            except sqlite3.Error:
                pass
        return lambda cwd, resume: (last.get(cwd or ""), False)

    def known_dirs(self, settings: Settings) -> set[Path]:
        db = _db(settings)
        if not db.exists():
            return set()
        try:
            with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                return {Path(r[0]) for r in con.execute("SELECT DISTINCT cwd FROM threads WHERE cwd IS NOT NULL")}
        except sqlite3.Error:
            return set()


class Mcp:
    def servers(self, settings: Settings) -> list[dict]:
        path = settings.paths.codex_home / "config.toml"
        try:
            servers = tomllib.loads(path.read_text()).get("mcp_servers") or {}
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            return []
        return [entry(n, c, "codex", "user") for n, c in servers.items() if isinstance(c, dict)]

    def validate(self, p) -> None:
        if getattr(p, "transport", None) == "sse":
            raise ValueError("Codex supports stdio and http servers only")
        if p.scope != "user":
            raise ValueError("Codex servers are global; use scope 'user'")
        if getattr(p, "headers", None):
            raise ValueError("Codex can't set headers; use bearer_token_env_var")

    def add(self, p):
        args = ["mcp", "add", p.name]
        if p.transport == "stdio":
            for k, v in p.env.items():
                args += ["--env", f"{k}={v}"]
            return args + ["--", p.command, *p.args], None
        args += ["--url", p.url]
        if p.bearer_token_env_var:
            args += ["--bearer-token-env-var", p.bearer_token_env_var]
        return args, None

    def remove(self, p):
        return ["mcp", "remove", p.name], None


TOOL = Tool(id="codex", title="Codex", binary="codex", needs="Codex sessions and Codex MCP changes can't run",
            sessions=Sessions(), mcp=Mcp())
