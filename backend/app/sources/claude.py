"""Claude Code usage from ~/.claude.json, read fresh on every call.

The file is small (hundreds of KB), so there's no need for a background poller; every
request is already live. Cost here is the last session per project; full history comes
with the usage indexer.
"""
import json
from pathlib import Path

from app.config import Settings
from app.sources.base import Availability, path_availability


def safe_read_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def configured_mcp(settings: Settings) -> list[dict]:
    d = safe_read_json(settings.paths.claude_json) or {}
    hidden = set(settings.privacy.hide_mcp)
    return [
        {"name": name, "type": cfg.get("type", "?"), "scope": "user"}
        for name, cfg in (d.get("mcpServers") or {}).items()
        if name not in hidden
    ]


class ClaudeSource:
    id = "claude"
    title = "Claude Code"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> Availability:
        return path_availability(self.settings.paths.claude_json, "~/.claude.json")

    def snapshot(self) -> dict:
        d = safe_read_json(self.settings.paths.claude_json) or {}
        projects = d.get("projects", {})
        rows = []
        totals = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
                  "cache_read_tokens": 0, "cache_creation_tokens": 0}
        by_model: dict[str, dict] = {}

        for path, p in projects.items():
            cost = p.get("lastCost") or 0
            tin = p.get("lastTotalInputTokens") or 0
            tout = p.get("lastTotalOutputTokens") or 0
            tcr = p.get("lastTotalCacheReadInputTokens") or 0
            tcc = p.get("lastTotalCacheCreationInputTokens") or 0
            if not (cost or tin or tout):
                continue
            totals["cost_usd"] += cost
            totals["input_tokens"] += tin
            totals["output_tokens"] += tout
            totals["cache_read_tokens"] += tcr
            totals["cache_creation_tokens"] += tcc

            models = p.get("lastModelUsage") or {}
            for m, mu in models.items():
                bm = by_model.setdefault(m, {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
                bm["cost_usd"] += mu.get("costUSD") or 0
                bm["input_tokens"] += mu.get("inputTokens") or 0
                bm["output_tokens"] += mu.get("outputTokens") or 0

            rows.append({
                "path": path,
                "cost_usd": round(cost, 4),
                "input_tokens": tin,
                "output_tokens": tout,
                "cache_read_tokens": tcr,
                "cache_creation_tokens": tcc,
                "models": list(models.keys()),
                "last_start_time": p.get("lastStartTime"),
            })

        rows.sort(key=lambda r: r["cost_usd"], reverse=True)
        totals["cost_usd"] = round(totals["cost_usd"], 4)
        for m in by_model:
            by_model[m]["cost_usd"] = round(by_model[m]["cost_usd"], 4)

        settings_json = safe_read_json(self.settings.paths.claude_home / "settings.json") or {}
        return {
            "projects": rows,
            "totals": totals,
            "by_model": by_model,
            "enabled_plugins": list((settings_json.get("enabledPlugins") or {}).keys()),
            "configured_mcp": configured_mcp(self.settings),
        }
