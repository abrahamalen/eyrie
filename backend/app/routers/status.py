from fastapi import APIRouter

from app.services import claude, codex, mcp, nexus

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/claude")
def claude_usage():
    return claude.get_usage()


@router.get("/codex")
def codex_usage():
    return codex.get_usage()


@router.get("/mcp")
def mcp_status():
    claude_data = claude.get_usage()
    return {
        "configured": claude_data["configured_mcp"],
        "last_known_failures": mcp.get_last_known_status(),
    }


@router.get("/nexus")
def nexus_agents():
    return {"agents": nexus.get_agents()}
