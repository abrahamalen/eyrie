from app.schemas import SOURCE_MODELS
from app.sources.base import build_registry


def test_every_source_has_a_typed_route(app, settings):
    spec = app.openapi()
    for sid in build_registry(settings):
        assert sid in SOURCE_MODELS, f"source {sid} has no response model in app/schemas.py"
        op = spec["paths"][f"/api/v1/sources/{sid}"]["get"]
        ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/" + SOURCE_MODELS[sid].__name__)


def test_every_json_route_declares_a_response_model(app):
    untyped = []
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            schema = op["responses"].get("200", {}).get("content", {}).get("application/json", {}).get("schema")
            if not schema:
                untyped.append(f"{method.upper()} {path}")
    assert untyped == []
