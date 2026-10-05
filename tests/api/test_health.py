import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.health import HealthResponse


def test_health_contract() -> None:
    application = create_app(Settings(_env_file=None, app_name="shelfcash-backend"))
    with TestClient(application) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "shelfcash-backend"}
    assert response.headers["content-type"] == "application/json"
    assert HealthResponse.model_validate(response.json()).status == "ok"

    specification = application.openapi()
    operation = specification["paths"]["/health"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
    assert specification["components"]["schemas"]["HealthResponse"] == (
        HealthResponse.model_json_schema()
    )
    json.dumps(specification)


def test_only_intended_routes_exist() -> None:
    application = create_app(Settings(_env_file=None))
    assert set(application.openapi()["paths"]) == {"/health"}
    assert {(route.path, frozenset(route.methods)) for route in application.routes} == {
        ("/health", frozenset({"GET"})),
        ("/openapi.json", frozenset({"GET", "HEAD"})),
    }
    with TestClient(application) as client:
        assert client.get("/openapi.json").status_code == 200


