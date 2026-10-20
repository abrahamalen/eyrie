"""Idle sessions and what keeping them costs (docs/stop-and-idle.md §3, §7).

Eyrie only ever suggests: nothing here stops anything. Snoozes and dismissals live in
<data_dir>/suggestions.json, never in the tools' own files.
"""
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.fsutil import atomic_write
from app.sessions import procs
from app.tools import TOOLS

KEY_RE = re.compile(r"^(eyrie:eyrie-[a-z0-9]{4,16}|(claude|codex|gemini):[A-Za-z0-9][A-Za-z0-9._-]{0,63}|pid:\d{1,8}:\d{1,12})$")
SNOOZE = {"1d": timedelta(days=1), "7d": timedelta(days=7)}
KEEP = timedelta(days=30)
MAX_ITEMS = 500


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def session_key(s: dict, managed: bool) -> str:
    """Eyrie sessions by name; external ones by conversation when it's known exactly
    (survives a restart of the same conversation), else by pid + start time."""
    if managed:
        return f"eyrie:{s['name']}"
    if s.get("conversation_id") and s.get("name_exact") and KEY_RE.match(f"{s['tool']}:{s['conversation_id']}"):
        return f"{s['tool']}:{s['conversation_id']}"
    started = _parse(s.get("process_started")) or _parse(s.get("started"))
    return f"pid:{s['pid']}:{int(started.timestamp()) if started else 0}"


class Snoozes:
    """{"version": 1, "items": {key: {"until": iso | null, "activity": iso | null, "at": iso}}}.
    until set: snoozed until then. until null: dismissed until the session is used again."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict):
            return {}
        return {k: v for k, v in items.items() if isinstance(k, str) and KEY_RE.match(k) and isinstance(v, dict)}

    def _save(self, items: dict[str, dict], now: datetime) -> None:
        def keep(v: dict) -> bool:
            until, at = _parse(v.get("until")), _parse(v.get("at"))
            expired = until is not None and until < now
            return not (expired and at is not None and now - at > KEEP)
        items = {k: v for k, v in items.items() if keep(v)}
        if len(items) > MAX_ITEMS:
            items = dict(sorted(items.items(), key=lambda kv: kv[1].get("at") or "")[-MAX_ITEMS:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps({"version": 1, "items": items}, indent=1) + "\n")

    def set(self, key: str, how: str, activity: str | None, now: datetime | None = None) -> dict:
        if not KEY_RE.match(key):
            raise ValueError("Not a suggestion key")
        if how not in (*SNOOZE, "dismiss"):
            raise ValueError("snooze is 1d, 7d or dismiss")
        now = now or datetime.now(timezone.utc)
        entry = {"until": _iso(now + SNOOZE[how]) if how in SNOOZE else None,
                 "activity": activity if _parse(activity) else None, "at": _iso(now)}
        with self._lock:
            items = self.load()
            items[key] = entry
            self._save(items, now)
        return {"key": key, **entry}

    def clear(self, key: str) -> bool:
        with self._lock:
            items = self.load()
            if items.pop(key, None) is None:
                return False
            self._save(items, datetime.now(timezone.utc))
        return True

    @staticmethod
    def state(entry: dict | None, activity: datetime | None, now: datetime) -> tuple[str | None, bool]:
        """(snoozed until, dismissed) for one session right now."""
        if not entry:
            return None, False
        until = _parse(entry.get("until"))
        if until is not None:
            return (_iso(until), False) if until > now else (None, False)
        then = _parse(entry.get("activity"))
        # Dismissed until it's used again: newer activity brings the suggestion back.
        return None, not (activity and then and activity > then)


def context_hint(tool: str, conversation_id: str | None, exact: bool, turns: dict, now: datetime,
                 settings: Settings, idle: bool) -> dict:
    """Context size of the last turn and whether its prompt cache has expired (§3.3)."""
    out = {"context_tokens": None, "cache_expired": None, "compact_command": None}
    caps = TOOLS[tool].sessions if tool in TOOLS else None
    turn = turns.get((tool, conversation_id)) if conversation_id and exact else None
    if turn is None or caps is None:
        return out
    out["context_tokens"] = turn["context_tokens"]
    last = _parse(turn["ts"])
    if caps.cache_minutes is None or last is None:
        return out
    ttl = caps.cache_minutes[1 if turn["wrote_1h"] else 0]
    out["cache_expired"] = now - last > timedelta(minutes=ttl)
    if idle and out["cache_expired"] and turn["context_tokens"] >= settings.sessions.large_context_tokens:
        out["compact_command"] = caps.compact_command
    return out


def annotate(settings: Settings, managed: list[dict], external: list[dict], table: dict[int, procs.Proc],
             index, snoozes: Snoozes, now: datetime | None = None) -> None:
    """Adds `resources` and `idle` to each session, in place."""
    now = now or datetime.now(timezone.utc)
    rows = [(s, True) for s in managed] + [(s, False) for s in external]
    wanted = [(s["tool"], s["conversation_id"]) for s, m in rows
              if s.get("tool") and s.get("conversation_id") and (m or s.get("name_exact"))]
    try:
        turns = index.last_turns(wanted) if index is not None else {}
    except Exception:  # noqa: BLE001  the usage DB is optional here: no hint rather than no sessions
        turns = {}
    saved = snoozes.load()
    threshold = settings.sessions.idle_hours * 60
    for s, is_managed in rows:
        alive = s.get("alive", True)
        s["resources"] = procs.resources(table, s.get("pid")) if alive else {"rss_bytes": None, "child_processes": None}
        activity = _parse(s.get("activity_at"))
        if not alive or activity is None:
            s["idle"] = None
            continue
        minutes = max(int((now - activity).total_seconds() // 60), 0)
        key = session_key(s, is_managed)
        snoozed_until, dismissed = Snoozes.state(saved.get(key), activity, now)
        attached = (s.get("attached", 0) > 0) if is_managed else None
        is_idle = minutes >= threshold
        exact_conv = is_managed or bool(s.get("name_exact"))
        s["idle"] = {
            "minutes": minutes, "since": _iso(activity), "exact": bool(s.get("activity_exact", True)),
            "idle": is_idle,
            "suggested": is_idle and not snoozed_until and not dismissed
                         and not (settings.sessions.idle_requires_detached and attached),
            "key": key, "snoozed_until": snoozed_until, "dismissed": dismissed, "attached": attached,
            **context_hint(s["tool"], s.get("conversation_id"), exact_conv, turns, now, settings, is_idle),
        }
