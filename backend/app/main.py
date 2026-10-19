from pathlib import Path

from fastapi import FastAPI

from app import __version__

from app.config import Settings, get_settings
from app.actions.audit import AuditLog
from app.actions.runner import Runner
from app.routers import actions, auth, memory, sessions, sources, tasks, usage
from app.schemas import Meta, Status, Summary
from app.summary import Versions, build_summary
from app.security import LocalOnlyMiddleware, load_or_create_token
from app.sources.base import build_registry
from app.ui import mount_ui


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    token = load_or_create_token(settings.paths.data_dir)

    app = FastAPI(title="Eyrie", version=__version__,
                  description="Local control plane for Claude Code, Codex, MCP, and agent memory")
    app.state.settings = settings
    app.state.registry = build_registry(settings)
    app.state.token = token
    app.state.runner = Runner(settings)
    app.state.audit = AuditLog(settings.paths.data_dir / "audit.jsonl")
    app.add_middleware(LocalOnlyMiddleware, token=token)

    app.include_router(auth.router)
    app.include_router(sources.router)
    app.include_router(tasks.router)
    app.include_router(usage.router)
    app.include_router(actions.router)
    app.include_router(sessions.router)
    app.include_router(memory.router)

    @app.get("/api/v1/health", response_model=Status)
    def health():
        return {"status": "ok"}

    versions = Versions(app.state.runner)

    @app.get("/api/v1/summary", response_model=Summary)
    def summary():
        """What needs you and what's going on: the home page and the widget both read this."""
        return build_summary(settings, app.state.registry, versions)

    @app.get("/api/v1/meta", response_model=Meta)
    def meta():
        return {"home": str(Path.home()), "version": __version__}

    # Last: a catch-all for the UI, so it never shadows an API route.
    mount_ui(app, settings.server.ui_dir)

    return app

