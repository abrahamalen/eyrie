from fastapi import FastAPI

from app.config import Settings, get_settings
from app.actions.audit import AuditLog
from app.actions.runner import Runner
from app.routers import actions, auth, sessions, sources, tasks, usage
from app.security import LocalOnlyMiddleware, load_or_create_token
from app.sources.base import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    token = load_or_create_token(settings.paths.data_dir)

    app = FastAPI(title="Eyrie", description="Local control plane for Claude Code, Codex, MCP, and Nexus")
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

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    return app

