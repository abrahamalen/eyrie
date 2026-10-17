"""Serves the built UI (frontend/dist) at /, so an installed Eyrie is one process on one
port. Client-side routes (/sessions, /usage, ...) fall back to index.html; /api stays API.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

NOT_BUILT = """<!doctype html><title>Eyrie</title><body style="font-family:system-ui;padding:2rem">
<h1>Eyrie's UI isn't built</h1><p>Run <code>make build</code> (or use <code>make dev</code> while developing),
then reload.</p></body>"""


def mount_ui(app: FastAPI, ui_dir: Path) -> None:
    root = ui_dir.resolve()

    # Unknown /api paths are a JSON 404 for every method, never the UI (or a 405 from it).
    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(rest: str):
        raise HTTPException(404, "Not found")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def ui(path: str):
        index = root / "index.html"
        if not index.exists():
            return HTMLResponse(NOT_BUILT, status_code=503)
        target = (root / path).resolve() if path else index
        if path and root in target.parents and target.is_file():
            # Vite fingerprints everything under assets/, so it can be cached forever.
            immutable = target.parent == root / "assets"
            return FileResponse(target, headers={"cache-control": "public, max-age=31536000, immutable"
                                                 if immutable else "no-cache"})
        return FileResponse(index, headers={"cache-control": "no-cache"})
