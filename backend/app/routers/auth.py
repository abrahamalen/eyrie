from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/token")
def get_token(request: Request):
    # Reachable only from this machine's own pages: LocalOnlyMiddleware rejects other
    # hosts, origins and cross-site fetches before this runs.
    return {"token": request.app.state.token}
