import pytest
from fastapi.testclient import TestClient

from app.config import Server
from app.main import create_app


@pytest.fixture
def ui(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside dist")
    app = create_app(settings.model_copy(update={"server": Server(ui_dir=dist)}))
    return TestClient(app, base_url="http://localhost")


def test_index_and_spa_routes(ui):
    for path in ("/", "/sessions", "/usage/anything"):
        r = ui.get(path)
        assert r.status_code == 200 and "id=root" in r.text and r.headers["cache-control"] == "no-cache"


def test_head_supported(ui):
    assert ui.head("/sessions").status_code == 200


def test_assets_cached_immutable(ui):
    r = ui.get("/assets/index-abc123.js")
    assert r.text == "console.log(1)" and "immutable" in r.headers["cache-control"]
    assert ui.get("/favicon.svg").headers["cache-control"] == "no-cache"


def test_api_routes_not_shadowed(ui):
    assert ui.get("/api/v1/health").json() == {"status": "ok"}
    auth = {"X-Eyrie-Token": ui.app.state.token}  # writes are authenticated before routing
    for method in ("get", "put", "post", "delete"):
        r = getattr(ui, method)("/api/v1/nope", headers=auth)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_no_escape_from_dist(ui):
    r = ui.get("/..%2Fsecret.txt")
    assert "outside dist" not in r.text


def test_not_built_message(settings, tmp_path):
    app = create_app(settings.model_copy(update={"server": Server(ui_dir=tmp_path / "missing")}))
    r = TestClient(app, base_url="http://localhost").get("/")
    assert r.status_code == 503 and "make build" in r.text


def test_ui_still_behind_host_check(ui):
    assert ui.get("/", headers={"Host": "evil.example"}).status_code == 403


def test_security_headers_on_every_response(ui):
    for path in ("/", "/api/v1/health", "/assets/index-abc123.js"):
        h = ui.get(path).headers
        assert h["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"
