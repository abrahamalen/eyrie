from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("")
def list_sources(request: Request):
    out = []
    for source in request.app.state.registry.values():
        a = source.available()
        out.append({"id": source.id, "title": source.title, "available": a.available, "reason": a.reason})
    return out


@router.get("/{source_id}")
def get_source(source_id: str, request: Request):
    source = request.app.state.registry.get(source_id)
    if source is None:
        raise HTTPException(404, f"Unknown or disabled source: {source_id}")
    return source.snapshot()
