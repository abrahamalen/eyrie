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


def _usage_row(key: str, ts: str, state: dict, u: dict):
    # OpenAI counts cached (and cache-written) tokens inside input_tokens; reasoning tokens are
    # inside output_tokens. Store input as the uncached part so pricing can't double-count.
    cached = u.get("cached_input_tokens") or 0
    written = u.get("cache_write_input_tokens") or 0
    fresh = max((u.get("input_tokens") or 0) - cached - written, 0)
    return (key, ts, state.get("session"), state.get("cwd"), state.get("model") or "unknown", 0,
            fresh, u.get("output_tokens") or 0, cached, written, 0)


class Usage:
    """Per-call usage from ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl.

    The session and directory come from the `session_meta` line and the model from the latest
    `turn_context`, so they're carried in the per-file state. Newer Codex writes one
    `token_usage_record` per API response (keyed on its response_id); older rollouts only have
    `token_count` events, whose `last_token_usage` is one call and whose running total is
    repeated when nothing changed, so they're keyed on (session, running total). Once a file
    has records, its token_count events are ignored, so a call isn't counted twice.
    """
    needles = (b'"session_meta"', b'"turn_context"', b'"token_usage_record"', b'"token_count"')

    def files(self, settings: Settings) -> list[tuple[Path, bool]]:
        d = settings.paths.codex_home / "sessions"
        return [(p, False) for p in d.glob("*/*/*/rollout-*.jsonl")] if d.exists() else []

    def parse(self, d: dict, subagent: bool, state: dict):
        kind, p, ts = d.get("type"), d.get("payload") or {}, d.get("timestamp")
        if kind == "session_meta":
            state["session"], state["cwd"] = p.get("id"), p.get("cwd")
        elif kind == "turn_context":
            state["model"] = p.get("model") or state.get("model")
            state["cwd"] = p.get("cwd") or state.get("cwd")
        elif kind == "token_usage_record" and ts and isinstance(p.get("usage"), dict):
            state["records"] = True
            return _usage_row(f"codex:{p.get('response_id') or ts}", ts, state, p["usage"])
        elif kind == "event_msg" and p.get("type") == "token_count" and ts and not state.get("records"):
            info = p.get("info") or {}
            last, total = info.get("last_token_usage"), info.get("total_token_usage") or {}
            if isinstance(last, dict) and total.get("total_tokens"):
                return _usage_row(f"codex:{state.get('session')}:{total['total_tokens']}", ts, state, last)
        return None


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
            sessions=Sessions(), usage=Usage(), mcp=Mcp())
