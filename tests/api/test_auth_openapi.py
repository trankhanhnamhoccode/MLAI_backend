from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def test_s41_openapi_exact_methods_envelopes_headers_and_cookie():
    app = create_app(Settings(_env_file=None, auth_allowed_origins=["https://fe.example.test"]))
    schema = app.openapi()
    expected = {
        "/api/v1/auth/login": ("post", "A01", "200"),
        "/api/v1/auth/me": ("get", "A03", "200"),
        "/api/v1/auth/logout": ("post", "A04", "204"),
        "/api/v1/auth/credentials/complete": ("post", "N7", "200"),
        "/api/v1/stores": ("get", "T01", "200"),
        "/api/v1/stores/{store_id}": ("get", "T02", "200"),
    }
    b1_paths = {"/api/v1/auth/register", "/api/v1/auth/email-verifications/request", "/api/v1/auth/email-verifications/complete", "/api/v1/auth/password-reset/request"}
    staff_paths = {"/api/v1/stores/{store_id}/memberships", "/api/v1/stores/{store_id}/memberships/{membership_id}/permissions",
        "/api/v1/stores/{store_id}/permission-events", "/api/v1/stores/{store_id}/staff-invitations",
        "/api/v1/stores/{store_id}/staff-invitations/{invitation_id}/actions", "/api/v1/staff-invitations/{invitation_id}",
        "/api/v1/staff-invitations/{invitation_id}/accept", "/api/v1/staff-invitations/{invitation_id}/decline"}
    import_paths = {'/api/v1/stores/{store_id}/imports', '/api/v1/imports/{import_id}/files', '/api/v1/imports/{import_id}/mappings/{mapping_id}', '/api/v1/stores/{store_id}/mapping-profiles/{profile_id}/decisions', '/api/v1/imports/{import_id}/sheets/{sheet_id}/field-options', '/api/v1/jobs/{job_id}', '/api/v1/imports/{import_id}/mapping-summary', '/api/v1/imports/{import_id}/mappings', '/api/v1/imports/{import_id}', '/api/v1/imports/{import_id}/analyze', '/api/v1/imports/{import_id}/process'}
    import_paths |= {'/api/v1/stores/{store_id}/procurement-plans','/api/v1/procurement-plans/{plan_id}'}
    import_paths |= {'/api/v1/procurement-plans/{plan_id}/ingredients',
        '/api/v1/procurement-plans/{plan_id}/ingredients/{ingredient_id}',
        '/api/v1/procurement-plans/{plan_id}/explanation',
        '/api/v1/procurement-plans/{plan_id}/exports',
        '/api/v1/procurement-plans/{plan_id}/exports/{export_id}',
        '/api/v1/stores/{store_id}/imports/calendar'}
    assert set(schema["paths"]) == {"/health", '/api/v1/stores/{store_id}/planning-requirements', '/api/v1/stores/{store_id}/planning-requirements/{saved_requirement_id}', '/api/v1/stores/{store_id}/planning-budget', '/api/v1/stores/{store_id}/readiness', '/api/v1/stores/{store_id}/planning-context', *expected, *staff_paths, *import_paths,
        '/api/v1/imports/{import_id}/completion', '/api/v1/stores/{store_id}/inventory/receipts', '/api/v1/stores/{store_id}/inventory/{ingredient_id}/threshold',
        '/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule',
        '/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule/changes',
        '/api/v1/stores/{store_id}/products/{product_id}/recipe-schedule/changes/{change_id}',
        *b1_paths, *['/api/v1/stores/{store_id}/products', '/api/v1/stores/{store_id}/products/{product_id}', '/api/v1/stores/{store_id}/inventory', '/api/v1/stores/{store_id}/inventory/{ingredient_id}', '/api/v1/stores/{store_id}/inventory/{ingredient_id}/lots', '/api/v1/stores/{store_id}/inventory/{ingredient_id}/movements']}
    for path, (method, identity, status) in expected.items():
        assert set(schema["paths"][path]) == {method}
        operation = schema["paths"][path][method]
        assert operation["operationId"] == identity and status in operation["responses"]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}
        if identity == "A04":
            assert "content" not in operation["responses"]["204"]
        else:
            assert "Envelope" in operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert schema["components"]["securitySchemes"]["APIKeyCookie"] == {"type": "apiKey", "in": "cookie", "name": "__Host-shelfcash_session"}
    assert "security" not in schema["paths"]["/api/v1/auth/login"]["post"]
    assert "security" not in schema["paths"]["/api/v1/auth/credentials/complete"]["post"]
    assert {} in schema["paths"]["/api/v1/auth/logout"]["post"]["security"]
    assert schema["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"APIKeyCookie": []}]
    assert set(schema["components"]["schemas"]["ErrorEnvelope"]["required"]) == {"data", "meta", "error"}
    assert schema["components"]["schemas"]["LoginRequest"]["additionalProperties"] is False
    assert set(schema["components"]["schemas"]["LoginRequest"]["properties"]) == {"email", "password", "remember_me"}
    with TestClient(app, base_url="https://backend.example.test") as client:
        # Origin fence before any DB operation.
        response = client.post("/api/v1/auth/login", json=dict(email="a@b.test", password="Synthetic-password"))
        assert response.status_code == 403
        assert set(response.json()) == {"data", "meta", "error"}
        assert response.headers["referrer-policy"] == "no-referrer"
