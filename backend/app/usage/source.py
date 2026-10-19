"""Usage history: cost and tokens per day, tool, model and project, for every tool with a
usage reader (Claude Code transcripts, Codex rollouts).

Numbers come from the transcript index and are priced at query time, so fixing a price
corrects all history.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from app.config import Settings
from app.sources.base import Availability
from app.tools import TOOLS
from app.usage.index import UsageIndex
from app.usage.prices import DEFAULT_PRICES, PRICES_UPDATED, ModelPrice

COVERAGE_NOTE = (
    "Cost is computed from session transcripts at list prices. Claude Code makes a few background "
    "calls it doesn't write there (titles, compaction), so its cost can read slightly low; "
    "subscription plans aren't billed per token at all."
)


def _cost(p: ModelPrice, r) -> float:
    return (r["input"] * p.input + r["output"] * p.output + r["cache_read"] * p.cache_read
            + r["cache_write_5m"] * p.cache_write_5m + r["cache_write_1h"] * p.cache_write_1h) / 1e6


def _tokens(r) -> int:
    return r["input"] + r["output"] + r["cache_read"] + r["cache_write_5m"] + r["cache_write_1h"]


def _local_day(ts: str) -> date:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date()


class UsageSource:
    id = "usage"
    title = "Usage"

    def __init__(self, settings: Settings) -> None:
        readers = {t.id: t.usage for t in TOOLS.values() if t.usage}
        self.index = UsageIndex(settings.paths.data_dir / "usage.db", readers, settings)
        self.prices = {**DEFAULT_PRICES, **settings.pricing}

    def available(self) -> Availability:
        if self.index.transcript_files():
            return Availability(True)
        return Availability(False, "No session transcripts found for any tool")

    def snapshot(self) -> dict:
        return self.report(30)

    def report(self, days: int) -> dict:
        self.index.scan()
        today = date.today()
        start = today - timedelta(days=days - 1)
        start_local = datetime.combine(start, time.min).astimezone()
        since = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        per_day: dict[date, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"cost": 0.0, "tokens": 0}))
        models: dict[tuple[str, str], dict] = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "cache_read": 0,
                                                       "cache_write": 0, "tokens": 0, "messages": 0})
        projects: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "sessions": set()})
        unpriced: set[str] = set()
        sessions: set[str] = set()
        tools: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "sessions": set()})
        # A session belongs to the directory it started in, even if it later cd's elsewhere.
        session_project: dict[tuple[str, str], str] = {}

        for r in self.index.rows_since(since):
            day = _local_day(r["ts"])
            if day < start:
                continue
            price = self.prices.get(r["model"])
            cost = _cost(price, r) if price else 0.0
            if not price:
                unpriced.add(r["model"])
            tokens = _tokens(r)
            d = per_day[day][r["model"]]
            d["cost"] += cost
            d["tokens"] += tokens
            m = models[(r["tool"], r["model"])]
            m["cost"] += cost
            m["tokens"] += tokens
            m["messages"] += 1
            m["input"] += r["input"]
            m["output"] += r["output"]
            m["cache_read"] += r["cache_read"]
            m["cache_write"] += r["cache_write_5m"] + r["cache_write_1h"]
            project = r["project"] or "(unknown)"
            sid = (r["tool"], r["session_id"]) if r["session_id"] else None
            if sid:
                project = session_project.setdefault(sid, project)
            p = projects[project]
            p["cost"] += cost
            p["tokens"] += tokens
            t = tools[r["tool"]]
            t["cost"] += cost
            t["tokens"] += tokens
            if sid:
                p["sessions"].add(sid)
                t["sessions"].add(sid)
                sessions.add(sid)

        day_list = []
        for i in range(days):
            day = start + timedelta(days=i)
            day_list.append({"day": day.isoformat(), "models": {
                k: {"cost": round(v["cost"], 4), "tokens": v["tokens"]} for k, v in per_day.get(day, {}).items()}})

        by_model = sorted(({"model": model, "tool": tool, "priced": model not in unpriced, **v,
                            "cost": round(v["cost"], 4)} for (tool, model), v in models.items()),
                          key=lambda x: (-x["cost"], -x["tokens"]))
        by_tool = sorted(({"tool": k, "cost": round(v["cost"], 4), "tokens": v["tokens"], "sessions": len(v["sessions"])}
                          for k, v in tools.items()), key=lambda x: (-x["cost"], -x["tokens"]))
        by_project = sorted(({"project": k, "cost": round(v["cost"], 4), "tokens": v["tokens"],
                              "sessions": len(v["sessions"])} for k, v in projects.items()),
                            key=lambda x: (-x["cost"], -x["tokens"]))
        return {
            "range": {"days": days, "start": start.isoformat(), "end": today.isoformat()},
            "days": day_list,
            "by_model": by_model,
            "by_project": by_project,
            "by_tool": by_tool,
            "totals": {"cost": round(sum(m["cost"] for m in models.values()), 4),
                       "tokens": sum(m["tokens"] for m in models.values()),
                       "messages": sum(m["messages"] for m in models.values()),
                       "sessions": len(sessions)},
            "index": self.index.stats(),
            "pricing": {"updated": PRICES_UPDATED, "unpriced_models": sorted(unpriced)},
            "note": COVERAGE_NOTE,
        }
