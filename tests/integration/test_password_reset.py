"""B2 public RESET acceptance, fake delivery and fresh-session state only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.application.contracts.auth import AuthError, CredentialCompletion, LoginRequest, PublicEmailRequest
from app.application.use_cases.password_reset import PasswordReset
from app.application.use_cases.password_reset_delivery import PasswordResetDispatcher
from app.infrastructure.auth_crypto import digest, verify_password
from app.models import User, Store, StoreMembership
from app.models.auth import AuthAccount, AuthAudit, AuthSession, CredentialToken, MembershipGrant
from app.models.password_reset import PasswordResetDelivery
from tests.integration.test_email_verification import env, signup, delivered_token, complete, post, EMAIL, PASSWORD, ORIGIN

NEW_PASSWORD = "New synthetic holder password"


@pytest.fixture
def reset_env(env):
    auth, transport, settings = env[2], env[3], env[7]
    request = PasswordReset(auth, settings, transport)
    dispatcher = PasswordResetDispatcher(auth, settings, transport)
    env[6].app.state.password_reset = request
    env[6].app.state.password_reset_dispatcher = dispatcher
    return env, request, dispatcher


def verified(env):
    signup(env)
    assert complete(env, delivered_token(env)).status_code == 200
    env[3].messages.clear()
    with Session(env[0]) as fresh:
        return fresh.scalar(select(User.id))


def request_reset(reset_env, email=EMAIL):
    response = post(reset_env[0], "password-reset/request", dict(email=email))
    assert response.status_code == 202, response.text
    assert response.json()["data"] == dict(next_action="check_email", delivery={"status": "accepted"}, retry_after_seconds=60)
    assert response.json()["error"] is None and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store" and response.headers["access-control-allow-origin"] == ORIGIN
    assert email not in response.text
    return response


def reset_token(reset_env):
    assert reset_env[2].dispatch()["delivered"] == 1
    return reset_env[0][3].messages[-1][1]


def finish(env, raw, password=NEW_PASSWORD):
    return post(env, "credentials/complete", dict(token=raw, password=password))


def active_sessions(env):
    first_context, first = env[2].login(LoginRequest(email=EMAIL, password=PASSWORD), "device-1")
    _, second = env[2].login(LoginRequest(email=EMAIL, password=PASSWORD, remember_me=True), "device-2")
    env[6].cookies.set("__Host-shelfcash_session", first)
    return first, second


def assert_sessions_work(env, tokens):
    for token in tokens:
        assert env[2].me(token).user.email == EMAIL


def test_public_reset_fake_delivery_n7_relogin_and_all_old_sessions_revoked(reset_env):
    env, _, _ = reset_env
    uid = verified(env)
    old_sessions = active_sessions(env)
    with Session(env[0]) as fresh:
        old_hash = fresh.get(User, uid).password_hash
        before = fresh.get(AuthAccount, uid).credential_revision
    request_reset(reset_env)
    assert_sessions_work(env, old_sessions)
    with Session(env[0]) as fresh:
        token = fresh.scalar(select(CredentialToken).where(CredentialToken.purpose == "RESET"))
        assert token.revision == before and token.expires_at-token.issued_at == timedelta(minutes=30)
        assert fresh.get(User, uid).password_hash == old_hash
        intent = fresh.scalar(select(PasswordResetDelivery))
        assert intent.ciphertext and intent.status == "queued" and intent.email == EMAIL
    raw = reset_token(reset_env)
    assert finish(env, raw, "short").status_code == 422
    assert finish(env, "invalid-token").status_code == 400
    assert_sessions_work(env, old_sessions)
    response = finish(env, raw)
    assert response.status_code == 200 and response.json()["data"]["next_action"] == "login"
    assert "set-cookie" not in response.headers and raw not in response.text
    with Session(env[0]) as fresh:
        assert fresh.get(AuthAccount, uid).credential_revision == before+1
        assert verify_password(fresh.get(User, uid).password_hash, NEW_PASSWORD)
        assert fresh.get(CredentialToken, digest(raw)).consumed_at == env[1][0]
        assert all(row.revoked_at == env[1][0] for row in fresh.scalars(select(AuthSession)))
        assert fresh.scalar(select(PasswordResetDelivery)).ciphertext is None
        audit = fresh.scalar(select(AuthAudit).where(AuthAudit.request_reference == response.json()["meta"]["request_id"]+":reset-complete"))
        assert "RESET;delivery=" in audit.evidence_reference and raw not in audit.evidence_reference
        for model in (Store, StoreMembership, MembershipGrant):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
    assert env[6].get("/api/v1/auth/me").status_code == 401
    for old in old_sessions:
        with pytest.raises(AuthError, match="UNAUTHENTICATED"):
            env[2].me(old)
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 401
    assert post(env, "login", dict(email=EMAIL, password=NEW_PASSWORD)).status_code == 200
    assert env[6].get("/api/v1/stores").json()["data"]["items"] == []
    assert finish(env, raw).status_code == 400


@pytest.mark.parametrize("state", ["unknown", "unverified", "inactive", "verified", "verified_unset", "changed_email_proof"])
def test_generic_acceptance_only_active_verified_accounts_get_reset_intent(reset_env, state):
    env = reset_env[0]
    uid = None
    if state == "unverified":
        signup(env)
    elif state != "unknown":
        uid = verified(env)
        with Session(env[0]) as session:
            if state == "inactive": session.get(User, uid).active = False
            if state == "verified_unset": session.get(AuthAccount, uid).credential_ready = False
            if state == "changed_email_proof": session.get(User, uid).email = "other@example.test"
            session.commit()
    request_reset(reset_env)
    with Session(env[0]) as fresh:
        expected = int(state in {"verified", "verified_unset"})
        assert fresh.scalar(select(func.count()).select_from(PasswordResetDelivery)) == expected
        assert fresh.scalar(select(func.count()).select_from(CredentialToken).where(CredentialToken.purpose == "RESET")) == expected
        if state == "unknown": assert fresh.scalar(select(func.count()).select_from(User)) == 0
    if state == "verified_unset":
        assert finish(env, reset_token(reset_env)).status_code == 200


def test_disabled_capability_uniform_before_lookup_and_existing_token_still_completes(reset_env, monkeypatch):
    from app.repositories.auth import AuthRepository
    env = reset_env[0]
    verified(env)
    request_reset(reset_env)
    raw = reset_token(reset_env)
    env[3].available = False
    def forbidden(*args): raise AssertionError("Account lookup forbidden while service disabled")
    with monkeypatch.context() as guards:
        guards.setattr(AuthRepository, "lock_user_by_email", forbidden)
        errors = []
        for email in (EMAIL, "unknown@example.test", "unverified@example.test", "inactive@example.test"):
            response = post(env, "password-reset/request", dict(email=email))
            assert response.status_code == 503 and response.headers["retry-after"] == "60"
            assert response.headers["access-control-allow-origin"] == ORIGIN and "set-cookie" not in response.headers
            errors.append(response.json()["error"])
        assert all(error == errors[0] for error in errors)
        assert errors[0]["code"] == "EMAIL_DELIVERY_UNAVAILABLE"
    assert finish(env, raw).status_code == 200


def test_reissue_cooldown_old_token_invalid_and_quotas_do_not_revoke_sessions(reset_env):
    env = reset_env[0]
    uid = verified(env)
    old_sessions = active_sessions(env)
    request_reset(reset_env)
    old = reset_token(reset_env)
    request_reset(reset_env)  # shared email budget includes prior B1 signup
    env[1][0] += timedelta(seconds=60)
    request_reset(reset_env)  # email budget exhausted: generic acceptance, no issue
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PasswordResetDelivery)) == 1
    env[1][0] += timedelta(minutes=15)
    request_reset(reset_env)
    current = reset_token(reset_env)
    assert current != old and finish(env, old).status_code == 400
    assert_sessions_work(env, old_sessions)
    with Session(env[0]) as fresh:
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)
        assert fresh.get(CredentialToken, digest(old)).consumed_at is not None
    assert finish(env, current).status_code == 200


def test_expiry_single_use_wrong_purpose_and_concurrent_completion(reset_env):
    env, _, _ = reset_env
    verified(env)
    request_reset(reset_env)
    raw = reset_token(reset_env)
    assert complete(env, raw).status_code == 400  # RESET cannot establish EMAIL_VERIFY proof.
    signup(env, "other-holder@example.test")
    verification_token = delivered_token(env)
    assert finish(env, verification_token).status_code == 400  # Live EMAIL_VERIFY cannot be consumed by N7.
    def consume(i):
        try: return env[2].complete(CredentialCompletion(token=raw, password=NEW_PASSWORD), f"race-{i}").next_action
        except AuthError as error: return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(consume, range(2))) == ["CREDENTIAL_TOKEN_INVALID", "login"]
    assert finish(env, raw).status_code == 400
    env[1][0] += timedelta(seconds=60)
    request_reset(reset_env)
    expired = reset_token(reset_env)
    env[1][0] += timedelta(minutes=30)
    assert finish(env, expired).status_code == 400
    with Session(env[0]) as fresh:
        assert fresh.get(CredentialToken, digest(expired)).consumed_at is None
        assert verify_password(fresh.scalar(select(User).where(User.email == EMAIL)).password_hash, NEW_PASSWORD)


@pytest.mark.parametrize("change", ["proof", "email", "credential", "inactive"])
def test_stale_binding_blocks_completion_and_delivery(reset_env, change):
    env = reset_env[0]
    uid = verified(env)
    request_reset(reset_env)
    from app.infrastructure.invitation_secret import InvitationSecret
    from app.application.use_cases.password_reset import delivery_identity
    with Session(env[0]) as fresh:
        intent = fresh.scalar(select(PasswordResetDelivery))
        raw = InvitationSecret(env[7].auth_delivery_encryption_key).open(intent.ciphertext,
            delivery_identity(intent.token_digest, intent.id)).get_secret_value()
    with Session(env[0]) as session:
        if change == "proof": session.get(AuthAccount, uid).proof_revision += 1
        elif change == "email": session.get(User, uid).email = "other@example.test"
        elif change == "credential": session.get(AuthAccount, uid).credential_revision += 1
        else: session.get(User, uid).active = False
        session.commit()
    assert finish(env, raw).status_code == 400
    assert reset_env[2].dispatch()["cancelled"] == 1
    assert not env[3].messages
    with Session(env[0]) as fresh:
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)
        assert fresh.get(CredentialToken, digest(raw)).consumed_at is None


@pytest.mark.parametrize("phase", ["request", "completion"])
def test_atomic_audit_failure_rolls_back_request_or_completion_without_session_revocation(reset_env, monkeypatch, phase):
    env = reset_env[0]
    uid = verified(env)
    old_sessions = active_sessions(env)
    raw = None
    if phase == "completion":
        request_reset(reset_env)
        raw = reset_token(reset_env)
    def fault(*args, **kwargs): raise RuntimeError("SYNTHETIC-PRIVATE-RESET-FAULT")
    with monkeypatch.context() as faults:
        faults.setattr(env[2], "_audit", fault)
        response = post(env, "password-reset/request", dict(email=EMAIL)) if phase == "request" else finish(env, raw)
        assert response.status_code == 503 and "SYNTHETIC-PRIVATE-RESET-FAULT" not in response.text
    assert_sessions_work(env, old_sessions)
    with Session(env[0]) as fresh:
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)
        if phase == "request": assert fresh.scalar(select(func.count()).select_from(PasswordResetDelivery)) == 0
        else: assert fresh.get(CredentialToken, digest(raw)).consumed_at is None


@pytest.mark.parametrize("phase", ["request", "completion"])
def test_lost_commit_ack_retry_does_not_duplicate_or_overwrite(reset_env, monkeypatch, phase):
    env = reset_env[0]
    uid = verified(env)
    old_sessions = active_sessions(env)
    raw = None
    if phase == "completion":
        request_reset(reset_env)
        raw = reset_token(reset_env)
    kind = "PASSWORD_RESET_ISSUED" if phase == "request" else "CREDENTIAL_COMPLETED"
    original_audit, original_commit = env[2]._audit, Session.commit
    def marked(session, audit_kind, *args, **kwargs):
        if audit_kind == kind: session.info["lose-reset-ack"] = True
        original_audit(session, audit_kind, *args, **kwargs)
    def uncertain(session):
        lose = session.info.get("lose-reset-ack", False)
        original_commit(session)
        if lose: raise RuntimeError("SYNTHETIC-PRIVATE-RESET-ACK")
    with monkeypatch.context() as faults:
        faults.setattr(env[2], "_audit", marked)
        faults.setattr(Session, "commit", uncertain)
        response = post(env, "password-reset/request", dict(email=EMAIL)) if phase == "request" else finish(env, raw)
        assert response.status_code == 503 and "set-cookie" not in response.headers
        assert "SYNTHETIC-PRIVATE-RESET-ACK" not in response.text
    if phase == "request":
        assert_sessions_work(env, old_sessions)
        request_reset(reset_env)
        with Session(env[0]) as fresh:
            assert fresh.scalar(select(func.count()).select_from(PasswordResetDelivery)) == 1
        assert finish(env, reset_token(reset_env)).status_code == 200
    else:
        assert finish(env, raw, "Different retry password").status_code == 400
        with Session(env[0]) as fresh:
            assert all(row.revoked_at is not None for row in fresh.scalars(select(AuthSession)))
    assert post(env, "login", dict(email=EMAIL, password=NEW_PASSWORD)).status_code == 200
    with Session(env[0]) as fresh:
        assert fresh.get(AuthAccount, uid).credential_revision == 3
        assert verify_password(fresh.get(User, uid).password_hash, NEW_PASSWORD)


def test_fake_delivery_failure_uncertain_recovery_reissue_and_no_secret_logs(reset_env, caplog):
    env, _, dispatcher = reset_env
    verified(env)
    sessions = active_sessions(env)
    request_reset(reset_env)
    env[3].fail = True
    assert dispatcher.dispatch()["failed"] == 1
    assert "SYNTHETIC-SECRET-PROVIDER-FAILURE" not in caplog.text
    assert_sessions_work(env, sessions)
    env[3].fail = False
    env[1][0] += timedelta(seconds=60)
    request_reset(reset_env)
    with Session(env[0]) as fresh:
        identifier = fresh.scalar(select(PasswordResetDelivery.id).where(PasswordResetDelivery.status == "queued"))
    attempt = dispatcher.claim(identifier)
    from app.infrastructure.invitation_secret import InvitationSecret
    secret = InvitationSecret(env[7].auth_delivery_encryption_key).open(attempt.ciphertext, attempt.identity)
    env[3](attempt.address, secret)  # send succeeded, settlement acknowledgment lost
    assert dispatcher.dispatch()["delivered"] == 0
    env[1][0] += timedelta(seconds=61)
    assert dispatcher.dispatch()["delivered"] == 1
    assert env[3].messages[-1] == env[3].messages[-2]
    assert not dispatcher.settle(attempt, "delivered")
    assert finish(env, env[3].messages[-1][1]).status_code == 200


def test_http_ip_and_shared_completion_limits_persist_and_expire(reset_env):
    env = reset_env[0]
    for i in range(20): request_reset(reset_env, f"absent-{i}@example.test")
    response = post(env, "password-reset/request", dict(email=EMAIL))
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert response.headers["access-control-allow-origin"] == ORIGIN
    for i in range(10): assert finish(env, "bad-token").status_code == 400
    assert finish(env, "bad-token").status_code == 429
    assert complete(env, "bad-token").status_code == 429  # B1 and N7 share completion IP budget.
    env[1][0] += timedelta(minutes=16)
    assert finish(env, "bad-token").status_code == 400
    request_reset(reset_env)


def test_reset_expiry_rechecked_after_postgres_lock_wait(reset_env, monkeypatch):
    from threading import Event
    from app.repositories.auth import AuthRepository
    env = reset_env[0]
    uid = verified(env)
    sessions = active_sessions(env)
    request_reset(reset_env)
    raw = reset_token(reset_env)
    entered, waiting, release = Event(), Event(), Event()
    original = AuthRepository.lock_user
    def observed(repository, user_id):
        waiting.set()
        return original(repository, user_id)
    monkeypatch.setattr(AuthRepository, "lock_user", observed)
    def holder():
        with Session(env[0]) as session:
            session.scalar(select(User).where(User.id == uid).with_for_update())
            entered.set()
            assert release.wait(10)
            session.commit()
    with ThreadPoolExecutor(max_workers=2) as workers:
        lock = workers.submit(holder)
        try:
            assert entered.wait(10)
            pending = workers.submit(env[2].complete, CredentialCompletion(token=raw, password=NEW_PASSWORD), "lock-expiry")
            assert waiting.wait(10)
            env[1][0] += timedelta(minutes=30)
        finally:
            release.set()
        lock.result()
        with pytest.raises(AuthError, match="CREDENTIAL_TOKEN_INVALID"):
            pending.result()
    with Session(env[0]) as fresh:
        assert fresh.get(CredentialToken, digest(raw)).consumed_at is None
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)
        assert all(row.revoked_at is None for row in fresh.scalars(select(AuthSession)))


def test_delivery_recovers_in_fresh_process_and_expired_ciphertext_scrubs_when_disabled(reset_env):
    import json, os, subprocess, sys
    env, _, dispatcher = reset_env
    verified(env)
    request_reset(reset_env)
    with Session(env[0]) as fresh:
        identifier = fresh.scalar(select(PasswordResetDelivery.id))
    dispatcher.claim(identifier)
    env[1][0] += timedelta(seconds=61)
    code = '''
import json,os
from datetime import datetime
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from app.config import Settings
from scripts.dev import validate_reset_target
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.password_reset_delivery import PasswordResetDispatcher
s=Settings(_env_file=None,environment="test",database_url=os.environ["B2_TEST_URL"],auth_delivery_encryption_key=SecretStr(os.environ["B2_TEST_KEY"]))
u=make_url(s.database_url)
assert (u.database,u.username)==("shelfcash_auth_test","shelfcash_auth_tester")
validate_reset_target(s)
engine=create_database_engine(s)
auth=AuthUseCases(engine,clock=lambda:datetime.fromisoformat(os.environ["B2_TEST_NOW"]))
class Sink:
    available=True
    def __call__(self,address,secret):
        assert address=="holder@example.test" and engine.pool.checkedout()==0
try:
    print(json.dumps(PasswordResetDispatcher(auth,s,Sink()).dispatch()))
finally:
    engine.dispose()
'''
    child_env = dict(os.environ, B2_TEST_URL=env[7].database_url,
        B2_TEST_KEY=env[7].auth_delivery_encryption_key.get_secret_value(), B2_TEST_NOW=env[1][0].isoformat())
    result = subprocess.run([sys.executable, "-c", code], env=child_env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["delivered"] == 1
    with Session(env[0]) as fresh:
        intent = fresh.get(PasswordResetDelivery, identifier)
        assert intent.status == "delivered" and intent.attempts == 2 and intent.ciphertext is None
    env[1][0] += timedelta(minutes=16)
    request_reset(reset_env)
    env[1][0] += timedelta(minutes=30)
    env[3].available = False
    assert dispatcher.dispatch()["delivered"] == 0
    with Session(env[0]) as fresh:
        assert all(row.ciphertext is None for row in fresh.scalars(select(PasswordResetDelivery)))


def test_concurrent_reset_requests_one_intent_no_password_or_session_change(reset_env):
    env, requests, _ = reset_env
    uid = verified(env)
    sessions = active_sessions(env)
    env[1][0] += timedelta(minutes=16)
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda i: requests.request(PublicEmailRequest(email=EMAIL), f"concurrent-{i}"), range(6)))
    assert all(result.next_action == "check_email" for result in results)
    assert_sessions_work(env, sessions)
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PasswordResetDelivery)) == 1
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)


def test_native_email_worker_dispatches_reset_using_fake_adapter_and_joins(reset_env):
    from threading import Event
    from fastapi.testclient import TestClient
    from app.main import create_app
    env, _, dispatcher = reset_env
    verified(env)
    request_reset(reset_env)
    sent = Event()
    env[3].sent = sent
    app = create_app(env[7].model_copy(update={"auth_email_delivery_enabled": True}))
    app.state.password_reset_dispatcher = dispatcher
    with TestClient(app):
        assert sent.wait(10)
    # Lifespan stop() joins the sole email thread before returning.
    import threading
    assert not any(thread.name == "email-verification" and thread.is_alive() for thread in threading.enumerate())
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(PasswordResetDelivery)).status == "delivered"


def test_concurrent_dispatch_claim_and_uncertain_recovery_are_bounded(reset_env):
    env, _, dispatcher = reset_env
    verified(env)
    sessions = active_sessions(env)
    request_reset(reset_env)
    with Session(env[0]) as fresh:
        identifier = fresh.scalar(select(PasswordResetDelivery.id))
    other = PasswordResetDispatcher(env[2], env[7], env[3])
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(queue.claim, identifier) for queue in (dispatcher, other)]
        claims = [future.result() for future in futures]
    assert sum(value is not None for value in claims) == 1
    attempts = [value for value in claims if value is not None]
    for _ in range(2):
        env[1][0] += timedelta(seconds=61)
        attempts.append(dispatcher.claim(identifier))
        assert attempts[-1] is not None and attempts[-1] != "cancelled"
    env[1][0] += timedelta(seconds=61)
    assert dispatcher.dispatch() == dict(delivered=0, failed=0, cancelled=1)
    for attempt in attempts: assert not dispatcher.settle(attempt, "delivered")
    assert_sessions_work(env, sessions)
    with Session(env[0]) as fresh:
        intent = fresh.get(PasswordResetDelivery, identifier)
        assert intent.attempts == 3 and intent.status == "failed" and intent.ciphertext is None
        assert verify_password(fresh.scalar(select(User)).password_hash, PASSWORD)


def test_reset_preserves_existing_store_membership_and_grants(reset_env):
    from uuid import uuid4
    from app.application.contracts.provisioning import ProvisionStoreCommand
    from app.application.use_cases.provisioning import AssistedProvisioning
    env = reset_env[0]
    uid = verified(env)
    receipt = AssistedProvisioning(env[0], env[7], clock=lambda: env[1][0]).provision(
        ProvisionStoreCommand(request_reference=str(uuid4()), evidence_reference="synthetic-existing-owner",
            email=EMAIL, display_name="Holder", existing_user_id=uid, store_name="Existing fixture Store"),
        "synthetic", env[7].auth_operator_key)
    with Session(env[0]) as session:
        membership = session.scalar(select(StoreMembership).where(StoreMembership.user_id == uid))
        membership_id = membership.id
        session.add(MembershipGrant(membership_id=membership_id, permission="menu.read"))
        session.commit()
    with Session(env[0]) as fresh:
        membership = fresh.get(StoreMembership, membership_id)
        before = (membership.store_id, membership.user_id, membership.role, membership.active, membership.authorization_revision)
    request_reset(reset_env)
    assert finish(env, reset_token(reset_env)).status_code == 200
    with Session(env[0]) as fresh:
        membership = fresh.get(StoreMembership, membership_id)
        assert (membership.store_id, membership.user_id, membership.role, membership.active, membership.authorization_revision) == before
        assert fresh.scalar(select(func.count()).select_from(Store)) == 1
        assert fresh.scalar(select(func.count()).select_from(StoreMembership)) == 1
        assert tuple(fresh.scalars(select(MembershipGrant.permission))) == ("menu.read",)
    response = post(env, "login", dict(email=EMAIL, password=NEW_PASSWORD))
    assert response.status_code == 200 and response.json()["data"]["accessible_store_count"] == 1
