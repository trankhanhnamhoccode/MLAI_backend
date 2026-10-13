"""Real PostgreSQL + real public routes; all data synthetic, test DB guarded."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from app.application.contracts.auth import AuthError, CredentialCompletion, LoginRequest
from app.application.contracts.provisioning import ProvisionStoreCommand, VerifiedAccountCommand, IssueCredentialCommand
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.provisioning import AssistedProvisioning
from app.domain.permissions import PERMISSIONS
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.engine import create_database_engine
from app.main import create_app
from app.models import User, Store, StoreMembership, Product
from app.models.auth import AuthAccount, AuthSession, AuthAudit, CredentialToken, MembershipGrant

ORIGIN = "https://fe.example.test"
PASSWORD = "Synthetic password 123"
KEY = SecretStr("SYNTHETIC-OPERATOR-CREDENTIAL")


@pytest.fixture
def env(database_settings):
    settings = database_settings.model_copy(update={"auth_allowed_origins": [ORIGIN], "auth_operator_id": "support-test", "auth_operator_key": KEY})
    engine = create_database_engine(settings)
    clock = [datetime(2026, 10, 10, 2, tzinfo=timezone.utc)]
    auth = AuthUseCases(engine, clock=lambda: clock[0])
    provisioning = AssistedProvisioning(engine, settings, clock=lambda: clock[0])
    application = create_app(settings)
    application.state.auth = auth
    with TestClient(application, base_url="https://backend.example.test") as client:
        yield settings, engine, auth, provisioning, clock, client
    engine.dispose()


def provision(env, email="owner@example.test", *, store=True, existing=None):
    _, _, _, tool, _, _ = env
    cls = ProvisionStoreCommand if store else VerifiedAccountCommand
    fields = dict(request_reference=str(uuid4()), evidence_reference="support-case-verified-holder", email=email, display_name="Synthetic Owner", existing_user_id=existing)
    if store:
        fields["store_name"] = "Synthetic Cafe"
    return tool.provision(cls(**fields), "support-test", KEY)


def issue(env, receipt, *, email="owner@example.test", purpose="SETUP", deliver=None):
    secrets = []
    result = env[3].issue(IssueCredentialCommand(user_id=receipt.user_id, purpose=purpose,
        request_reference=str(uuid4()), evidence_reference="verified-account-holder", verified_email=email),
        "support-test", KEY, deliver or (lambda address, secret: secrets.append((address, secret.get_secret_value()))))
    return result, secrets[0][1] if secrets else None


def setup(env, email="owner@example.test", store=True):
    receipt = provision(env, email, store=store)
    _, token = issue(env, receipt, email=email)
    env[2].complete(CredentialCompletion(token=token, password=PASSWORD), "setup")
    return receipt


def login(env, email="owner@example.test", **body):
    return env[5].post("/api/v1/auth/login", headers={"Origin": ORIGIN}, json=dict(email=email, password=PASSWORD, **body))


def test_assisted_provision_atomic_retry_authority_and_unset_login(env):
    _, engine, _, tool, _, client = env
    command = ProvisionStoreCommand(request_reference="verified-store-1", evidence_reference="verified-owner-1", email="owner@example.test", display_name="Owner", store_name="Cafe")
    with pytest.raises(AuthError, match="OPERATOR_NOT_AUTHORIZED"):
        tool.provision(command, "attacker", KEY)
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User)) == 0
    first = tool.provision(command, "support-test", KEY)
    assert first == tool.provision(command, "support-test", KEY)
    with Session(engine) as fresh:
        user = fresh.get(User, first.user_id)
        assert user.password_hash == "!UNSET"
        assert not fresh.get(AuthAccount, user.id).credential_ready
        member = fresh.scalar(select(StoreMembership))
        assert member.role == "OWNER" and member.store_id == first.store_id
        assert member.delegated_permissions == []
        event = fresh.get(AuthAudit, first.audit_id)
        assert (event.operator_reference, event.evidence_reference) == ("support-test", "verified-owner-1")
        assert fresh.scalar(select(func.count()).select_from(Store)) == 1
    assert login(env).status_code == 401
    with pytest.raises(AuthError, match="EXISTING_ACCOUNT_REQUIRES_VERIFICATION"):
        provision(env)
    with pytest.raises(AuthError, match="IDEMPOTENCY_KEY_REUSED"):
        tool.provision(command.model_copy(update={"store_name": "Other"}), "support-test", KEY)


def test_login_me_store_logout_http_and_fresh_sessions(env):
    receipt = setup(env)
    _, engine, _, _, clock, client = env
    response = login(env)
    assert response.status_code == 200
    wire = response.json()
    assert wire["error"] is None and wire["meta"]["request_id"]
    assert wire["data"]["default_store_id"] == str(receipt.store_id)
    assert wire["data"]["accessible_store_count"] == 1
    session = wire["data"]["session"]
    assert session["expires_at"] == "2026-10-10T02:30:00Z"
    header = response.headers["set-cookie"]
    assert "__Host-shelfcash_session=" in header
    assert "Secure" in header and "HttpOnly" in header and "SameSite=lax" in header and "Path=/" in header
    assert "Domain" not in header and "Max-Age" not in header
    assert response.headers["cache-control"] == "no-store"
    raw = client.cookies.get("__Host-shelfcash_session")
    assert raw not in response.text
    with Session(engine) as fresh:
        persisted = fresh.get(AuthSession, digest(raw))
        assert persisted.user_id == receipt.user_id and persisted.revoked_at is None
        assert raw != persisted.digest
    clock[0] += timedelta(minutes=10)
    assert client.get("/api/v1/auth/me").json()["data"]["session"]["expires_at"] == "2026-10-10T02:40:00Z"
    stores = client.get("/api/v1/stores").json()
    assert stores["meta"]["pagination"] == dict(limit=50, next_cursor=None, total_count=1)
    context = client.get(f"/api/v1/stores/{receipt.store_id}").json()["data"]
    assert set(context["membership"]["effective_permissions"]) == PERMISSIONS
    assert context["as_of_date"] == "2026-10-10" and "budget" not in context
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    response = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
    assert response.status_code == 204 and response.content == b""
    with Session(engine) as fresh:
        assert fresh.get(AuthSession, digest(raw)).revoked_at is not None
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 204


def test_uniform_invalid_inactive_missing_and_throttle(env):
    receipt = setup(env)
    _, engine, _, _, clock, client = env
    attempts = []
    for email, password in [("missing@example.test", PASSWORD), ("owner@example.test", "wrong")]:
        r = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN}, json=dict(email=email, password=password))
        attempts.append(r.json()["error"])
        assert r.status_code == 401 and "Max-Age=0" in r.headers["set-cookie"]
    with Session(engine) as s:
        s.get(User, receipt.user_id).active = False
        s.commit()
    assert login(env).json()["error"] == attempts[0] == attempts[1]
    for _ in range(3):
        assert login(env).status_code == 401
    response = login(env)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    clock[0] += timedelta(minutes=16)
    assert login(env).status_code == 401


def test_origin_cors_payload_validation_and_no_secret_echo(env):
    client = env[5]
    for origin in [None, "https://evil.example.test"]:
        assert client.post("/api/v1/auth/login", json=dict(email="a@b.test", password=PASSWORD), headers={} if origin is None else {"Origin": origin}).status_code == 403
    preflight = client.options("/api/v1/auth/login", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type"})
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == ORIGIN
    assert preflight.headers["access-control-allow-credentials"] == "true"
    evil = client.options("/api/v1/auth/login", headers={"Origin": "https://evil.example.test", "Access-Control-Request-Method": "POST"})
    assert evil.status_code == 400 and "access-control-allow-origin" not in evil.headers
    for extra in [dict(role="OWNER"), dict(user_id=str(uuid4())), dict(store_id=str(uuid4()))]:
        response = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN}, json=dict(email="a@b.test", password=PASSWORD, **extra))
        assert response.status_code == 422 and PASSWORD not in response.text
    r = client.post("/api/v1/auth/credentials/complete", headers={"Origin": ORIGIN}, json=dict(token="synthetic-secret", password="short"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "PASSWORD_POLICY_VIOLATION"
    assert "synthetic-secret" not in r.text
    assert client.get("/api/v1/stores?store_id="+str(uuid4())).status_code == 422
    assert client.get("/api/v1/stores?limit=101").status_code == 422
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/register", json={}).status_code == 403


@pytest.mark.parametrize("remember,advance", [(False, timedelta(minutes=31)), (True, timedelta(days=8))])
def test_idle_expiry_and_remember_cookie(env, remember, advance):
    setup(env)
    response = login(env, remember_me=remember)
    assert ("Max-Age=2592000" in response.headers["set-cookie"]) is remember
    env[4][0] += advance
    assert env[5].get("/api/v1/auth/me").status_code == 401


def test_absolute_expiry_rotation_and_deactivation_revocation(env):
    receipt = setup(env)
    first = login(env).json()["data"]["session"]["csrf_token"]
    raw = env[5].cookies.get("__Host-shelfcash_session")
    second = login(env).json()["data"]["session"]["csrf_token"]
    assert first != second
    with Session(env[1]) as fresh:
        assert fresh.get(AuthSession, digest(raw)).revoked_at is not None
    for _ in range(15):
        env[4][0] += timedelta(minutes=29)
        assert env[5].get("/api/v1/auth/me").status_code == 200
    env[4][0] += timedelta(minutes=46)
    assert env[5].get("/api/v1/auth/me").status_code == 401
    login(env)
    newest = env[5].cookies.get("__Host-shelfcash_session")
    with Session(env[1]) as s:
        s.get(User, receipt.user_id).active = False
        s.commit()
    with Session(env[1]) as fresh:
        assert fresh.get(AuthSession, digest(newest)).revoked_at is not None
        fresh.get(User, receipt.user_id).active = True
        fresh.commit()
    assert env[5].get("/api/v1/auth/me").status_code == 401


def test_no_stores_multiple_stores_cursor_and_current_revocation(env):
    receipt = setup(env, store=False)
    data = login(env).json()["data"]
    assert data["accessible_store_count"] == 0 and data["default_store_id"] is None
    assert env[5].get("/api/v1/stores").json()["data"]["items"] == []
    a = provision(env, existing=receipt.user_id)
    b = provision(env, existing=receipt.user_id)
    data = env[5].get("/api/v1/auth/me").json()["data"]
    assert data["accessible_store_count"] == 2 and data["default_store_id"] is None
    first = env[5].get("/api/v1/stores?limit=1").json()
    cursor = first["meta"]["pagination"]["next_cursor"]
    second = env[5].get("/api/v1/stores", params={"limit": 1, "cursor": cursor}).json()
    assert second["data"]["items"][0]["store_id"] != first["data"]["items"][0]["store_id"]
    assert env[5].get("/api/v1/stores", params={"limit": 1, "cursor": cursor+"x"}).status_code == 422
    with Session(env[1]) as s:
        m = s.scalar(select(StoreMembership).where(StoreMembership.store_id == a.store_id))
        m.active = False
        s.commit()
    assert env[5].get(f"/api/v1/stores/{a.store_id}").status_code == 404
    assert env[5].get("/api/v1/auth/me").json()["data"]["default_store_id"] == str(b.store_id)
    assert env[5].get("/api/v1/stores", params={"limit": 1, "cursor": cursor}).status_code == 422


def test_store_isolation_staff_grants_owner_scope_resource_spoofing(env):
    owner = setup(env)
    staff = setup(env, "staff@example.test", store=False)
    other = provision(env, "other@example.test")
    with Session(env[1]) as s:
        m = StoreMembership(id=uuid4(), user_id=staff.user_id, store_id=owner.store_id, role="STAFF")
        p = Product(id=uuid4(), store_id=other.store_id, sku="other", name="Other", selling_unit="cup")
        s.add_all([m, p]); s.flush()
        s.add(MembershipGrant(membership_id=m.id, permission="menu.read"))
        mid, pid = m.id, p.id
        s.commit()
    login(env, "staff@example.test")
    raw = env[5].cookies.get("__Host-shelfcash_session")
    data = env[5].get(f"/api/v1/stores/{owner.store_id}").json()["data"]
    assert data["membership"]["effective_permissions"] == ["menu.read"]
    assert env[5].get(f"/api/v1/stores/{other.store_id}").status_code == 404
    with pytest.raises(AuthError, match="PERMISSION_DENIED"):
        env[2].authorize_resource(raw, owner.store_id, Product, pid, ("inventory.read",))
    with pytest.raises(AuthError, match="PERMISSION_DENIED"):
        env[2].authorize_resource(raw, owner.store_id, Product, pid, owner_only=True)
    with pytest.raises(AuthError, match="RESOURCE_NOT_FOUND"):
        env[2].authorize_resource(raw, owner.store_id, Product, pid, ("menu.read",))
    with Session(env[1]) as s:
        s.delete(s.get(MembershipGrant, (mid, "menu.read"))); s.commit()
    current = env[5].get(f"/api/v1/stores/{owner.store_id}").json()["data"]
    assert current["membership"]["effective_permissions"] == []
    assert current["authorization_version"] != data["authorization_version"]
    login(env)
    raw = env[5].cookies.get("__Host-shelfcash_session")
    with pytest.raises(AuthError, match="RESOURCE_NOT_FOUND"):
        env[2].authorize_resource(raw, other.store_id, Product, pid)


def test_setup_reset_reissue_expiry_and_single_use_http(env):
    receipt = provision(env)
    _, old = issue(env, receipt)
    _, token = issue(env, receipt)
    client = env[5]
    headers = {"Origin": ORIGIN}
    assert client.post("/api/v1/auth/credentials/complete", headers=headers, json=dict(token=old, password=PASSWORD)).status_code == 400
    done = client.post("/api/v1/auth/credentials/complete", headers=headers, json=dict(token=token, password=PASSWORD))
    assert done.status_code == 200 and done.json()["data"]["next_action"] == "login"
    assert "set-cookie" not in done.headers
    assert client.post("/api/v1/auth/credentials/complete", headers=headers, json=dict(token=token, password=PASSWORD)).status_code == 400
    login(env)
    session_secret = client.cookies.get("__Host-shelfcash_session")
    _, reset = issue(env, receipt, purpose="RESET")
    assert client.get("/api/v1/auth/me").status_code == 200  # issuing reset alone does not revoke
    env[2].complete(CredentialCompletion(token=reset, password=PASSWORD+" changed"), "reset")
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(env[1]) as fresh:
        assert fresh.get(AuthSession, digest(session_secret)).revoked_at is not None
        assert fresh.get(AuthAccount, receipt.user_id).credential_revision == 3
        assert fresh.get(CredentialToken, digest(reset)).consumed_at is not None
        assert fresh.get(User, receipt.user_id).password_hash.startswith("$argon2id$")
    _, expired = issue(env, receipt, purpose="RESET")
    env[4][0] += timedelta(minutes=30)
    with pytest.raises(AuthError, match="CREDENTIAL_TOKEN_INVALID"):
        env[2].complete(CredentialCompletion(token=expired, password=PASSWORD), "reset")


def test_concurrent_completion_only_one_revision_and_provision_retry(env):
    receipt = provision(env)
    _, token = issue(env, receipt)
    def attempt(_):
        try:
            env[2].complete(CredentialCompletion(token=token, password=PASSWORD), "race")
            return "completed"
        except AuthError as e:
            return e.code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ["CREDENTIAL_TOKEN_INVALID", "completed"]
    with Session(env[1]) as fresh:
        assert fresh.get(AuthAccount, receipt.user_id).credential_revision == 2
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind=="CREDENTIAL_COMPLETED")) == 1
    command = ProvisionStoreCommand(request_reference="same-concurrent-reference", evidence_reference="verified", email="race@example.test", display_name="Race", store_name="Race Cafe")
    with ThreadPoolExecutor(2) as pool:
        receipts = list(pool.map(lambda _: env[3].provision(command, "support-test", KEY), range(2)))
    assert receipts[0] == receipts[1]
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User).where(User.email=="race@example.test")) == 1


def test_delivery_failure_does_not_enable_account_or_leak_token(env):
    receipt = provision(env)
    def failure(address, secret):
        assert address == "owner@example.test"
        raise OSError("synthetic-delivery-failure")
    result, raw = issue(env, receipt, deliver=failure)
    assert result.status == "failed" and raw is None
    with Session(env[1]) as fresh:
        assert not fresh.get(AuthAccount, receipt.user_id).credential_ready
        assert fresh.scalar(select(CredentialToken)).consumed_at is not None
        assert fresh.scalar(select(AuthAudit).where(AuthAudit.kind=="CREDENTIAL_DELIVERY_FAILED")) is not None
    assert login(env).status_code == 401


@pytest.mark.parametrize("phase", ["provision", "complete", "login"])
def test_transaction_failure_rolls_back_whole_aggregate(env, monkeypatch, phase):
    receipt = token = None
    if phase != "provision":
        receipt = provision(env)
        _, token = issue(env, receipt)
        if phase == "login":
            env[2].complete(CredentialCompletion(token=token, password=PASSWORD), "setup")
    original = Session.commit
    def fail(s):
        # Allow separate throttle transaction; reject actual credential mutation.
        if phase=="complete" and not any(isinstance(x, AuthAudit) and x.kind=="CREDENTIAL_COMPLETED" for x in s.new):
            return original(s)
        s.flush()
        raise ValueError("synthetic-commit-programming-failure")
    with monkeypatch.context() as m:
        m.setattr(Session, "commit", fail)
        with pytest.raises(ValueError):
            if phase=="provision":
                provision(env)
            elif phase=="complete":
                env[2].complete(CredentialCompletion(token=token, password=PASSWORD), "test")
            else:
                env[2].login(LoginRequest(email="owner@example.test", password=PASSWORD), "test")
    with Session(env[1]) as fresh:
        if phase=="provision":
            assert fresh.scalar(select(func.count()).select_from(User)) == 0
            assert fresh.scalar(select(func.count()).select_from(Store)) == 0
            assert fresh.scalar(select(func.count()).select_from(AuthAudit)) == 0
        elif phase=="complete":
            assert fresh.get(User, receipt.user_id).password_hash == "!UNSET"
            assert fresh.get(CredentialToken, digest(token)).consumed_at is None
            assert fresh.get(AuthAccount, receipt.user_id).credential_revision == 1
        else:
            assert fresh.scalar(select(func.count()).select_from(AuthSession)) == 0
            assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind=="LOGIN")) == 0


def test_store_inactive_and_reset_all_sessions_not_other_accounts(env):
    owner = setup(env)
    another = setup(env, "another@example.test", store=False)
    _, a = env[2].login(LoginRequest(email="owner@example.test", password=PASSWORD), "direct-a")
    _, b = env[2].login(LoginRequest(email="owner@example.test", password=PASSWORD), "direct-b")
    _, untouched = env[2].login(LoginRequest(email="another@example.test", password=PASSWORD), "direct-other")
    with Session(env[1]) as s:
        s.get(Store, owner.store_id).active = False
        s.commit()
    assert env[2].me(a).accessible_store_count == 0
    with pytest.raises(AuthError, match="RESOURCE_NOT_FOUND"):
        env[2].store_context(a, owner.store_id)
    _, reset = issue(env, owner, purpose="RESET")
    env[2].complete(CredentialCompletion(token=reset, password=PASSWORD+" new"), "reset-all")
    for raw in (a, b):
        with pytest.raises(AuthError, match="UNAUTHENTICATED"):
            env[2].me(raw)
    assert env[2].me(untouched).user.user_id == another.user_id
    with Session(env[1]) as fresh:
        assert fresh.get(AuthSession, digest(a)).revoked_at and fresh.get(AuthSession, digest(b)).revoked_at
        assert fresh.get(AuthSession, digest(untouched)).revoked_at is None


def test_http_programming_commit_error_never_success_and_no_secret_echo(env, monkeypatch):
    setup(env)
    original = Session.commit
    def bug(s):
        original(s)
        raise ValueError("SYNTHETIC-DO-NOT-ECHO")
    with monkeypatch.context() as m:
        m.setattr(Session, "commit", bug)
        response = login(env)
        assert response.status_code == 503 and "SYNTHETIC-DO-NOT-ECHO" not in response.text
        assert "set-cookie" not in response.headers
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(AuthSession)) == 1
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind=="LOGIN")) == 1


def test_credential_expiry_is_rechecked_after_lock_wait(env, monkeypatch):
    receipt = provision(env)
    _, token = issue(env, receipt)
    from threading import Event
    entered, release, waiting = Event(), Event(), Event()
    from app.repositories.auth import AuthRepository
    original = AuthRepository.lock_user
    def observed_wait(repository, user_id):
        waiting.set()
        return original(repository, user_id)
    monkeypatch.setattr(AuthRepository, "lock_user", observed_wait)
    def holder():
        with Session(env[1]) as s:
            s.scalar(select(User).where(User.id==receipt.user_id).with_for_update())
            entered.set()
            assert release.wait(10)
            s.commit()
    with ThreadPoolExecutor(2) as pool:
        lock = pool.submit(holder)
        assert entered.wait(10)
        pending = pool.submit(env[2].complete, CredentialCompletion(token=token, password=PASSWORD), "lock-expiry")
        assert waiting.wait(10)
        env[4][0] += timedelta(minutes=30)
        release.set()
        lock.result()
        with pytest.raises(AuthError, match="CREDENTIAL_TOKEN_INVALID"):
            pending.result()
    with Session(env[1]) as fresh:
        assert not fresh.get(AuthAccount, receipt.user_id).credential_ready
        assert fresh.get(CredentialToken, digest(token)).consumed_at is None


def test_authorization_fence_uses_current_membership_and_does_not_commit(env):
    receipt = setup(env)
    _, raw = env[2].login(LoginRequest(email="owner@example.test", password=PASSWORD), "fence")
    with Session(env[1]) as s:
        transaction = s.begin()
        actor, summary, permissions = env[2].authorize_in_session(s, raw, receipt.store_id, ("budget.read",), owner_only=True)
        assert s.get_transaction() is transaction and s.in_transaction()
        assert actor.user_id == receipt.user_id and set(permissions) == PERMISSIONS
        s.rollback()
    with Session(env[1]) as s:
        s.scalar(select(StoreMembership).where(StoreMembership.store_id==receipt.store_id)).active = False
        s.commit()
    with Session(env[1]) as s:
        with pytest.raises(AuthError, match="RESOURCE_NOT_FOUND"):
            env[2].authorize_in_session(s, raw, receipt.store_id, owner_only=True)


def test_grants_aba_changes_version_and_no_action_is_deny_by_default(env):
    receipt = setup(env)
    staff = setup(env, "staff@example.test", store=False)
    with Session(env[1]) as s:
        member = StoreMembership(id=uuid4(), user_id=staff.user_id, store_id=receipt.store_id, role="STAFF")
        product = Product(id=uuid4(), store_id=receipt.store_id, name="Own Product", selling_unit="cup")
        s.add_all([member, product]); s.flush()
        mid, pid = member.id, product.id
        s.commit()
    _, raw = env[2].login(LoginRequest(email="staff@example.test", password=PASSWORD), "aba")
    initial = env[2].store_context(raw, receipt.store_id).authorization_version
    with Session(env[1]) as s:
        s.add(MembershipGrant(membership_id=mid, permission="menu.read")); s.commit()
    added = env[2].store_context(raw, receipt.store_id).authorization_version
    assert env[2].authorize_resource(raw, receipt.store_id, Product, pid, ("menu.read",)).user_id == staff.user_id
    with Session(env[1]) as s:
        s.delete(s.get(MembershipGrant, (mid, "menu.read"))); s.commit()
    removed = env[2].store_context(raw, receipt.store_id).authorization_version
    assert len({initial, added, removed}) == 3
    with Session(env[1]) as fresh:
        assert fresh.get(StoreMembership, mid).authorization_revision == 3
        assert fresh.get(StoreMembership, mid).delegated_permissions == []
    with pytest.raises(AuthError, match="PERMISSION_DENIED"):
        env[2].authorize_resource(raw, receipt.store_id, Product, pid)
    with pytest.raises(AuthError, match="PERMISSION_DENIED"):
        env[2].authorize_resource(raw, receipt.store_id, Product, pid, ("menu.read",))


def test_identity_proof_email_change_and_operator_reset_do_not_guess_holder(env):
    receipt = provision(env)
    _, token = issue(env, receipt)
    with pytest.raises(AuthError, match="IDENTITY_VERIFICATION_MISMATCH"):
        issue(env, receipt, email="someone-else@example.test")
    with Session(env[1]) as s:
        s.get(User, receipt.user_id).email = "changed@example.test"
        s.commit()
    with pytest.raises(AuthError, match="CREDENTIAL_TOKEN_INVALID"):
        env[2].complete(CredentialCompletion(token=token, password=PASSWORD), "proof")
    assert login(env, "changed@example.test").status_code == 401


def test_ip_and_completion_rate_limits_survive_new_service_instance(env):
    # Exercise persistent limiter through HTTP; real Argon2 verifies login failures.
    for index in range(100):
        assert login(env, f"synthetic-{index}@example.test").status_code == 401
    limited = login(env, "fresh-address@example.test")
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "RATE_LIMITED"
    for _ in range(10):
        response = env[5].post("/api/v1/auth/credentials/complete", headers={"Origin": ORIGIN}, json=dict(token="synthetic-invalid", password=PASSWORD))
        assert response.status_code == 400
    replacement = AuthUseCases(env[1], clock=lambda: env[4][0])
    with pytest.raises(AuthError) as error:
        replacement.complete(CredentialCompletion(token="synthetic-invalid", password=PASSWORD), "testclient")
    assert error.value.status == 429 and error.value.retry_after


def test_grant_revoke_waits_for_authorization_fence_and_next_request_denies(env):
    receipt = setup(env)
    staff = setup(env, "staff@example.test", store=False)
    with Session(env[1]) as s:
        member = StoreMembership(id=uuid4(), user_id=staff.user_id, store_id=receipt.store_id, role="STAFF")
        s.add(member); s.flush()
        mid = member.id
        s.add(MembershipGrant(membership_id=mid, permission="menu.read")); s.commit()
    _, raw = env[2].login(LoginRequest(email="staff@example.test", password=PASSWORD), "revoke-fence")
    from threading import Event
    from time import monotonic, sleep
    started = Event()
    def revoke():
        with Session(env[1]) as s:
            s.execute(text("SET LOCAL application_name = 's41-revoke-test'"))
            started.set()
            s.delete(s.get(MembershipGrant, (mid, "menu.read")))
            s.commit()  # Grant trigger must lock same membership.
    with Session(env[1]) as fence, ThreadPoolExecutor(1) as pool:
        env[2].authorize_in_session(fence, raw, receipt.store_id, ("menu.read",))
        future = pool.submit(revoke)
        assert started.wait(10)
        deadline, waiting = monotonic()+5, False
        while monotonic() < deadline:
            with env[1].connect() as monitor:
                waiting = bool(monitor.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = current_database() AND application_name = 's41-revoke-test' AND wait_event_type = 'Lock')")))
            if waiting:
                break
            sleep(.02)
        # Always release before waiting on executor, including assertion failure.
        fence.commit()
        future.result(timeout=10)
        assert waiting, "Real PostgreSQL revoke did not wait on authority fence"
    with Session(env[1]) as fresh:
        assert fresh.get(MembershipGrant, (mid, "menu.read")) is None
    with Session(env[1]) as s:
        with pytest.raises(AuthError, match="PERMISSION_DENIED"):
            env[2].authorize_in_session(s, raw, receipt.store_id, ("menu.read",))


def test_explicit_dev_cookie_requires_loopback_peer_and_has_separate_name(env):
    setup(env)
    origin = "http://localhost:3000"
    settings = env[0].model_copy(update={"auth_dev_cookie": True, "auth_allowed_origins": [origin]})
    app = create_app(settings)
    app.state.auth = env[2]
    with TestClient(app, base_url="http://localhost") as remote:
        # A loopback Host alone cannot opt a remote peer into insecure transport.
        assert remote.post("/api/v1/auth/login", headers={"Origin": origin}, json=dict(email="owner@example.test", password=PASSWORD)).status_code == 403
    async def loopback(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": ("127.0.0.1", 55000)}
        await app(scope, receive, send)
    with TestClient(loopback, base_url="http://localhost") as local:
        response = local.post("/api/v1/auth/login", headers={"Origin": origin}, json=dict(email="owner@example.test", password=PASSWORD))
        assert response.status_code == 200
        assert "shelfcash_dev_session=" in response.headers["set-cookie"]
        assert "__Host-" not in response.headers["set-cookie"] and "Secure" not in response.headers["set-cookie"]
        assert local.get("/api/v1/auth/me").status_code == 200
