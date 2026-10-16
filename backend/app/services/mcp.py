"""Live MCP server status — configured servers from ~/.claude.json, last-known connect/fail
status recovered from recent session transcripts (there's no way to live-ping an MCP server
from outside a running Claude Code session, so 'last known' is the honest framing)."""
import json
import re
from pathlib import Path

HOME = Path.home()
ARRAY_RE = re.compile(r'"failedMcpServers":\[(.*?)\]')
ENTRY_RE = re.compile(r'\{"name":"([^"]+)","errorCode":"([^"]*)","error":"([^"]*)"\}')


def get_last_known_status() -> list[dict]:
    proj_dir = HOME / ".claude/projects"
    if not proj_dir.exists():
        return []
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
                prior = seen.get(name)
                if prior is None or mtime > prior["_mtime"]:
                    seen[name] = {"name": name, "status": "failed", "detail": code or err, "_mtime": mtime}
    for v in seen.values():
        v.pop("_mtime", None)
    return list(seen.values())
