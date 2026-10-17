from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError

from app.actions.registry import ACTIONS, Context, redact
from app.actions.runner import CliNotFound
from app.sessions.dirs import is_allowed

router = APIRouter(prefix="/api/v1", tags=["actions"])


class ActionRequest(BaseModel):
    params: dict[str, Any] = {}
    dry_run: bool = False
    confirm: bool = False


def _errors(e: ValidationError) -> str:
    return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())


@router.post("/actions/{action_id}")
def run_action(action_id: str, body: ActionRequest, request: Request):
    action = ACTIONS.get(action_id)
    if action is None:
        raise HTTPException(404, f"Unknown action: {action_id}")
    try:
        params = action.params.model_validate(body.params)
    except ValidationError as e:
        raise HTTPException(422, _errors(e))
    state = request.app.state
    try:
        planned = action.plan(params, Context(state.settings, state.runner))
    except CliNotFound as e:
        raise HTTPException(503, str(e))
    shown = redact(planned.tool, planned.args)
    if body.dry_run:
        return {"action": action_id, "argv": shown, "destructive": action.destructive, "dry_run": True}
    if action.destructive and not body.confirm:
        raise HTTPException(428, {"detail": "Destructive action; review the command and confirm", "argv": shown})

    blocked = _precheck(state, action_id, params)
    if blocked:
        raise HTTPException(409, blocked)
    try:
        result = state.runner.run(planned.tool, planned.args, cwd=planned.cwd)
    except CliNotFound as e:
        raise HTTPException(503, str(e))

    message = "\n".join(x for x in (result.stdout.strip(), result.stderr.strip()) if x)
    ok = result.ok
    if ok:
        problem = _verify(state, action_id, params)
        if problem:
            ok, message = False, f"{problem}\n{message}".strip()
    source = state.registry.get(action.invalidates or "")
    if hasattr(source, "invalidate"):
        source.invalidate()
    entry = state.audit.record(action_id, shown, _safe_params(params), ok, result.exit_code, result.duration_ms, message)
    return {"action": action_id, "argv": shown, "ok": ok, "exit_code": result.exit_code,
            "message": message, "duration_ms": entry["duration_ms"]}


def _installed_plugin(state, plugin_id: str) -> dict | None:
    source = state.registry.get("plugins")
    if source is None:
        return None
    return next((p for p in source.snapshot()["plugins"] if p["id"] == plugin_id), None)


def _precheck(state, action_id: str, params) -> str | None:
    # `claude plugin enable` reports success for a plugin that isn't installed, and
    # records it as enabled anyway, so check first.
    if action_id.startswith("plugins.") and _installed_plugin(state, params.plugin) is None:
        return f"{params.plugin} isn't installed"
    if action_id == "sessions.start":
        if not is_allowed(state.settings, params.cwd):
            return (f"{params.cwd} isn't an allowed directory. Use a project Claude Code or Codex already knows, "
                    "or add a parent folder to sessions.roots in eyrie.toml.")
        if state.registry["sessions"].tmux.exists(params.name):
            return f"A session named {params.name} already exists"
    if action_id == "sessions.stop" and not state.registry["sessions"].tmux.exists(params.name):
        return f"No session named {params.name}"
    return None


def _verify(state, action_id: str, params) -> str | None:
    """Check the change really happened: some CLI paths exit 0 without doing anything."""
    if action_id.startswith("plugins."):
        state.registry["plugins"].invalidate()
        p = _installed_plugin(state, params.plugin)
        want = action_id == "plugins.enable"
        if p is not None and p["enabled"] != want:
            return f"The CLI reported success but {params.plugin} is still {'disabled' if want else 'enabled'}."
        return None
    if action_id.startswith("sessions."):
        alive = state.registry["sessions"].tmux.exists(params.name)
        if action_id == "sessions.start" and not alive:
            return "tmux reported success but the session isn't running."
        if action_id == "sessions.stop" and alive:
            return "The session is still running."
        return None
    mcp = state.registry.get("mcp")
    if mcp is None or not action_id.startswith("mcp."):
        return None
    found = mcp.find(params.client, params.name, params.scope, params.project_dir)
    if action_id == "mcp.add" and not found:
        return "The CLI reported success but the server isn't in its config."
    if action_id == "mcp.remove" and found:
        return "The server is still configured after removal."
    return None


def _safe_params(params) -> dict:
    d = params.model_dump()
    for key in ("env", "headers"):
        if d.get(key):
            d[key] = {k: "***" for k in d[key]}
    return d


@router.get("/audit")
def audit(request: Request, limit: int = Query(100, ge=1, le=1000)):
    return request.app.state.audit.recent(limit)
