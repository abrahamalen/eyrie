import stat

import pytest


def test_token_file_is_private(app, settings):
    path = settings.paths.data_dir / "token"
    assert path.read_text() == app.state.token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_token_survives_restart(settings):
    from app.main import create_app
    assert create_app(settings).state.token == create_app(settings).state.token


@pytest.mark.parametrize("content", ["", "  \n"])
def test_empty_token_file_is_replaced(settings, content):
    from fastapi.testclient import TestClient

    from app.main import create_app
    path = settings.paths.data_dir / "token"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    path.chmod(0o644)
    client = TestClient(create_app(settings), base_url="http://localhost")
    assert client.post("/api/v1/tasks", json={"text": "x"}).status_code == 401
    assert client.post("/api/v1/tasks", json={"text": "x"}, headers={"X-Eyrie-Token": ""}).status_code == 401
    token = path.read_text()
    assert token.strip() and token == client.app.state.token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:5173", "[::1]:8000"])
def test_loopback_hosts_allowed(client, host):
    assert client.get("/api/v1/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "eyrie.local", "192.168.1.5:8000"])
def test_rebinding_hosts_rejected(client, host):
    assert client.get("/api/v1/health", headers={"Host": host}).status_code == 403


def test_foreign_origin_rejected(client):
    r = client.get("/api/v1/auth/token", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_cross_site_fetch_rejected(client):
    r = client.get("/api/v1/auth/token", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_same_origin_page_gets_token(client, app):
    r = client.get("/api/v1/auth/token", headers={"Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-origin"})
    assert r.json() == {"token": app.state.token}


def test_writes_need_token(client):
    assert client.post("/api/v1/tasks", json={"text": "x"}).status_code == 401
    assert client.post("/api/v1/tasks", json={"text": "x"}, headers={"X-Eyrie-Token": "wrong"}).status_code == 401


def test_writes_with_token(authed):
    assert authed.post("/api/v1/tasks", json={"text": "x"}, headers={"If-Match": "absent"}).status_code == 200


def _ws_rejected(client, url, **kw):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url, **kw):
            pass
    return e.value.code


def test_websocket_wrong_host_rejected(client, app):
    # The test client sends Host: testserver for relative WebSocket URLs.
    assert _ws_rejected(client, "/api/v1/sessions/eyrie-abcd/term",
                        subprotocols=["eyrie", f"eyrie.token.{app.state.token}"]) == 4403


def test_websocket_needs_token(client, app):
    assert _ws_rejected(client, "ws://localhost/api/v1/sessions/eyrie-abcd/term") == 4401
    assert _ws_rejected(client, "ws://localhost/api/v1/sessions/eyrie-abcd/term", subprotocols=["eyrie", "eyrie.token.wrong"]) == 4401


def test_websocket_foreign_origin_rejected_even_with_token(client, app):
    code = _ws_rejected(client, "ws://localhost/api/v1/sessions/eyrie-abcd/term",
                        subprotocols=["eyrie", f"eyrie.token.{app.state.token}"], headers={"Origin": "https://evil.example"})
    assert code == 4403


def test_websocket_token_via_subprotocol_reaches_route(client, app, monkeypatch):
    from app.actions import runner
    from app.actions.runner import RunResult
    monkeypatch.setattr(runner.Runner, "run", lambda self, tool, args, cwd=None: RunResult(1, "", "no server", 1))
    # Auth passes; the route then closes because the session doesn't exist.
    code = _ws_rejected(client, "ws://localhost/api/v1/sessions/eyrie-abcd/term", subprotocols=["eyrie", f"eyrie.token.{app.state.token}"])
    assert code == 4404
