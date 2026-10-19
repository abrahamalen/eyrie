import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app import setup
from app.schemas import SetupBody, SetupState
from app.sources.base import build_registry

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


@router.get("", response_model=SetupState)
def read_setup(request: Request):
    return setup.detect(request.app.state.settings, request.app.state.versions)


@router.put("", response_model=SetupState)
def write_setup(body: SetupBody, request: Request, if_match: str = Header()):
    """Write ~/.eyrie/eyrie.toml (If-Match: absent on first run) and apply it at once."""
    state = request.app.state
    started = time.perf_counter()
    try:
        new = setup.write(state.settings, body, if_match)
    except setup.Conflict:
        return JSONResponse({"detail": "The config file changed since you opened it",
                             "current": setup.detect(state.settings, state.versions)}, status_code=409)
    except ValueError as e:
        raise HTTPException(422, str(e))
    state.settings = new
    state.runner.settings = new
    state.registry = build_registry(new)
    path = str(setup.config_path())
    state.audit.record("setup.write", ["write", path], body.model_dump(), True, 0,
                       (time.perf_counter() - started) * 1000, f"Wrote {path}")
    return setup.detect(new, state.versions)
