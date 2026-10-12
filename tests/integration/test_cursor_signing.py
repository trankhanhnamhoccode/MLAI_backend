"""Client-held session must not be sufficient to sign authoritative cursors."""

import base64
import hashlib
import hmac
import json
from uuid import uuid4

from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, login, provision
from tests.integration.test_staff_public import staff_env
from app.models import User, StoreMembership


def forged_offset(cursor, raw):
    data = json.loads(base64.urlsafe_b64decode(cursor.split(".")[0]))
    data["offset"] = 2
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return (
        payload
        + "."
        + hmac.new(raw.encode(), payload.encode(), hashlib.sha256).hexdigest()
    )


def test_client_cannot_forge_t01_cursor(env):
    owner = setup(env)
    for _ in range(2):
        provision(env, existing=owner.user_id)
    assert login(env).status_code == 200
    first = env[5].get("/api/v1/stores", params={"limit": 1})
    assert first.status_code == 200
    cursor = first.json()["meta"]["pagination"]["next_cursor"]
    raw = env[5].cookies.get("__Host-shelfcash_session")
    response = env[5].get(
        "/api/v1/stores", params={"limit": 1, "cursor": forged_offset(cursor, raw)}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
    assert (
        env[5].get("/api/v1/stores", params={"limit": 1, "cursor": cursor}).status_code
        == 200
    )
    assert (
        env[5].get("/api/v1/stores", params={"limit": 2, "cursor": cursor}).status_code
        == 422
    )
    from tests.integration.test_auth_public import PASSWORD
    from app.application.contracts.auth import LoginRequest

    _, new_raw = env[2].login(
        LoginRequest(email="owner@example.test", password=PASSWORD), "second-session"
    )
    env[5].cookies.set(
        "__Host-shelfcash_session", new_raw, domain="backend.example.test", path="/"
    )
    assert (
        env[5].get("/api/v1/stores", params={"limit": 1, "cursor": cursor}).status_code
        == 422
    )


def test_client_cannot_forge_staff_cursor(staff_env):
    env, _, owner, _, raw, _ = staff_env
    with Session(env[1]) as s:
        for i in range(3):
            user = User(
                email=f"paging-{i}@example.test",
                display_name=f"Staff {i}",
                password_hash="!UNSET",
            )
            s.add(user)
            s.flush()
            s.add(
                StoreMembership(user_id=user.id, store_id=owner.store_id, role="STAFF")
            )
        s.commit()
    route = f"/api/v1/stores/{owner.store_id}/memberships"
    first = env[5].get(route, params={"limit": 1})
    assert first.status_code == 200
    cursor = first.json()["meta"]["pagination"]["next_cursor"]
    response = env[5].get(
        route, params={"limit": 1, "cursor": forged_offset(cursor, raw)}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
    assert env[5].get(route, params={"limit": 1, "cursor": cursor}).status_code == 200
    assert (
        env[5]
        .get(route, params={"limit": 1, "cursor": cursor, "active": "true"})
        .status_code
        == 422
    )
    inaccessible = f"/api/v1/stores/{uuid4()}/memberships"
    assert (
        env[5]
        .get(inaccessible, params={"limit": 1, "cursor": forged_offset(cursor, raw)})
        .status_code
        == 404
    )
