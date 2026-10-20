"""One answer to "what needs me, and what's going on?" for the home page and the widget
(docs/home-and-widget.md §2). Built only from existing sources, so the two views can never
disagree with the pages they link to."""
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.actions.runner import CliNotFound, Runner
from app.config import Settings
from app.sessions.dirs import is_allowed
from app.tools import TOOLS, enabled, used as tool_used

# tmux, then each tool: how to ask for its version.
PROBES = {"tmux": ["-V"], **{t.id: list(t.version_args) for t in TOOLS.values()}}
VERSION_RE = re.compile(r"\d+(?:\.\d+)+[a-z]?")
SEVERITY = {"problem": 0, "attention": 1}


class Versions:
    """`tool --version`, cached until the binary changes; polled views shouldn't spawn processes."""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self._cache: dict[str, tuple[tuple, dict]] = {}
        self._lock = threading.Lock()

    def get(self, tool: str) -> dict:
        try:
            path = Path(self.runner.binary(tool))
        except CliNotFound:
            return {"found": False, "version": None, "path": None}
        try:
            st = path.stat()
            key = (str(path), st.st_mtime_ns, st.st_size)
        except OSError:
            key = (str(path),)
        with self._lock:
            hit = self._cache.get(tool)
            if hit and hit[0] == key:
                return hit[1]
        r = self.runner.run(tool, PROBES[tool])
        m = VERSION_RE.search(r.stdout + r.stderr) if r.ok else None
        info = {"found": True, "version": m.group(0) if m else None, "path": str(path)}
        with self._lock:
            self._cache[tool] = (key, info)
        return info


