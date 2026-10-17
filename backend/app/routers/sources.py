from fastapi import APIRouter, HTTPException, Request

from app.schemas import SOURCE_MODELS, SourceInfo

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.get("", response_model=list[SourceInfo])
def list_sources(request: Request):
    out = []
    for source in request.app.state.registry.values():
        a = source.available()
        out.append({"id": source.id, "title": source.title, "available": a.available, "reason": a.reason})
    return out


def _snapshot(request: Request, source_id: str):
    source = request.app.state.registry.get(source_id)
    if source is None:
        raise HTTPException(404, f"Unknown or disabled source: {source_id}")
    return source.snapshot()


def _typed_route(source_id: str, model) -> None:
    # One route per source so each snapshot has its own schema in OpenAPI (and so its
    # own generated TypeScript type). Declared before the generic route below.
    def get_source(request: Request):
        return _snapshot(request, source_id)

    router.add_api_route(f"/{source_id}", get_source, methods=["GET"], response_model=model,
                         name=f"source_{source_id}", operation_id=f"source_{source_id}")


for _id, _model in SOURCE_MODELS.items():
    _typed_route(_id, _model)


@router.get("/{source_id}", include_in_schema=False)
def get_source(source_id: str, request: Request):
    return _snapshot(request, source_id)
