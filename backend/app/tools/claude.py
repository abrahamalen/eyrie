"""Claude Code: `claude`, state in ~/.claude.json and ~/.claude/projects/*/*.jsonl."""
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.sessions.names import NAME_RE, Name, clean, tail_records
from app.sources.claude import safe_read_json
from app.tools._mcp import entry
from app.tools.base import Tool
from app.usage.prices import normalize_model

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHORT_ID = re.compile(r"^[0-9a-f]{8}$")


def transcript_dir(claude_home: Path, cwd: str) -> Path:
    # Claude Code keeps a project's transcripts under its path with non-alphanumerics as "-".
    return claude_home / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)


class Sessions:
    modes = ("new", "continue", "resume")
    resume_requires_cwd = False
    helpers = frozenset({"daemon", "bg-pty-host", "bg-spare", "mcp", "mcp-server", "login", "logout", "plugin",
                         "--version", "-v", "doctor", "update", "install"})

    def argv(self, exe, mode, cwd, resume_id, conversation_id):
        return {"new": [exe, "--session-id", conversation_id], "continue": [exe, "--continue"],
                "resume": [exe, "--resume", resume_id]}[mode]

    def wants_conversation_id(self, mode):
        return mode == "new"

    def activity(self, settings: Settings):
        def lookup(cwd, resume):
            if not cwd:
                return None, False
            d = transcript_dir(settings.paths.claude_home, cwd)
            exact = d / f"{resume}.jsonl" if resume and UUID_RE.match(resume) else None
            if exact and exact.exists():
                return datetime.fromtimestamp(exact.stat().st_mtime, tz=timezone.utc), True
            mtimes = [f.stat().st_mtime for f in d.glob("*.jsonl")] if d.is_dir() else []
            return (datetime.fromtimestamp(max(mtimes), tz=timezone.utc) if mtimes else None), False
        return lookup

    def known_dirs(self, settings: Settings) -> set[Path]:
        return {Path(p) for p in ((safe_read_json(settings.paths.claude_json) or {}).get("projects") or {})}

    def names(self, settings: Settings):
        """Running claude writes ~/.claude/sessions/<pid>.json with its conversation id and
        name (nameSource "user" after /rename or --resume <name>; "auto"/"derived" when Claude
        chose it). Otherwise the transcript's last custom-title (yours) or ai-title (Claude's),
        which Claude re-appends near the end of the file after each turn."""
        home = settings.paths.claude_home

        def lookup(pid, cwd, conversation_id, resume, started):
            conv = conversation_id
            if pid:
                d = safe_read_json(home / "sessions" / f"{pid}.json")
                sid = d.get("sessionId") if isinstance(d, dict) and d.get("pid") == pid else None
                if isinstance(sid, str) and UUID_RE.match(sid):
                    conv = sid
                    name = clean(d.get("name"))
                    if name and d.get("nameSource") and name != sid[:8]:
                        return Name(sid, name, "user" if d["nameSource"] == "user" else "tool")
            if not conv and resume and SHORT_ID.match(resume):
                # `claude attach <id8>`: a terminal on a background session, which has its own pid file.
                for f in (home / "sessions").glob("*.json"):
                    d = safe_read_json(f)
                    sid = d.get("sessionId") if isinstance(d, dict) else None
                    if isinstance(sid, str) and UUID_RE.match(sid) and sid.startswith(resume):
                        name = clean(d.get("name"))
                        if name and d.get("nameSource") and name != sid[:8]:
                            return Name(sid, name, "user" if d["nameSource"] == "user" else "tool")
                        return Name(sid)
            if not conv and resume and UUID_RE.match(resume):
                conv = resume
            if conv and cwd:
                found = _transcript_name(transcript_dir(home, cwd) / f"{conv}.jsonl")
                if found:
                    return Name(conv, *found)
            if conv:
                return Name(conv)
            if resume and NAME_RE.match(resume):
                return Name(None, clean(resume), "user")
            return Name()
        return lookup


