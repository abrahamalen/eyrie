"""Claude Code: `claude`, state in ~/.claude.json and ~/.claude/projects/*/*.jsonl."""
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.sources.claude import safe_read_json
from app.tools._mcp import entry
from app.tools.base import Tool

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def transcript_dir(claude_home: Path, cwd: str) -> Path:
    # Claude Code keeps a project's transcripts under its path with non-alphanumerics as "-".
    return claude_home / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)


class Sessions:
    modes = ("new", "continue", "resume")
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


class Mcp:
    def servers(self, settings: Settings) -> list[dict]:
        d = safe_read_json(settings.paths.claude_json) or {}
        out = [entry(n, c, "claude", "user") for n, c in (d.get("mcpServers") or {}).items()]
        for project, p in (d.get("projects") or {}).items():
            out += [entry(n, c, "claude", "local", project) for n, c in (p.get("mcpServers") or {}).items()]
            shared = safe_read_json(Path(project) / ".mcp.json") or {}
            out += [entry(n, c, "claude", "project", project) for n, c in (shared.get("mcpServers") or {}).items()]
        return out

    def validate(self, p) -> None:
        if getattr(p, "bearer_token_env_var", None):
            raise ValueError("bearer_token_env_var is Codex-only; use headers for Claude Code")

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
            needs="Claude Code sessions and MCP/plugin changes can't run",
            sessions=Sessions(), mcp=Mcp(), plugins=True)
