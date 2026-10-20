"""Gemini CLI: `gemini` (a Node script), state in ~/.gemini.

Layout (gemini-cli packages/core: config/storage.ts, config/projectRegistry.ts,
services/chatRecordingService.ts):
- ~/.gemini/projects.json maps each project root to a short id (a slug of its folder name),
  and ~/.gemini/tmp/<id>/ holds that project's data, with a `.project_root` marker naming
  the root. Older versions used sha256(root) as the folder name; both are read.
- Sessions are append-only JSON Lines, ~/.gemini/tmp/<id>/chats/session-<time>-<sid8>.jsonl.
  The first line is metadata ({sessionId, projectHash, startTime, ...}); then message
  records ({id, type: "user"|"gemini", timestamp, model, tokens, ...}); then updates
  ({$set}, {$patch}, {$rewindTo}). A message can be written again with the same id as it
  grows. Subagents are chats/<parentSessionId>/<agentId>.jsonl.
- MCP servers are in settings.json (user: ~/.gemini, project: <root>/.gemini) under
  mcpServers: command/args/env/cwd for stdio, url for SSE, httpUrl for streamable HTTP.
Older single-file .json sessions are skipped (newer CLIs convert them on load).
"""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.masking import mask_args, mask_url
from app.sessions.names import Name, clean, tail_records
from app.sources.claude import safe_read_json
from app.tools.base import Tool

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def project_dirs(settings: Settings) -> dict[str, Path]:
    """Project root → its data folder, from the registry, the markers, and legacy hashes."""
    tmp = settings.paths.gemini_home / "tmp"
    out: dict[str, Path] = {}
    reg = (safe_read_json(settings.paths.gemini_home / "projects.json") or {}).get("projects") or {}
    for root, short in reg.items():
        if isinstance(short, str) and (tmp / short).is_dir():
            out[root] = tmp / short
    if tmp.is_dir():
        for d in tmp.iterdir():
            marker = d / ".project_root"
            if d.is_dir() and marker.is_file():
                try:
                    out.setdefault(marker.read_text().strip(), d)
                except OSError:
                    pass
    return out


def data_dir(settings: Settings, root: str) -> Path | None:
    d = project_dirs(settings).get(root)
    if d:
        return d
    legacy = settings.paths.gemini_home / "tmp" / hashlib.sha256(root.encode()).hexdigest()
    return legacy if legacy.is_dir() else None


class Sessions:
    modes = ("new", "continue", "resume")
    resume_requires_cwd = True
    helpers = frozenset({"mcp", "extensions", "--version", "-v", "-h", "--help", "--list-sessions",
                         "--delete-session"})

    def argv(self, exe, mode, cwd, resume_id, conversation_id):
        # Gemini keys sessions by the directory it starts in (tmux starts it in cwd), and a
        # new session takes no arguments; `env` keeps the program 2+ items so tmux execs it
        # without a shell.
        return {"new": ["/usr/bin/env", exe], "continue": [exe, "--resume", "latest"],
                "resume": [exe, "--resume", resume_id]}[mode]

    def wants_conversation_id(self, mode):
        return False

    def activity(self, settings: Settings):
        dirs = project_dirs(settings)

        def lookup(cwd, resume):
            d = dirs.get(cwd or "") or (data_dir(settings, cwd) if cwd else None)
            chats = d / "chats" if d else None
            if not chats or not chats.is_dir():
                return None, False
            if resume and UUID_RE.match(resume):
                exact = sorted(chats.glob(f"session-*-{resume[:8]}.jsonl"), key=lambda f: f.stat().st_mtime)
                if exact:
                    return datetime.fromtimestamp(exact[-1].stat().st_mtime, tz=timezone.utc), True
            mtimes = [f.stat().st_mtime for f in chats.glob("session-*.jsonl")]
            return (datetime.fromtimestamp(max(mtimes), tz=timezone.utc) if mtimes else None), False
        return lookup

    def known_dirs(self, settings: Settings) -> set[Path]:
        return {Path(root) for root in project_dirs(settings)}

    def names(self, settings: Settings):
        """Gemini has no rename; a session's `summary` (written by `{"$set": {"summary": …}}`
        updates) is its title. The file is chats/session-<time>-<sid8>.jsonl: by id when the
        session was resumed by id, else the newest one written since the process started."""
        dirs = project_dirs(settings)

        def lookup(pid, cwd, conversation_id, resume, started):
            conv = conversation_id or (resume if resume and UUID_RE.match(resume) else None)
            d = dirs.get(cwd or "") or (data_dir(settings, cwd) if cwd else None)
            chats = d / "chats" if d else None
            if not chats or not chats.is_dir():
                return Name(conv)
            if conv:
                files, exact = sorted(chats.glob(f"session-*-{conv[:8]}.jsonl"), key=_mtime), True
            else:
                since = started.timestamp() - 5 if started else 0
                files = sorted((f for f in chats.glob("session-*.jsonl") if _mtime(f) >= since), key=_mtime)
                exact = False
            if not files:
                return Name(conv)
            sid = _session_id(files[-1]) or conv
            summary = None
            for r in tail_records(files[-1], needle=b'"summary"'):
                s = r.get("$set") if isinstance(r.get("$set"), dict) else r
                summary = clean(s.get("summary")) or summary
            if not sid:
                return Name()
            return Name(sid, summary, "tool" if summary else "id", exact)
        return lookup


