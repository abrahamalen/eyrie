from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import UsageReport

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


@router.get("", response_model=UsageReport)
def usage(request: Request, days: int = Query(30, ge=1, le=365)):
    source = request.app.state.registry.get("usage")
    if source is None:
        raise HTTPException(404, "Usage source is disabled")
    return source.report(days)
