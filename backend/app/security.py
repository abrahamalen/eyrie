"""Eyrie can change local tool config, so it must only obey this machine's own browser.

- Host must be a loopback name: blocks DNS-rebinding pages that resolve to 127.0.0.1.
- Origin (when sent) must be loopback, and Sec-Fetch-Site must not be cross-site: blocks
  other websites driving the API from the user's browser.
- Mutating requests need the per-install token from <data_dir>/token.
"""
import hmac
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOKEN_HEADER = "x-eyrie-token"


def load_or_create_token(data_dir: Path) -> str:
    path = data_dir / "token"
    if path.exists():
        return path.read_text().strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.touch(mode=0o600)
    path.write_text(token)
    return token


def _hostname(value: str) -> str | None:
    if not value:
        return None
    return urlsplit(value if "//" in value else f"//{value}").hostname


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        error = self._check(scope, headers)
        if error:
            status, detail = error
            return await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
        await self.app(scope, receive, send)

    def _check(self, scope: Scope, headers: dict[str, str]) -> tuple[int, str] | None:
        if _hostname(headers.get("host", "")) not in LOOPBACK:
            return 403, "Host not allowed"
        origin = headers.get("origin")
        if origin and _hostname(origin) not in LOOPBACK:
            return 403, "Origin not allowed"
        if headers.get("sec-fetch-site") == "cross-site":
            return 403, "Cross-site request blocked"
        method = scope.get("method", "GET")
        if scope["type"] == "websocket" or method not in SAFE_METHODS:
            if not hmac.compare_digest(headers.get(TOKEN_HEADER, ""), self.token):
                return 401, "Missing or invalid token"
        return None
