"""MCP servers: configured ones from ~/.claude.json, plus last-known connect failures recovered
from recent session transcripts. There's no way to live-ping an MCP server from outside a
running Claude Code session, so "last known" is the honest framing."""
import re

from app.config import Settings
from app.sources.base import Availability, path_availability
from app.sources.claude import configured_mcp

ARRAY_RE = re.compile(r'"failedMcpServers":\[(.*?)\]')
ENTRY_RE = re.compile(r'\{"name":"([^"]+)","errorCode":"([^"]*)","error":"([^"]*)"\}')


class McpSource:
    id = "mcp"
    title = "MCP servers"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> Availability:
        return path_availability(self.settings.paths.claude_json, "~/.claude.json")

    def snapshot(self) -> dict:
        return {
            "configured": configured_mcp(self.settings),
            "last_known_failures": self._last_known_failures(),
        }

    def _last_known_failures(self) -> list[dict]:
        proj_dir = self.settings.paths.claude_home / "projects"
        if not proj_dir.exists():
            return []
        hidden = set(self.settings.privacy.hide_mcp)
        jsonl_files = sorted(proj_dir.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        seen: dict[str, dict] = {}
        for f in jsonl_files:
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            mtime = f.stat().st_mtime
            for arr_match in ARRAY_RE.finditer(text):
                for name, code, err in ENTRY_RE.findall(arr_match.group(1)):
                    if name in hidden:
                        continue
                    prior = seen.get(name)
                    if prior is None or mtime > prior["_mtime"]:
                        seen[name] = {"name": name, "status": "failed", "detail": code or err, "_mtime": mtime}
        for v in seen.values():
            v.pop("_mtime", None)
        return list(seen.values())
