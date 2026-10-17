"""Usage history: Claude Code cost and tokens per day, model and project, plus Codex totals.

Claude numbers come from the transcript index and are priced at query time, so fixing a
price corrects all history. Codex only stores a lifetime token total per thread, so it's
reported per thread and model, never spread across days.
"""
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone

from app.config import Settings
from app.sources.base import Availability, path_availability
from app.usage.index import UsageIndex
from app.usage.prices import DEFAULT_PRICES, PRICES_UPDATED, ModelPrice

COVERAGE_NOTE = (
    "Claude cost is computed from session transcripts. Claude Code makes a few background "
    "calls it doesn't write there (titles, compaction), so this can read slightly low."
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
        self.projects_dir = settings.paths.claude_home / "projects"
        self.codex_db = settings.paths.codex_home / "state_5.sqlite"
        self.index = UsageIndex(settings.paths.data_dir / "usage.db", self.projects_dir)
        self.prices = {**DEFAULT_PRICES, **settings.pricing}

    def available(self) -> Availability:
        return path_availability(self.projects_dir, "Claude Code transcripts")

    def snapshot(self) -> dict:
        return self.report(30)

    def report(self, days: int) -> dict:
        self.index.scan()
        today = date.today()
        start = today - timedelta(days=days - 1)
        start_local = datetime.combine(start, time.min).astimezone()
        since = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        per_day: dict[date, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"cost": 0.0, "tokens": 0}))
        models: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "cache_read": 0,
                                                       "cache_write": 0, "tokens": 0, "messages": 0})
        projects: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "tokens": 0, "sessions": set()})
        unpriced: set[str] = set()
        sessions: set[str] = set()
        # A session belongs to the directory it started in, even if it later cd's elsewhere.
        session_project: dict[str, str] = {}

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
            m = models[r["model"]]
            m["cost"] += cost
            m["tokens"] += tokens
            m["messages"] += 1
            m["input"] += r["input"]
            m["output"] += r["output"]
            m["cache_read"] += r["cache_read"]
            m["cache_write"] += r["cache_write_5m"] + r["cache_write_1h"]
            project = r["project"] or "(unknown)"
            if r["session_id"]:
                project = session_project.setdefault(r["session_id"], project)
            p = projects[project]
            p["cost"] += cost
            p["tokens"] += tokens
            if r["session_id"]:
                p["sessions"].add(r["session_id"])
                sessions.add(r["session_id"])

        day_list = []
        for i in range(days):
            day = start + timedelta(days=i)
            day_list.append({"day": day.isoformat(), "models": {
                k: {"cost": round(v["cost"], 4), "tokens": v["tokens"]} for k, v in per_day.get(day, {}).items()}})

        by_model = sorted(({"model": k, "priced": k not in unpriced, **v, "cost": round(v["cost"], 4)}
                           for k, v in models.items()), key=lambda x: (-x["cost"], -x["tokens"]))
        by_project = sorted(({"project": k, "cost": round(v["cost"], 4), "tokens": v["tokens"],
                              "sessions": len(v["sessions"])} for k, v in projects.items()),
                            key=lambda x: (-x["cost"], -x["tokens"]))
        return {
            "range": {"days": days, "start": start.isoformat(), "end": today.isoformat()},
            "days": day_list,
            "by_model": by_model,
            "by_project": by_project,
            "totals": {"cost": round(sum(m["cost"] for m in models.values()), 4),
                       "tokens": sum(m["tokens"] for m in models.values()),
                       "messages": sum(m["messages"] for m in models.values()),
                       "sessions": len(sessions)},
            "codex": self._codex(start_local),
            "index": self.index.stats(),
            "pricing": {"updated": PRICES_UPDATED, "unpriced_models": sorted(unpriced)},
            "note": COVERAGE_NOTE,
        }

    def _codex(self, start_local: datetime) -> dict:
        if not self.codex_db.exists():
            return {"available": False, "threads": 0, "tokens": 0, "by_model": []}
        try:
            with closing(sqlite3.connect(f"file:{self.codex_db}?mode=ro", uri=True)) as con:
                rows = con.execute(
                    "SELECT coalesce(model, 'unknown'), count(*), coalesce(sum(tokens_used), 0) FROM threads "
                    "WHERE archived = 0 AND updated_at >= ? GROUP BY 1 ORDER BY 3 DESC",
                    (int(start_local.timestamp()),),
                ).fetchall()
        except sqlite3.Error as e:
            return {"available": False, "error": str(e), "threads": 0, "tokens": 0, "by_model": []}
        return {
            "available": True,
            "threads": sum(r[1] for r in rows),
            "tokens": sum(r[2] for r in rows),
            "by_model": [{"model": m, "threads": n, "tokens": t} for m, n, t in rows],
        }
