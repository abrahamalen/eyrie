from fastapi import APIRouter, HTTPException, Query, Request

from app.sessions.tmux import NAME_RE

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("/conversations")
def conversations(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Recent Claude Code conversations (from the usage index), to resume into a session."""
    usage = request.app.state.registry.get("usage")
    if usage is None:
        return []
    usage.index.scan()
    return usage.index.recent_sessions(limit)


@router.get("/{name}/screen")
def screen(name: str, request: Request, lines: int = Query(80, ge=10, le=2000)):
    """The session's visible screen plus scrollback, as plain text (read-only)."""
    if not NAME_RE.match(name):
        raise HTTPException(404, "Not an Eyrie session")
    sessions = request.app.state.registry.get("sessions")
    text = sessions.tmux.capture(name, lines) if sessions else None
    if text is None:
        raise HTTPException(404, f"No session named {name}")
    return {"name": name, "text": text}
