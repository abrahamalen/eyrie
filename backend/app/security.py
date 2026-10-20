"""Eyrie can change local tool config, so it must only obey this machine's own browser.

- Host must be a loopback name: blocks DNS-rebinding pages that resolve to 127.0.0.1.
- Origin (when sent) must be loopback, and Sec-Fetch-Site must not be cross-site: blocks
  other websites driving the API from the user's browser.
- Mutating requests and every WebSocket need the per-install token from <data_dir>/token.
  Browsers can't set headers on a WebSocket, so there it may come as a subprotocol
  "eyrie.token.<token>" (the server then accepts the plain "eyrie" subprotocol).
"""
import hmac
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.fsutil import atomic_write

LOOPBACK = {"localhost", "127.0.0.1", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOKEN_HEADER = "x-eyrie-token"  # noqa: S105 (a header name)
WS_TOKEN_PREFIX = "eyrie.token."  # noqa: S105 (a subprotocol prefix)
WS_PROTOCOL = "eyrie"


def load_or_create_token(data_dir: Path) -> str:
    path = data_dir / "token"
    token = path.read_text().strip() if path.exists() else ""
    # An empty token would match an empty header, turning auth off, so replace it.
    if token:
        return token
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    atomic_write(path, token, mode=0o600)
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
            if scope["type"] == "websocket":
                # Closing before accept makes the server answer the handshake with 403.
                await receive()
                return await send({"type": "websocket.close", "code": 4000 + status, "reason": detail})
            return await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
        if scope["type"] == "http":
            return await self.app(scope, receive, _with_headers(send))
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
            supplied = headers.get(TOKEN_HEADER, "")
            if scope["type"] == "websocket" and not supplied:
                for proto in (p.strip() for p in headers.get("sec-websocket-protocol", "").split(",")):
                    if proto.startswith(WS_TOKEN_PREFIX):
                        supplied = proto[len(WS_TOKEN_PREFIX):]
            if not hmac.compare_digest(supplied, self.token):
                return 401, "Missing or invalid token"
        return None


# Eyrie's pages have buttons that stop sessions and change config, so no other site may
# frame them (clickjacking), and responses shouldn't leak where they came from.
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]


def _with_headers(send: Send) -> Send:
    async def wrapped(message):
        if message["type"] == "http.response.start":
            message = {**message, "headers": [*message.get("headers", []), *SECURITY_HEADERS]}
        await send(message)
    return wrapped
