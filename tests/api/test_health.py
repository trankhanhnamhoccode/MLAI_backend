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
    public = {"/api/v1/auth/login": "POST", "/api/v1/auth/me": "GET",
              "/api/v1/auth/logout": "POST", "/api/v1/auth/credentials/complete": "POST",
              "/api/v1/stores": "GET", "/api/v1/stores/{store_id}": "GET"}
    public.update({"/api/v1/auth/register": "POST", "/api/v1/auth/email-verifications/request": "POST",
                   "/api/v1/auth/email-verifications/complete": "POST", "/api/v1/auth/password-reset/request": "POST"})
    public.update({"/api/v1/stores/{store_id}/memberships":"GET",
        "/api/v1/stores/{store_id}/memberships/{membership_id}/permissions":"PUT",
        "/api/v1/stores/{store_id}/permission-events":"GET",
        "/api/v1/stores/{store_id}/staff-invitations":"GET,POST",
        "/api/v1/stores/{store_id}/staff-invitations/{invitation_id}/actions":"POST",
        "/api/v1/staff-invitations/{invitation_id}":"GET",
        "/api/v1/staff-invitations/{invitation_id}/accept":"POST",
        "/api/v1/staff-invitations/{invitation_id}/decline":"POST"})
    public.update({'/api/v1/stores/{store_id}/products': 'GET', '/api/v1/stores/{store_id}/products/{product_id}': 'GET', '/api/v1/stores/{store_id}/inventory': 'GET', '/api/v1/stores/{store_id}/inventory/{ingredient_id}': 'GET', '/api/v1/stores/{store_id}/inventory/{ingredient_id}/lots': 'GET', '/api/v1/stores/{store_id}/inventory/{ingredient_id}/movements': 'GET'})
    public.update({'/api/v1/stores/{store_id}/imports': 'POST', '/api/v1/imports/{import_id}/files': 'POST', '/api/v1/imports/{import_id}/analyze': 'POST', '/api/v1/imports/{import_id}': 'GET', '/api/v1/imports/{import_id}/mapping-summary': 'GET', '/api/v1/imports/{import_id}/mappings': 'GET', '/api/v1/imports/{import_id}/sheets/{sheet_id}/field-options': 'GET', '/api/v1/imports/{import_id}/mappings/{mapping_id}': 'PATCH', '/api/v1/stores/{store_id}/mapping-profiles/{profile_id}/decisions': 'POST', '/api/v1/imports/{import_id}/process': 'POST', '/api/v1/jobs/{job_id}': 'GET'})
    public["/api/v1/imports/{import_id}/completion"] = "GET"
    public.update({"/api/v1/stores/{store_id}/inventory/receipts":"POST",
        "/api/v1/stores/{store_id}/inventory/{ingredient_id}/threshold":"PUT",
        "/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule":"GET",
        "/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule/changes":"POST",
        "/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule/changes/{change_id}":"GET"})
    public.update({'/api/v1/stores/{store_id}/planning-requirements': 'POST', '/api/v1/stores/{store_id}/planning-requirements/{saved_requirement_id}': 'GET,PUT', '/api/v1/stores/{store_id}/planning-budget': 'PUT', '/api/v1/stores/{store_id}/readiness': 'GET', '/api/v1/stores/{store_id}/planning-context': 'GET'})
    public.update({'/api/v1/stores/{store_id}/procurement-plans':'POST','/api/v1/procurement-plans/{plan_id}':'GET'})
    public.update({'/api/v1/procurement-plans/{plan_id}/ingredients':'GET',
        '/api/v1/procurement-plans/{plan_id}/ingredients/{ingredient_id}':'GET',
        '/api/v1/procurement-plans/{plan_id}/explanation':'GET',
        '/api/v1/procurement-plans/{plan_id}/exports':'POST',
        '/api/v1/procurement-plans/{plan_id}/exports/{export_id}':'GET',
        '/api/v1/stores/{store_id}/imports/calendar':'GET'})
    public['/api/v1/stores/{store_id}/imports']='GET,POST'
    public['/api/v1/stores/{store_id}/procurement-plans']='GET,POST'
    public.update({
        '/api/v1/notifications':'GET', '/api/v1/notifications/unread-count':'GET', '/api/v1/notifications/{notification_id}':'PATCH',
        '/api/v1/stores/{store_id}/permission-requests':'GET,POST',
        '/api/v1/stores/{store_id}/permission-requests/{request_id}':'GET',
        '/api/v1/stores/{store_id}/permission-requests/{request_id}/actions':'POST',
        '/api/v1/imports/{import_id}/mapping-submissions':'POST',
        '/api/v1/stores/{store_id}/mapping-submissions':'GET',
        '/api/v1/stores/{store_id}/mapping-submissions/{submission_id}':'GET'})
    public.update({'/api/v1/stores/{store_id}/today':'GET',
                   '/api/v1/stores/{store_id}/suppliers':'GET',
                   '/api/v1/stores':'GET,POST',
                   '/api/v1/procurement-plans/{plan_id}/exports':'GET,POST'})
    assert set(application.openapi()["paths"]) == {"/health", *public}
    assert {(route.path, frozenset(route.methods)) for route in application.routes} == {
        ("/health", frozenset({"GET"})),
        ("/openapi.json", frozenset({"GET", "HEAD"})),
    } | {(path, frozenset({method})) for path, methods in public.items() for method in methods.split(",")}
    with TestClient(application) as client:
        assert client.get("/openapi.json").status_code == 200


