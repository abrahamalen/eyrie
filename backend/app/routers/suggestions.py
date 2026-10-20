"""Snooze or dismiss an idle-session suggestion (docs/stop-and-idle.md §7). Eyrie's own
state in <data_dir>/suggestions.json; the tools' files are never touched."""
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.schemas import Snooze, Status
from app.sessions.idle import KEY_RE

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


class SnoozeBody(BaseModel):
    snooze: Literal["1d", "7d", "dismiss"]


def _sessions(request: Request):
    src = request.app.state.registry.get("sessions")
    if src is None:
        raise HTTPException(404, "Sessions source is disabled")
    return src


@router.put("/{key}", response_model=Snooze)
def snooze(key: str, body: SnoozeBody, request: Request):
    if not KEY_RE.match(key):
        raise HTTPException(422, "Not a suggestion key")
    src = _sessions(request)
    snap = src.snapshot()
    found = next((s["idle"] for s in [*snap["sessions"], *snap["external"]] if s.get("idle") and s["idle"]["key"] == key), None)
    if found is None:
        raise HTTPException(404, "No running session with that key")
    started = time.perf_counter()
    entry = src.snoozes.set(key, body.snooze, found["since"])
    request.app.state.audit.record("suggestions.snooze", ["snooze", key, body.snooze], {"key": key, "snooze": body.snooze},
                                   True, 0, (time.perf_counter() - started) * 1000, f"Snoozed {key}: {body.snooze}")
    return entry


@router.delete("/{key}", response_model=Status)
def unsnooze(key: str, request: Request):
    if not KEY_RE.match(key):
        raise HTTPException(422, "Not a suggestion key")
    started = time.perf_counter()
    if not _sessions(request).snoozes.clear(key):
        raise HTTPException(404, "Not snoozed")
    request.app.state.audit.record("suggestions.clear", ["unsnooze", key], {"key": key}, True, 0,
                                   (time.perf_counter() - started) * 1000, f"Suggestions back on for {key}")
    return {"status": "ok"}
