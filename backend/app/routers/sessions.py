import time

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from starlette.concurrency import run_in_threadpool

from app.actions.runner import CliNotFound
from app.security import WS_PROTOCOL
from app.sessions.terminal import TooManyTerminals, bridge
from app.sessions.tmux import NAME_RE, base_args

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


@router.websocket("/{name}/term")
async def terminal(ws: WebSocket, name: str, readonly: bool = False):
    """Interactive terminal attached to an Eyrie session (auth: LocalOnlyMiddleware)."""
    state = ws.app.state
    sessions = state.registry.get("sessions")
    if sessions is None or not NAME_RE.match(name) or not await run_in_threadpool(sessions.tmux.exists, name):
        return await ws.close(code=4404, reason=f"No session named {name}")
    try:
        tmux_bin = state.runner.binary("tmux")
    except CliNotFound as e:
        return await ws.close(code=4503, reason=str(e))
    offered = ws.scope.get("subprotocols") or []
    await ws.accept(subprotocol=WS_PROTOCOL if WS_PROTOCOL in offered else None)
    started = time.perf_counter()
    try:
        reason = await bridge(ws, state.settings, tmux_bin, name, readonly)
    except TooManyTerminals:
        await ws.close(code=4429, reason="Too many open terminals")
        return
    shown = ["tmux", *base_args(state.settings), "attach-session", "-t", name, *(["-r"] if readonly else [])]
    state.audit.record("sessions.attach", shown, {"name": name, "readonly": readonly}, True, 0,
                       (time.perf_counter() - started) * 1000, f"Browser terminal closed: {reason}")
    try:
        await ws.close()
    except RuntimeError:
        pass  # already closed by the browser