def _transcript_name(path: Path) -> tuple[str, str] | None:
    custom = ai = None
    for r in tail_records(path, needle=b'Title"'):
        if r.get("type") == "custom-title":
            custom = clean(r.get("customTitle")) or custom
        elif r.get("type") == "ai-title":
            ai = clean(r.get("aiTitle")) or ai
    if custom:
        return custom, "user"
    return (ai, "tool") if ai else None


class Usage:
    """Assistant lines of ~/.claude/projects transcripts.

    One API response is written as several lines (one per content block), each repeating its
    usage, and streaming lines can carry partial output counts: rows are keyed on
    (message.id, requestId) and the index keeps the max of each counter. Subagent runs live in
    <session>/subagents/*.jsonl and are billed to the parent session. Model ids may carry
    suffixes ([1m], -YYYYMMDD); "<synthetic>" rows aren't API calls.
    """
    needles = (b'"usage"',)

    def files(self, settings: Settings) -> list[tuple[Path, bool]]:
        d = settings.paths.claude_home / "projects"
        if not d.exists():
            return []
        return [(p, False) for p in d.glob("*/*.jsonl")] + [(p, True) for p in d.glob("*/*/subagents/*.jsonl")]

    def parse(self, d: dict, subagent: bool, state: dict):
        if d.get("type") != "assistant":
            return None
        m = d.get("message")
        if not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            return None
        model = m.get("model") or ""
        if not model or model == "<synthetic>" or not d.get("timestamp"):
            return None
        u = m["usage"]
        split = u.get("cache_creation")
        if isinstance(split, dict):
            w5, w1 = split.get("ephemeral_5m_input_tokens") or 0, split.get("ephemeral_1h_input_tokens") or 0
        else:
            w5, w1 = u.get("cache_creation_input_tokens") or 0, 0
        key = f"{m.get('id') or d.get('uuid')}|{d.get('requestId') or ''}"
        return (key, d["timestamp"], d.get("sessionId"), d.get("cwd"), normalize_model(model), int(subagent),
                u.get("input_tokens") or 0, u.get("output_tokens") or 0, u.get("cache_read_input_tokens") or 0, w5, w1)


class Mcp:
    scopes = ("user", "local", "project")
    transports = ("stdio", "http", "sse")
    headers = True
    bearer_token_env_var = False

    def servers(self, settings: Settings) -> list[dict]:
        d = safe_read_json(settings.paths.claude_json) or {}
        out = [entry(n, c, "claude", "user") for n, c in (d.get("mcpServers") or {}).items()]
        for project, p in (d.get("projects") or {}).items():
            out += [entry(n, c, "claude", "local", project) for n, c in (p.get("mcpServers") or {}).items()]
            shared = safe_read_json(Path(project) / ".mcp.json") or {}
            out += [entry(n, c, "claude", "project", project) for n, c in (shared.get("mcpServers") or {}).items()]
        return out

    def add(self, p):
        cwd = Path(p.project_dir) if p.project_dir else None
        args = ["mcp", "add", "-s", p.scope, "-t", p.transport, p.name]
        if p.transport == "stdio":
            for k, v in p.env.items():
                args += ["-e", f"{k}={v}"]
            return args + ["--", p.command, *p.args], cwd
        args.append(p.url)
        for k, v in p.headers.items():
            args += ["-H", f"{k}: {v}"]
        return args, cwd

    def remove(self, p):
        return ["mcp", "remove", "-s", p.scope, p.name], Path(p.project_dir) if p.project_dir else None


TOOL = Tool(id="claude", title="Claude Code", binary="claude",
            needs="Claude Code sessions and MCP/plugin changes can't run", home=lambda s: s.paths.claude_home,
            sessions=Sessions(), usage=Usage(), mcp=Mcp(), plugins=True)
