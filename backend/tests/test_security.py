import stat

import pytest


def test_token_file_is_private(app, settings):
    path = settings.paths.data_dir / "token"
    assert path.read_text() == app.state.token
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_token_survives_restart(settings):
    from app.main import create_app
    assert create_app(settings).state.token == create_app(settings).state.token


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
    assert authed.post("/api/v1/tasks", json={"text": "x"}).status_code == 200
