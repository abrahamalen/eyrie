"""Helpers shared by the adapters' MCP readers."""
from app.masking import mask_args, mask_url


def entry(name: str, cfg: dict, client: str, scope: str, project: str | None = None) -> dict:
    kind = cfg.get("type") or ("http" if cfg.get("url") else "stdio")
    target = (mask_url(cfg["url"]) if cfg.get("url")
              else " ".join(mask_args([cfg.get("command", ""), *cfg.get("args", [])])).strip())
    return {"name": name, "client": client, "scope": scope, "type": kind, "target": target, "project": project}
