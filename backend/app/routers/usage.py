from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


@router.get("")
def usage(request: Request, days: int = Query(30, ge=1, le=365)):
    source = request.app.state.registry.get("usage")
    if source is None:
        raise HTTPException(404, "Usage source is disabled")
    return source.report(days)