def _mtime(f: Path) -> float:
    try:
        return f.stat().st_mtime
    except OSError:
        return 0.0


def _session_id(path: Path) -> str | None:
    """The metadata line (the first) names the session."""
    try:
        with path.open("rb") as f:
            first = json.loads(f.readline(65536) or b"{}")
    except (OSError, ValueError):
        return None
    sid = first.get("sessionId") if isinstance(first, dict) else None
    return sid if isinstance(sid, str) and UUID_RE.match(sid) else None


class Usage:
    """`gemini` messages with `tokens`. The Gemini API counts cached tokens inside the prompt
    count and reports thinking and tool-use prompt tokens separately, so a row stores
    input = prompt - cached + tool, cache_read = cached, output = candidates + thoughts.
    Rewound messages stay counted: the calls were made (and billed)."""
    needles = (b'"tokens"', b'"sessionId"')

    def files(self, settings: Settings) -> list[tuple[Path, bool]]:
        tmp = settings.paths.gemini_home / "tmp"
        if not tmp.is_dir():
            return []
        top = [(p, False) for p in tmp.glob("*/chats/session-*.jsonl")]
        sub = [(p, True) for p in tmp.glob("*/chats/*/*.jsonl")]
        return top + sub

    def parse(self, d: dict, subagent: bool, state: dict):
        if "sessionId" in d and "projectHash" in d:
            state["session"] = d["sessionId"]
            dirs = d.get("directories")
            if isinstance(dirs, list) and dirs and isinstance(dirs[0], str):
                state["cwd"] = dirs[0]
            return None
        if "$patch" in d:
            # Patched messages carry their full new state; take the last one with tokens.
            ups = d["$patch"].get("updates") if isinstance(d.get("$patch"), dict) else None
            items = ups.values() if isinstance(ups, dict) else ups if isinstance(ups, list) else []
            rows = [r for r in (self._message(m, subagent, state) for m in items if isinstance(m, dict)) if r]
            return rows[-1] if rows else None
        return self._message(d, subagent, state)

    def _message(self, m: dict, subagent: bool, state: dict):
        t = m.get("tokens")
        if m.get("type") != "gemini" or not isinstance(t, dict) or not m.get("id") or not m.get("timestamp"):
            return None
        cached = t.get("cached") or 0
        fresh = max((t.get("input") or 0) - cached, 0) + (t.get("tool") or 0)
        return (f"gemini:{state.get('session')}:{m['id']}", m["timestamp"], state.get("session"), state.get("cwd"),
                m.get("model") or "unknown", int(subagent), fresh, (t.get("output") or 0) + (t.get("thoughts") or 0),
                cached, 0, 0)


def _entry(name: str, cfg: dict, scope: str, project: str | None) -> dict:
    url = cfg.get("httpUrl") or cfg.get("url")
    kind = "http" if cfg.get("httpUrl") else "sse" if cfg.get("url") else "stdio"
    target = mask_url(url) if url else " ".join(mask_args([cfg.get("command", ""), *cfg.get("args", [])])).strip()
    return {"name": name, "client": "gemini", "scope": scope, "type": kind, "target": target, "project": project}


class Mcp:
    scopes = ("user", "project")
    transports = ("stdio", "http", "sse")
    headers = True
    bearer_token_env_var = False

    def servers(self, settings: Settings) -> list[dict]:
        user = safe_read_json(settings.paths.gemini_home / "settings.json") or {}
        out = [_entry(n, c, "user", None) for n, c in (user.get("mcpServers") or {}).items() if isinstance(c, dict)]
        for root in project_dirs(settings):
            proj = safe_read_json(Path(root) / ".gemini" / "settings.json") or {}
            out += [_entry(n, c, "project", root) for n, c in (proj.get("mcpServers") or {}).items() if isinstance(c, dict)]
        return out

    def add(self, p):
        # gemini mcp add [options] <name> <commandOrUrl> [args...]; `--` so a server's own
        # flags (npx -y …) aren't read as gemini's.
        args = ["mcp", "add", "-s", p.scope, "-t", p.transport]
        for k, v in p.env.items():
            args += ["-e", f"{k}={v}"]
        for k, v in p.headers.items():
            args += ["-H", f"{k}: {v}"]
        cwd = Path(p.project_dir) if p.project_dir else None
        if p.transport == "stdio":
            return args + ["--", p.name, p.command, *p.args], cwd
        return args + ["--", p.name, p.url], cwd

    def remove(self, p):
        return ["mcp", "remove", "-s", p.scope, p.name], Path(p.project_dir) if p.project_dir else None


TOOL = Tool(id="gemini", title="Gemini CLI", binary="gemini",
            needs="Gemini CLI sessions and Gemini MCP changes can't run", home=lambda s: s.paths.gemini_home,
            sessions=Sessions(), usage=Usage(), mcp=Mcp())
