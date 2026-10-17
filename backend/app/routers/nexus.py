import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.sources.nexus import Conflict, NexusSource, NotFound

router = APIRouter(prefix="/api/v1/nexus", tags=["nexus"])


class FileBody(BaseModel):
    content: str


def _source(request: Request) -> NexusSource:
    source = request.app.state.registry.get("nexus")
    if source is None:
        raise HTTPException(404, "Nexus source is disabled")
    if not source.available().available:
        raise HTTPException(409, source.available().reason)
    return source


def _rel(agent: str, name: str) -> str:
    return f"agent-memory/Nexus/{agent}/{name}"


@router.get("/{agent}/{name}")
def read_file(agent: str, name: str, request: Request):
    source = _source(request)
    try:
        return source.read(agent, name)
    except NotFound:
        raise HTTPException(404, f"No file {_rel(agent, name)}")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.put("/{agent}/{name}")
def write_file(agent: str, name: str, body: FileBody, request: Request, if_match: str = Header()):
    """Create (If-Match: absent) or replace a memory file."""
    source = _source(request)
    started = time.perf_counter()
    try:
        result = source.write(agent, name, body.content, if_match)
    except Conflict:
        try:
            current = source.read(agent, name)
        except NotFound:
            current = None
        return JSONResponse({"detail": "The file changed since you opened it", "current": current}, status_code=409)
    except NotFound:
        raise HTTPException(404, f"No agent folder {agent}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    action = "nexus.create" if if_match == "absent" else "nexus.write"
    request.app.state.audit.record(action, ["write", _rel(agent, name)], {"agent": agent, "name": name}, True, 0,
                                   (time.perf_counter() - started) * 1000, f"{len(body.content.encode())} bytes")
    return result


@router.delete("/{agent}/{name}")
def delete_file(agent: str, name: str, request: Request, if_match: str = Header()):
    """Moves the file to the vault's .trash folder (recoverable)."""
    source = _source(request)
    started = time.perf_counter()
    try:
        dest = source.delete(agent, name, if_match)
    except Conflict:
        return JSONResponse({"detail": "The file changed since you opened it; review it before deleting",
                             "current": source.read(agent, name)}, status_code=409)
    except NotFound:
        raise HTTPException(404, f"No file {_rel(agent, name)}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    trashed = str(dest.relative_to(source.trash.parent))
    request.app.state.audit.record("nexus.delete", ["move", _rel(agent, name), trashed], {"agent": agent, "name": name},
                                   True, 0, (time.perf_counter() - started) * 1000, f"Moved to {trashed}")
    return {"trashed_to": trashed}