def _minutes_since(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    return int((now - datetime.fromisoformat(iso)).total_seconds() // 60)


def build_summary(settings: Settings, registry: dict, versions: Versions) -> dict:
    now = datetime.now(timezone.utc)
    attention: list[dict] = []

    on = enabled(settings)
    # Tools you haven't enabled get no health entry at all; tmux always matters.
    health = {tool: {**versions.get(tool), "used": tool_used(settings, tool)} if tool == "tmux" or tool in on else None
              for tool in PROBES}
    needs = {"tmux": "Sessions can't start or be opened", **{t.id: t.needs for t in TOOLS.values()}}
    for tool, info in health.items():
        # An enabled tool you've never run here (auto-enabled because it's on PATH) can't be
        # missing; one you use (or listed explicitly) can.
        if info and not info["found"] and (info["used"] or settings.tools.enabled != "auto"):
            attention.append({"kind": "cli_missing", "severity": "problem", "title": f"{tool} isn't installed",
                              "detail": f"{needs[tool]}. Install it, or set cli.{tool}_bin in eyrie.toml.",
                              "href": "/", "since": None})

    # Sessions
    sessions = []
    src = registry.get("sessions")
    snap = src.snapshot() if src else {"sessions": []}
    for s in snap["sessions"]:
        idle = _minutes_since(s["last_output"], now) if s["alive"] else None
        sessions.append({"name": s["name"], "tool": s["tool"], "project": s["cwd"], "alive": s["alive"],
                         "exit_status": s["exit_status"], "idle_minutes": idle, "last_output": s["last_output"],
                         "managed": True, "tty": None, "pid": None})
        tool = TOOLS[s["tool"]].title if s["tool"] in TOOLS else (s["tool"] or "Unknown tool")
        where = s["cwd"] or "unknown directory"
        if not s["alive"] and s["exit_status"] not in (None, 0):
            attention.append({"kind": "session_exited_error", "severity": "problem",
                              "title": f"{s['name']} exited with code {s['exit_status']}", "detail": f"{tool} · {where}",
                              "href": f"/sessions?open={s['name']}", "since": s["last_output"]})
        elif idle is not None and idle >= settings.sessions.idle_minutes:
            attention.append({"kind": "session_idle", "severity": "attention",
                              "title": f"{s['name']} has been idle {idle} min",
                              "detail": f"Probably waiting for you · {tool} · {where}",
                              "href": f"/sessions?open={s['name']}", "since": s["last_output"]})

    # Sessions in your own terminals: listed so the count is honest, but never flagged as idle;
    # parking a terminal session is normal, and Eyrie can't open it anyway.
    for e in snap.get("external", []):
        sessions.append({"name": f"{e['tool']} · {e['tty']}", "tool": e["tool"], "project": e["cwd"], "alive": True,
                         "exit_status": None, "idle_minutes": e["idle_minutes"], "last_output": e["last_activity"],
                         "managed": False, "tty": e["tty"], "pid": e["pid"]})

    # MCP: only servers you configured (hidden ones are already filtered by the source)
    mcp = registry.get("mcp")
    if mcp:
        m = mcp.snapshot()
        configured = {c["name"]: c for c in m["configured"]}
        for f in m["last_known_failures"]:
            c = configured.get(f["name"])
            if c is None:
                continue
            client = TOOLS[c["client"]].title
            attention.append({"kind": "mcp_failed", "severity": "attention",
                              "title": f"MCP server {f['name']} failed to connect",
                              "detail": f"{client} · {c['scope']} scope · {f['detail']}", "href": "/mcp", "since": None})

    # Spend, from the usage index
    spend = {"today": 0.0, "yesterday": 0.0, "last_7_days": [], "change_vs_prev_7_pct": None, "top_project_today": None}
    usage = registry.get("usage")
    if usage:
        two_weeks = usage.report(14)
        daily = [{"day": d["day"], "cost": round(sum(v["cost"] for v in d["models"].values()), 4)} for d in two_weeks["days"]]
        last7, prev7 = daily[-7:], daily[:-7]
        total7, totalp = sum(d["cost"] for d in last7), sum(d["cost"] for d in prev7)
        today_report = usage.report(1)
        top = today_report["by_project"][0]["project"] if today_report["by_project"] else None
        spend = {"today": daily[-1]["cost"], "yesterday": daily[-2]["cost"], "last_7_days": last7,
                 "change_vs_prev_7_pct": round((total7 - totalp) / totalp * 100, 1) if totalp else None,
                 "top_project_today": top}
        for model in two_weeks["pricing"]["unpriced_models"]:
            attention.append({"kind": "unpriced_model", "severity": "attention", "title": f"No price for {model}",
                              "detail": "Its usage counts as $0. Add it under [pricing] in eyrie.toml.",
                              "href": "/usage", "since": None})

    # Tasks
    # None when no tasks file is set: the views hide tasks rather than show an empty list.
    tasks = None if settings.paths.tasks is None else {"open_count": 0, "next": []}
    t = registry.get("tasks")
    if tasks is not None and t and t.available().available:
        open_tasks = [x for x in t.snapshot()["tasks"] if not x["done"]]
        tasks = {"open_count": len(open_tasks), "next": open_tasks[:3]}

    # Recent projects you can start a session in
    # (from the usage index, which every enabled tool with sessions feeds), newest first.
    recent: dict[str, dict] = {}
    if usage:
        for t in on.values():
            if not t.sessions:
                continue
            for c in usage.index.recent_sessions(40, tool=t.id):
                p = c["project"]
                if p and (p not in recent or recent[p]["last_used"] < c["last"]):
                    recent[p] = {"path": p, "last_used": c["last"], "tool": t.id}
    recent_projects = sorted((p for p in recent.values() if is_allowed(settings, p["path"])),
                             key=lambda p: p["last_used"], reverse=True)[:6]

    attention.sort(key=lambda a: SEVERITY[a["severity"]])
    state = "problem" if any(a["severity"] == "problem" for a in attention) else "attention" if attention else "ok"
    usage_stats = usage.index.stats() if usage else None
    return {
        "state": state,
        "attention": attention,
        "sessions": sessions,
        "spend": spend,
        "tasks": tasks,
        "recent_projects": recent_projects,
        "health": {**health, "usage_index": usage_stats},
        "generated_at": now.isoformat(),
    }
