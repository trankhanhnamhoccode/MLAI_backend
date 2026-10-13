from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.application.contracts.auth import LoginRequest, CredentialCompletion, AuthContext, Envelope, Meta, SessionSummary, UserSummary
from app.config import Settings
from app.domain.permissions import CATALOGUE, CATALOG_VERSION, PERMISSIONS, effective_permissions
from app.infrastructure.auth_crypto import HASHER, verify_password


def test_catalogue_is_explicit_no_implications():
    assert CATALOG_VERSION == "permissions-v3"
    assert len(PERMISSIONS) == 43
    assert effective_permissions("STAFF", ("planning.run",)) == ("planning.run",)
    assert set(effective_permissions("OWNER", ())) == PERMISSIONS
    assert all(p.grantable_to_staff and p.label_vi and p.description_vi for p in CATALOGUE)
    for role, grants in [("ADMIN", ()), ("STAFF", ("fake",)), ("STAFF", ("menu.read", "menu.read"))]:
        with pytest.raises(ValueError):
            effective_permissions(role, grants)


def test_credentials_preserve_password_and_argon2id():
    request = LoginRequest(email=" OWNER@Example.test ", password="  long password  ")
    assert request.email == "owner@example.test" and request.password == "  long password  "
    assert request.password not in repr(request)
    encoded = HASHER.hash(request.password)
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, request.password)
    assert not verify_password(encoded, request.password.strip())
    assert not verify_password("opaque-historical-hash", request.password)


@pytest.mark.parametrize("payload", [
    dict(email="no-email", password="some-password"),
    dict(email="a@b.test", password="some-password", role="OWNER"),
    dict(email="a@b.test", password=True),
    dict(email="a@b.test", password="some-password", remember_me=1),
])
def test_login_boundary_rejects_spoofed_or_invalid_fields(payload):
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(payload)


@pytest.mark.parametrize("password", ["short", "x"*129, True])
def test_completion_password_policy(password):
    with pytest.raises(ValidationError):
        CredentialCompletion(token="synthetic", password=password)


def test_production_cannot_enable_insecure_cookie_or_wildcard_origin():
    for options in [dict(environment="production", auth_dev_cookie=True), dict(auth_allowed_origins=["*"]), dict(auth_allowed_origins=["https://*.example.test"]), dict(auth_allowed_origins=["http://external.test"]), dict(auth_allowed_origins=["https://fe.test/"])]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **options)


def test_auth_envelope_keeps_required_nulls():
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    context = AuthContext(user=UserSummary(user_id=uuid4(), email="a@b.test", display_name="A"),
        session=SessionSummary(expires_at=now, absolute_expires_at=now, csrf_token="synthetic"),
        default_store_id=None, accessible_store_count=0, authorization_version="auth-1")
    wire = Envelope[AuthContext](data=context, meta=Meta(request_id="test"), error=None).model_dump(mode="json")
    assert wire["error"] is None and wire["data"]["default_store_id"] is None
    assert wire["meta"] == {"request_id": "test"}
