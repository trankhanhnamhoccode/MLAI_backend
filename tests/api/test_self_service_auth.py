"""Public transport checks without PostgreSQL or an email provider."""
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

ORIGIN = "https://fe.example.test"
ROUTES = {
    "/api/v1/auth/register": ("A02", {"email": "holder@example.test", "display_name": "Holder"}),
    "/api/v1/auth/email-verifications/request": ("A06", {"email": "holder@example.test"}),
    "/api/v1/auth/email-verifications/complete": ("A05", {"token": "synthetic", "password": "Synthetic password 123"}),
    "/api/v1/auth/password-reset/request": ("A07", {"email": "holder@example.test"}),
}


@pytest.fixture
def client():
    app = create_app(Settings(_env_file=None, auth_allowed_origins=[ORIGIN],
        database_url="postgresql+psycopg://shelfcash_auth_tester:synthetic@127.0.0.1:1/shelfcash_auth_test"))
    with TestClient(app, base_url="https://backend.example.test") as client:
        yield client


@pytest.mark.parametrize("path", ROUTES)
def test_origin_fence_and_public_schema(client, path):
    identity, body = ROUTES[path]
    operation = client.app.openapi()["paths"][path]["post"]
    assert operation["operationId"] == identity
    assert "security" not in operation
    for origin in (None, "https://evil.example.test", ORIGIN + "/"):
        r = client.post(path, json=body, headers={} if origin is None else {"Origin": origin})
        assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_CHECK_FAILED"
        assert "set-cookie" not in r.headers and r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [path for path, (identity, _) in ROUTES.items() if identity != "A05"])
def test_disabled_delivery_uniform_before_lookup(client, path):
    for email in ("absent@example.test", "verified@example.test", "inactive@example.test"):
        body = dict(ROUTES[path][1], email=email)
        r = client.post(path, json=body, headers={"Origin": ORIGIN, "Cookie": "__Host-shelfcash_session=unrelated"})
        assert r.status_code == 503
        assert r.json()["error"] == {
            "code": "EMAIL_DELIVERY_UNAVAILABLE",
            "message": "Tạm thời chưa thể gửi email; thử lại sau hoặc liên hệ hỗ trợ.",
            "details": {"reason_codes": ["EMAIL_DELIVERY_UNAVAILABLE"]},
        }
        assert r.headers["retry-after"] == "60"
        assert r.headers["access-control-allow-origin"] == ORIGIN
        assert "set-cookie" not in r.headers and email not in r.text


@pytest.mark.parametrize("body,code", [
    ({"email": "invalid", "display_name": "Holder"}, "INVALID_EMAIL"),
    ({"email": "holder@example.test", "display_name": "  "}, "VALIDATION_ERROR"),
    ({"email": "holder@example.test", "display_name": "Holder", "role": "OWNER"}, "VALIDATION_ERROR"),
])
def test_register_validation_before_capability(client, body, code):
    r = client.post("/api/v1/auth/register", json=body, headers={"Origin": ORIGIN})
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_verification_validation_and_request_limit(client):
    r = client.post("/api/v1/auth/email-verifications/complete", json={"token": "SECRET", "password": "short"}, headers={"Origin": ORIGIN})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PASSWORD_POLICY_VIOLATION"
    assert "SECRET" not in r.text
    r = client.post("/api/v1/auth/register", content=b"x" * 65537, headers={"Origin": ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.headers["access-control-allow-origin"] == ORIGIN


@pytest.mark.parametrize("path", ROUTES)
def test_malformed_json_safe_error_and_cors(client, path):
    r = client.post(path, content=b'{"email":', headers={"Origin": ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert "set-cookie" not in r.headers
    for origin in (None, "https://evil.example.test"):
        headers = {"Content-Type": "application/json"}
        if origin: headers["Origin"] = origin
        r = client.post(path, content=b'{"email":', headers=headers)
        assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_CHECK_FAILED"
