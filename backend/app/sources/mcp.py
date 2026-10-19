"""MCP servers across Claude Code (user, local and project scopes) and Codex, read from
their own config files, plus last-known connect failures recovered from recent session
transcripts. There's no way to live-ping an MCP server from outside a running session
(`claude mcp list` would launch every stdio server), so "last known" is the honest framing.
"""
import re
import tomllib
from pathlib import Path

from app.config import Settings
from app.masking import mask_args, mask_url
from app.sources.base import Availability, path_availability
from app.sources.claude import safe_read_json

ARRAY_RE = re.compile(r'"failedMcpServers":\[(.*?)\]')
ENTRY_RE = re.compile(r'\{"name":"([^"]+)","errorCode":"([^"]*)","error":"([^"]*)"\}')


def _entry(name: str, cfg: dict, client: str, scope: str, project: str | None = None) -> dict:
    kind = cfg.get("type") or ("http" if cfg.get("url") else "stdio")
    target = (mask_url(cfg["url"]) if cfg.get("url")
              else " ".join(mask_args([cfg.get("command", ""), *cfg.get("args", [])])).strip())
    return {"name": name, "client": client, "scope": scope, "type": kind, "target": target, "project": project}


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
        return [e for e in self._claude() + self._codex() if e["name"] not in hidden]

    def find(self, client: str, name: str, scope: str, project: str | None) -> dict | None:
        for e in self._claude() + self._codex():
            if (e["client"], e["name"], e["scope"]) == (client, name, scope) and (scope == "user" or e["project"] == project):
                return e
        return None

    def _claude(self) -> list[dict]:
        d = safe_read_json(self.settings.paths.claude_json) or {}
        out = [_entry(n, c, "claude", "user") for n, c in (d.get("mcpServers") or {}).items()]
        for project, p in (d.get("projects") or {}).items():
            out += [_entry(n, c, "claude", "local", project) for n, c in (p.get("mcpServers") or {}).items()]
            shared = safe_read_json(Path(project) / ".mcp.json") or {}
            out += [_entry(n, c, "claude", "project", project) for n, c in (shared.get("mcpServers") or {}).items()]
        return out

    def _codex(self) -> list[dict]:
        path = self.settings.paths.codex_home / "config.toml"
        try:
            servers = tomllib.loads(path.read_text()).get("mcp_servers") or {}
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            return []
        return [_entry(n, c, "codex", "user") for n, c in servers.items() if isinstance(c, dict)]

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
