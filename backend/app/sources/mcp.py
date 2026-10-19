"""MCP servers across every tool with MCP support (Claude Code's user, local and project
scopes; Codex's global config), read from their own config files, plus last-known connect failures recovered from recent session
transcripts. There's no way to live-ping an MCP server from outside a running session
(`claude mcp list` would launch every stdio server), so "last known" is the honest framing.
"""
import re
from pathlib import Path

from app.config import Settings
from app.sources.base import Availability, path_availability
from app.tools import TOOLS

ARRAY_RE = re.compile(r'"failedMcpServers":\[(.*?)\]')
ENTRY_RE = re.compile(r'\{"name":"([^"]+)","errorCode":"([^"]*)","error":"([^"]*)"\}')


class McpSource:
    id = "mcp"
    title = "MCP servers"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # path -> ((mtime_ns, size), failures found in that transcript). Transcripts are large
        # and polled often; only re-read the ones that changed.
        self._parsed: dict[Path, tuple[tuple[int, int], list[tuple[str, str]]]] = {}

    def available(self) -> Availability:
        return path_availability(self.settings.paths.claude_json, "~/.claude.json")

    def snapshot(self) -> dict:
        return {"configured": self.configured(), "last_known_failures": self._last_known_failures()}

    def configured(self) -> list[dict]:
        hidden = set(self.settings.privacy.hide_mcp)
        return [e for e in self._all() if e["name"] not in hidden]

    def find(self, client: str, name: str, scope: str, project: str | None) -> dict | None:
        for e in self._all():
            if (e["client"], e["name"], e["scope"]) == (client, name, scope) and (scope == "user" or e["project"] == project):
                return e
        return None

    def _all(self) -> list[dict]:
        return [e for t in TOOLS.values() if t.mcp for e in t.mcp.servers(self.settings)]

    def _last_known_failures(self) -> list[dict]:
        proj_dir = self.settings.paths.claude_home / "projects"
        if not proj_dir.exists():
            return []
        hidden = set(self.settings.privacy.hide_mcp)
        stats = []
        for f in proj_dir.glob("*/*.jsonl"):
            try:
                stats.append((f, f.stat()))
            except OSError:
                continue
        recent = sorted(stats, key=lambda x: x[1].st_mtime, reverse=True)[:15]
        self._parsed = {f: v for f, v in self._parsed.items() if any(f == r[0] for r in recent)}
        seen: dict[str, dict] = {}
        for f, st in recent:
            key = (st.st_mtime_ns, st.st_size)
            cached = self._parsed.get(f)
            if cached and cached[0] == key:
                found = cached[1]
            else:
                try:
                    text = f.read_text(errors="ignore")
                except Exception:
                    continue
                found = [(name, code or err) for m in ARRAY_RE.finditer(text) for name, code, err in ENTRY_RE.findall(m.group(1))]
                self._parsed[f] = (key, found)
            for name, detail in found:
                if name in hidden:
                    continue
                prior = seen.get(name)
                if prior is None or st.st_mtime > prior["_mtime"]:
                    seen[name] = {"name": name, "status": "failed", "detail": detail, "_mtime": st.st_mtime}
        for v in seen.values():
            v.pop("_mtime", None)
        return list(seen.values())
