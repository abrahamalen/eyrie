"""Codex: `codex`, state in ~/.codex (config.toml, state_5.sqlite)."""
import json
import sqlite3
import tomllib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.sessions.names import NAME_RE, UUID_RE, Name, clean
from app.tools._mcp import entry
from app.tools.base import Tool


def _db(settings: Settings) -> Path:
    return settings.paths.codex_home / "state_5.sqlite"


_index_cache: dict[Path, tuple[tuple[int, float], dict[str, str]]] = {}


def thread_names(settings: Settings) -> dict[str, str]:
    """~/.codex/session_index.jsonl: one line per rename, {id, thread_name, updated_at}; the
    last line for an id wins. Cached on (size, mtime)."""
    path = settings.paths.codex_home / "session_index.jsonl"
    try:
        st = path.stat()
    except OSError:
        return {}
    key = (st.st_size, st.st_mtime)
    hit = _index_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    names: dict[str, str] = {}
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        name = clean(d.get("thread_name")) if isinstance(d, dict) else None
        if name and isinstance(d.get("id"), str):
            names[d["id"]] = name
    _index_cache[path] = (key, names)
    return names


class Sessions:
    modes = ("new", "continue", "resume")
    resume_requires_cwd = False
    compact_command = "/compact"
    # OpenAI's longest prompt-cache retention: a conservative upper bound (docs/stop-and-idle.md §3.2).
    cache_minutes = (24 * 60, 24 * 60)
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

    def names(self, settings: Settings):
        """Thread names from session_index.jsonl (Codex doesn't record whether you or it named
        a thread, so they're all "tool"). Codex leaves no per-process trace, so without a
        resume id the thread is a guess: the newest one in that directory touched since the
        process started."""
        names = thread_names(settings)
        recent: list[tuple[str, str, int]] | None = None

        def threads() -> list[tuple[str, str, int]]:
            nonlocal recent
            if recent is None:
                recent = []
                db = _db(settings)
                if db.exists():
                    try:
                        with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                            recent = con.execute("SELECT id, cwd, updated_at FROM threads ORDER BY updated_at DESC LIMIT 500").fetchall()
                    except sqlite3.Error:
                        pass
            return recent

        def lookup(pid, cwd, conversation_id, resume, started):
            conv, exact = conversation_id, True
            if not conv and resume:
                if UUID_RE.match(resume):
                    conv = resume
                elif NAME_RE.match(resume):
                    conv = next((i for i, n in names.items() if n == resume), None)
            if not conv and cwd and started:
                since = started.timestamp() - 5
                conv = next((i for i, c, upd in threads() if c == cwd and (upd or 0) >= since), None)
                exact = False
            if not conv:
                return Name()
            name = names.get(conv)
            return Name(conv, name, "tool" if name else "id", exact)
        return lookup


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
    scopes = ("user",)
    transports = ("stdio", "http")
    headers = False
    bearer_token_env_var = True

    def servers(self, settings: Settings) -> list[dict]:
        path = settings.paths.codex_home / "config.toml"
        try:
            servers = tomllib.loads(path.read_text()).get("mcp_servers") or {}
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            return []
        return [entry(n, c, "codex", "user") for n, c in servers.items() if isinstance(c, dict)]

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
            home=lambda s: s.paths.codex_home,
            sessions=Sessions(), usage=Usage(), mcp=Mcp())
