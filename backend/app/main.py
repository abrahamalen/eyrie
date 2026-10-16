from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import status, tasks

app = FastAPI(title="Eyrie", description="Live view of Claude Code, Codex, MCP, and Nexus activity")

# Dev-only: Vite's dev server runs on a different port than the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
