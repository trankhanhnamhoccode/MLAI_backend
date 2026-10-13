"""B1 synthetic public flow, races, delivery faults and fresh-session evidence."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.application.contracts.auth import AuthError, CredentialCompletion, PublicEmailRequest, RegistrationRequest
from app.application.contracts.provisioning import VerifiedAccountCommand
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.email_verification import EmailVerification
from app.application.use_cases.email_verification_delivery import EmailVerificationDispatcher
from app.application.use_cases.provisioning import AssistedProvisioning
from app.infrastructure.auth_crypto import digest, verify_password
from app.infrastructure.database.engine import create_database_engine
from app.main import create_app
from app.models import User, Store, StoreMembership
from app.models.auth import AuthAccount, AuthAudit, AuthSession, CredentialToken, MembershipGrant
from app.models.email_verification import EmailVerificationToken, EmailVerificationDelivery

ORIGIN = "https://fe.example.test"
PASSWORD = "Synthetic holder password"
EMAIL = "holder@example.test"


class FakeDelivery:
    available = True

    def __init__(self, engine):
        self.engine, self.messages, self.fail = engine, [], False
        self.sent = None

    def __call__(self, address, secret):
        # Owned transaction/pool is released before any SMTP work.
        assert self.engine.pool.checkedout() == 0
        if self.fail:
            raise RuntimeError("SYNTHETIC-SECRET-PROVIDER-FAILURE")
        self.messages.append((address, secret.get_secret_value()))
        if self.sent is not None:
            self.sent.set()


@pytest.fixture
def env(database_settings):
    settings = database_settings.model_copy(update={"auth_allowed_origins": [ORIGIN],
        "auth_delivery_encryption_key": SecretStr(base64.b64encode(b"k" * 32).decode()),
        "auth_operator_id": "synthetic", "auth_operator_key": SecretStr("synthetic-key")})
    engine = create_database_engine(settings)
    clock = [datetime(2026, 10, 13, 2, tzinfo=timezone.utc)]
    auth = AuthUseCases(engine, clock=lambda: clock[0])
    transport = FakeDelivery(engine)
    use_cases = EmailVerification(auth, settings, transport)
    dispatcher = EmailVerificationDispatcher(auth, settings, transport)
    app = create_app(settings)
    app.state.auth, app.state.email_verification = auth, use_cases
    with TestClient(app, base_url="https://backend.example.test") as client:
        yield engine, clock, auth, transport, use_cases, dispatcher, client, settings
    engine.dispose()


def post(env, suffix, body):
    return env[6].post("/api/v1/auth/" + suffix, json=body, headers={"Origin": ORIGIN})


def signup(env, email=EMAIL, name="Original holder"):
    r = post(env, "register", dict(email=email, display_name=name))
    assert r.status_code == 202, r.text
    assert r.json()["data"] == dict(next_action="check_email", delivery={"status": "accepted"}, retry_after_seconds=60)
    assert "set-cookie" not in r.headers
    return r


def delivered_token(env):
    assert env[5].dispatch()["delivered"] == 1
    return env[3].messages[-1][1]


def complete(env, token, password=PASSWORD):
    return post(env, "email-verifications/complete", dict(token=token, password=password))


def test_public_signup_verify_login_empty_stores_and_no_authority(env):
    engine, clock, _, transport, _, _, client, _ = env
    signup(env, " HOLDER@Example.test ")
    with Session(engine) as fresh:
        user = fresh.scalar(select(User))
        uid = user.id
        account = fresh.get(AuthAccount, uid)
        assert user.password_hash == "!UNSET" and account.verified_at is None and not account.credential_ready
        for model in (Store, StoreMembership, MembershipGrant, AuthSession):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
        intent = fresh.scalar(select(EmailVerificationDelivery))
        assert intent.ciphertext and intent.status == "queued"
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 401
    raw = delivered_token(env)
    with Session(engine) as fresh:
        token = fresh.get(EmailVerificationToken, digest(raw))
        assert token.purpose == "EMAIL_VERIFY" and token.expires_at - token.issued_at == timedelta(minutes=30)
        assert fresh.scalar(select(EmailVerificationDelivery)).ciphertext is None
    r = complete(env, raw)
    assert r.status_code == 200 and r.json()["data"] == dict(next_action="login", completed_at="2026-10-13T02:00:00Z")
    assert "set-cookie" not in r.headers and raw not in r.text
    with Session(engine) as fresh:
        account = fresh.get(AuthAccount, uid)
        assert account.verified_at == clock[0] and account.verified_email == EMAIL and account.credential_revision == 2
        assert verify_password(fresh.get(User, uid).password_hash, PASSWORD)
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at == clock[0]
        assert fresh.scalar(select(EmailVerificationDelivery)).ciphertext is None
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind == "EMAIL_VERIFICATION_COMPLETED")) == 1
        audit = fresh.scalar(select(AuthAudit).where(AuthAudit.kind == "EMAIL_VERIFICATION_COMPLETED"))
        assert audit.request_reference == r.json()["meta"]["request_id"] + ":complete"
        assert "proof_revision=2;credential_revision=2;actor=holder" in audit.evidence_reference
        assert raw not in str((audit.evidence_reference, audit.request_digest, audit.request_reference))
        for model in (Store, StoreMembership, MembershipGrant, AuthSession):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
    assert complete(env, raw, "Different holder password").json()["error"]["code"] == "EMAIL_VERIFICATION_TOKEN_INVALID"
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 200
    assert client.get("/api/v1/auth/me").json()["data"]["accessible_store_count"] == 0
    assert client.get("/api/v1/stores").json()["data"]["items"] == []
    assert transport.messages[0][0] == EMAIL
    with Session(engine) as fresh:
        for model in (Store, StoreMembership, MembershipGrant):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
        assert fresh.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_existing_absent_unverified_verified_inactive_have_same_public_acceptance(env):
    engine, clock, _, _, _, _, _, settings = env
    signup(env, "unverified@example.test")
    signup(env, "inactive@example.test")
    with Session(engine) as session:
        session.scalar(select(User).where(User.email == "inactive@example.test")).active = False
        session.commit()
    AssistedProvisioning(engine, settings, clock=lambda: clock[0]).provision(
        VerifiedAccountCommand(request_reference=str(uuid4()), evidence_reference="synthetic-verified-proof",
            email="verified@example.test", display_name="Verified"), "synthetic", settings.auth_operator_key)
    public = []
    for email in ("absent@example.test", "unverified@example.test", "verified@example.test", "inactive@example.test"):
        for suffix, body in (("email-verifications/request", dict(email=email)),
                             ("register", dict(email=email, display_name="Requester"))):
            response = post(env, suffix, body)
            assert response.status_code == 202 and "set-cookie" not in response.headers
            assert response.headers["cache-control"] == "no-store"
            assert email not in response.text
            public.append((response.json()["data"], response.json()["error"]))
    assert all(value == public[0] for value in public)
    with Session(engine) as fresh:
        for model in (Store, StoreMembership, MembershipGrant, AuthSession):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("phase", ["register", "complete"])
def test_lost_commit_ack_retry_preserves_one_transition_and_holder_login(env, monkeypatch, phase):
    engine = env[0]
    raw = None
    if phase == "complete":
        signup(env)
        raw = delivered_token(env)
    original = Session.commit
    original_audit = env[2]._audit
    kind = "SELF_SERVICE_REGISTERED" if phase == "register" else "EMAIL_VERIFICATION_COMPLETED"
    def mark_transition(session, audit_kind, *args, **kwargs):
        if audit_kind == kind:
            session.info["b1_lost_ack_transition"] = True
        original_audit(session, audit_kind, *args, **kwargs)
    def lost_ack(session):
        owns_transition = session.info.get("b1_lost_ack_transition", False)
        original(session)
        if owns_transition:
            raise RuntimeError("SYNTHETIC-PRIVATE-ACK-LOSS")
    with monkeypatch.context() as faults:
        faults.setattr(env[2], "_audit", mark_transition)
        faults.setattr(Session, "commit", lost_ack)
        response = (post(env, "register", dict(email=EMAIL, display_name="Holder"))
                    if phase == "register" else complete(env, raw))
        assert response.status_code == 503 and "set-cookie" not in response.headers
        assert "SYNTHETIC-PRIVATE-ACK-LOSS" not in response.text
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User)) == 1
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind == kind)) == 1
    if phase == "register":
        signup(env, name="Retry must preserve holder")
        with Session(engine) as fresh:
            assert fresh.scalar(select(User)).display_name == "Holder"
            assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
        assert complete(env, delivered_token(env)).status_code == 200
    else:
        retry = complete(env, raw, "Different password on retry")
        assert retry.status_code == 400 and retry.json()["error"]["code"] == "EMAIL_VERIFICATION_TOKEN_INVALID"
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 200
    with Session(engine) as fresh:
        account = fresh.scalar(select(AuthAccount))
        assert account.proof_revision == 2 and account.credential_revision == 2
        assert verify_password(fresh.scalar(select(User)).password_hash, PASSWORD)
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind == "EMAIL_VERIFICATION_COMPLETED")) == 1
        for model in (Store, StoreMembership, MembershipGrant):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0


def test_verification_expiry_rechecked_after_real_postgres_lock_wait(env, monkeypatch):
    from threading import Event
    from app.repositories.auth import AuthRepository
    engine, clock, _, _, use_cases, _, _, _ = env
    signup(env)
    raw = delivered_token(env)
    with Session(engine) as fresh:
        uid = fresh.scalar(select(User.id))
    entered, waiting, release = Event(), Event(), Event()
    original = AuthRepository.lock_user
    def observed_wait(repository, user_id):
        waiting.set()
        return original(repository, user_id)
    monkeypatch.setattr(AuthRepository, "lock_user", observed_wait)
    def holder():
        with Session(engine) as session:
            session.scalar(select(User).where(User.id == uid).with_for_update())
            entered.set()
            assert release.wait(10)
            session.commit()
    with ThreadPoolExecutor(max_workers=2) as workers:
        locked = workers.submit(holder)
        try:
            assert entered.wait(10)
            pending = workers.submit(use_cases.complete, CredentialCompletion(token=raw, password=PASSWORD), "lock-expiry")
            assert waiting.wait(10)
            clock[0] += timedelta(minutes=30)
        finally:
            release.set()
        locked.result()
        with pytest.raises(AuthError, match="EMAIL_VERIFICATION_TOKEN_INVALID"):
            pending.result()
    with Session(engine) as fresh:
        account = fresh.get(AuthAccount, uid)
        assert account.verified_at is None and not account.credential_ready
        assert fresh.get(User, uid).password_hash == "!UNSET"
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at is None


def test_uncertain_delivery_claim_recovery_has_bounded_attempts(env):
    engine, clock, _, transport, _, dispatcher, _, _ = env
    signup(env)
    with Session(engine) as fresh:
        identifier = fresh.scalar(select(EmailVerificationDelivery.id))
    attempts = []
    for _ in range(3):
        attempts.append(dispatcher.claim(identifier))
        assert attempts[-1] is not None and attempts[-1] != "cancelled"
        assert dispatcher.claim(identifier) is None
        clock[0] += timedelta(seconds=61)
    assert dispatcher.dispatch() == dict(delivered=0, failed=0, cancelled=1)
    assert not transport.messages
    for attempt in attempts:
        assert not dispatcher.settle(attempt, "delivered")
    with Session(engine) as fresh:
        intent = fresh.get(EmailVerificationDelivery, identifier)
        assert intent.attempts == 3 and intent.status == "failed" and intent.ciphertext is None
        assert intent.error_code == "TOKEN_UNAVAILABLE"
        assert fresh.scalar(select(AuthAccount)).verified_at is None


def test_collisions_cookie_target_inactive_verified_assisted_and_absent_resend(env):
    engine, clock, auth, _, use_cases, _, client, settings = env
    signup(env)
    raw = delivered_token(env)
    assert signup(env, name="Attacker name").status_code == 202
    with Session(engine) as fresh:
        assert fresh.scalar(select(User)).display_name == "Original holder"
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
    assert complete(env, raw).status_code == 200
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 200
    # Existing requester cookie is irrelevant to target resolution.
    signup(env, "second@example.test", "Second")
    with Session(engine) as fresh:
        before = fresh.scalar(select(User.password_hash).where(User.email == EMAIL))
    signup(env, name="Takeover")
    assert post(env, "email-verifications/request", dict(email="absent@example.test")).status_code == 202
    assisted = AssistedProvisioning(engine, settings, clock=lambda: clock[0]).provision(
        VerifiedAccountCommand(request_reference=str(uuid4()), evidence_reference="verified-assisted-proof",
            email="assisted@example.test", display_name="Assisted"), "synthetic", settings.auth_operator_key)
    signup(env, "assisted@example.test", "Attacker")
    signup(env, "inactive@example.test")
    with Session(engine) as s:
        inactive = s.scalar(select(User).where(User.email == "inactive@example.test"))
        inactive.active = False
        s.commit()
    clock[0] += timedelta(seconds=61)
    signup(env, "inactive@example.test", "Reactivate")
    with Session(engine) as fresh:
        assert fresh.scalar(select(User.password_hash).where(User.email == EMAIL)) == before
        assert fresh.get(AuthAccount, assisted.user_id).verification_reference == "verified-assisted-proof"
        assert fresh.scalar(select(User).where(User.email == "assisted@example.test")).display_name == "Assisted"
        assert not fresh.scalar(select(User).where(User.email == "inactive@example.test")).active
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken).where(EmailVerificationToken.email == "assisted@example.test")) == 0
        assert fresh.scalar(select(func.count()).select_from(User).where(User.email == "absent@example.test")) == 0


def test_stored_identity_without_auth_proof_keeps_name_and_opaque_hash_until_holder_complete(env):
    engine = env[0]
    with Session(engine) as s:
        user = User(email=EMAIL, display_name="Stored identity", password_hash="opaque-unusable-hash")
        s.add(user)
        s.commit()
        uid = user.id
    signup(env, name="Attacker supplied name")
    with Session(engine) as fresh:
        assert fresh.get(User, uid).display_name == "Stored identity"
        assert fresh.get(User, uid).password_hash == "opaque-unusable-hash"
        assert fresh.get(AuthAccount, uid).verified_at is None
    assert complete(env, delivered_token(env)).status_code == 200


def test_concurrent_signup_and_completion_single_transition(env):
    engine, _, _, _, use_cases, _, _, _ = env
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda i: use_cases.request(RegistrationRequest(email=EMAIL, display_name=f"Name {i}"), f"ip-{i}"), range(6)))
    assert all(r.next_action == "check_email" for r in results)
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User)) == 1
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
    raw = delivered_token(env)
    def consume(i):
        try:
            return use_cases.complete(CredentialCompletion(token=raw, password=PASSWORD), f"complete-{i}").next_action
        except AuthError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(consume, range(2))) == ["EMAIL_VERIFICATION_TOKEN_INVALID", "login"]
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind == "EMAIL_VERIFICATION_COMPLETED")) == 1


def test_resend_cooldown_account_limit_and_expiry(env):
    engine, clock, _, _, use_cases, dispatcher, _, _ = env
    signup(env)
    old = delivered_token(env)
    post(env, "email-verifications/request", dict(email=EMAIL))
    clock[0] += timedelta(seconds=60)
    post(env, "email-verifications/request", dict(email=EMAIL))
    current = delivered_token(env)
    assert current != old and complete(env, old).status_code == 400
    clock[0] += timedelta(seconds=61)
    # Fourth request is generically accepted but makes no issuance.
    assert post(env, "email-verifications/request", dict(email=EMAIL)).status_code == 202
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 2
    clock[0] += timedelta(minutes=30)
    for raw in (current, "invalid-token"):
        r = complete(env, raw)
        assert r.status_code == 400 and r.json()["error"]["code"] == "EMAIL_VERIFICATION_TOKEN_INVALID"
    dispatcher.dispatch()


@pytest.mark.parametrize("change", ["credential", "proof", "email", "inactive", "assisted"])
def test_stale_binding_never_overwrites_credential(env, change):
    engine, clock, _, _, _, _, _, settings = env
    signup(env)
    raw = delivered_token(env)
    with Session(engine) as s:
        user = s.scalar(select(User))
        uid = user.id
        account = s.get(AuthAccount, uid)
        if change == "credential": account.credential_revision += 1
        elif change == "proof": account.proof_revision += 1
        elif change == "email": user.email = "changed@example.test"
        elif change == "inactive": user.active = False
        s.commit()
    if change == "assisted":
        AssistedProvisioning(engine, settings, clock=lambda: clock[0]).provision(
            VerifiedAccountCommand(request_reference=str(uuid4()), evidence_reference="new-proof", email=EMAIL,
                display_name="No overwrite", existing_user_id=uid), "synthetic", settings.auth_operator_key)
    assert complete(env, raw).status_code == 400
    with Session(engine) as fresh:
        assert fresh.get(User, uid).password_hash == "!UNSET"
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at is None


def test_atomic_failure_completion_and_acceptance(env, monkeypatch):
    engine, _, auth, _, _, _, _, _ = env
    original = auth._audit
    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC-INJECTED-FAULT")
    monkeypatch.setattr(auth, "_audit", fail)
    assert post(env, "register", dict(email=EMAIL, display_name="Holder")).status_code == 503
    with Session(engine) as fresh:
        for model in (User, AuthAccount, EmailVerificationToken, EmailVerificationDelivery):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
    monkeypatch.setattr(auth, "_audit", original)
    signup(env)
    raw = delivered_token(env)
    monkeypatch.setattr(auth, "_audit", fail)
    assert complete(env, raw).status_code == 503
    with Session(engine) as fresh:
        user = fresh.scalar(select(User))
        assert user.password_hash == "!UNSET" and fresh.get(AuthAccount, user.id).verified_at is None
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at is None
    env[1][0] += timedelta(seconds=60)
    assert post(env, "email-verifications/request", dict(email=EMAIL)).status_code == 503
    with Session(engine) as fresh:
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at is None
        assert fresh.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1
    monkeypatch.setattr(auth, "_audit", original)
    assert complete(env, raw).status_code == 200


def test_delivery_failure_recovery_uncertainty_and_late_mail(env, caplog):
    engine, clock, auth, transport, use_cases, dispatcher, _, settings = env
    signup(env)
    with Session(engine) as fresh:
        identifier = fresh.scalar(select(EmailVerificationDelivery.id))
    attempt = dispatcher.claim(identifier)
    from app.infrastructure.invitation_secret import InvitationSecret
    # SMTP succeeded but process died before recording its outcome.
    uncertain_secret = InvitationSecret(settings.auth_delivery_encryption_key).open(attempt.ciphertext, attempt.identity)
    transport(attempt.address, uncertain_secret)
    restarted = EmailVerificationDispatcher(auth, settings, transport)
    assert restarted.dispatch()["delivered"] == 0
    clock[0] += timedelta(seconds=61)
    assert restarted.dispatch()["delivered"] == 1
    assert len(transport.messages) == 2 and transport.messages[0] == transport.messages[1]
    old = transport.messages[-1][1]
    clock[0] += timedelta(seconds=60)
    post(env, "email-verifications/request", dict(email=EMAIL))
    transport.fail = True
    assert restarted.dispatch()["failed"] == 1
    assert "SYNTHETIC-SECRET-PROVIDER-FAILURE" not in caplog.text
    with Session(engine) as fresh:
        user = fresh.scalar(select(User))
        assert fresh.get(AuthAccount, user.id).verified_at is None
        failed = fresh.scalar(select(EmailVerificationDelivery).where(EmailVerificationDelivery.status == "failed"))
        assert failed.ciphertext is None and failed.error_code == "EMAIL_DELIVERY_FAILED"
    assert complete(env, old).status_code == 400
    transport.fail = False
    clock[0] += timedelta(seconds=61)
    post(env, "email-verifications/request", dict(email=EMAIL))
    latest = delivered_token(env)
    assert not restarted.settle(attempt, "delivered")
    assert complete(env, latest).status_code == 200


def test_uniform_service_disabled_no_side_effects_and_completion_still_works(env):
    engine, clock, _, transport, _, _, _, _ = env
    signup(env)
    raw = delivered_token(env)
    transport.available = False
    for email in (EMAIL, "absent@example.test", "inactive@example.test", "assisted@example.test"):
        for suffix, body in (("register", dict(email=email, display_name="Holder")), ("email-verifications/request", dict(email=email))):
            r = post(env, suffix, body)
            assert r.status_code == 503 and r.headers["retry-after"] == "60"
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User)) == 1
        assert fresh.get(EmailVerificationToken, digest(raw)).consumed_at is None
    assert complete(env, raw).status_code == 200


def test_ip_limit_concurrent_account_budget_and_completion_no_permanent_lock(env):
    engine, clock, _, _, use_cases, _, _, _ = env
    for i in range(20):
        use_cases.request(PublicEmailRequest(email=f"absent-{i}@example.test"), "same-ip")
    with pytest.raises(AuthError, match="RATE_LIMITED"):
        use_cases.request(RegistrationRequest(email=EMAIL, display_name="Holder"), "same-ip")
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(User)) == 0
    for i in range(10):
        with pytest.raises(AuthError, match="EMAIL_VERIFICATION_TOKEN_INVALID"):
            use_cases.complete(CredentialCompletion(token="bad", password=PASSWORD), "limited")
    with pytest.raises(AuthError, match="RATE_LIMITED"):
        use_cases.complete(CredentialCompletion(token="bad", password=PASSWORD), "limited")
    clock[0] += timedelta(minutes=16)
    with pytest.raises(AuthError, match="EMAIL_VERIFICATION_TOKEN_INVALID"):
        use_cases.complete(CredentialCompletion(token="bad", password=PASSWORD), "limited")


def test_verification_invalidates_assisted_tokens_and_sessions_atomically(env):
    engine, clock, _, _, _, _, _, _ = env
    signup(env)
    raw = delivered_token(env)
    with Session(engine) as s:
        uid = s.scalar(select(User.id))
        for purpose in ("SETUP", "RESET"):
            s.add(CredentialToken(digest=digest("synthetic-" + purpose), user_id=uid, revision=1, purpose=purpose,
                issued_at=clock[0], expires_at=clock[0] + timedelta(minutes=30)))
        s.add(AuthSession(digest=digest("synthetic-session"), user_id=uid, credential_revision=1,
            csrf_token="synthetic-csrf", remember_me=False, issued_at=clock[0],
            idle_expires_at=clock[0] + timedelta(minutes=30), absolute_expires_at=clock[0] + timedelta(hours=8)))
        s.commit()
    assert post(env, "credentials/complete", dict(token=raw, password=PASSWORD)).status_code == 400
    assert complete(env, "synthetic-SETUP").status_code == 400
    assert complete(env, raw).status_code == 200
    with Session(engine) as fresh:
        assert all(t.consumed_at == clock[0] for t in fresh.scalars(select(CredentialToken)))
        assert fresh.scalar(select(AuthSession)).revoked_at == clock[0]
    assert post(env, "credentials/complete", dict(token="synthetic-SETUP", password="Different holder password")).status_code == 400


def test_new_verified_invitee_still_needs_separate_acceptance(env):
    from app.application.contracts.provisioning import ProvisionStoreCommand, IssueCredentialCommand
    from app.application.use_cases.staff import StaffUseCases
    engine, clock, auth, _, _, _, client, settings = env
    provisioning = AssistedProvisioning(engine, settings, clock=lambda: clock[0])
    owner = provisioning.provision(ProvisionStoreCommand(request_reference=str(uuid4()), evidence_reference="synthetic-owner",
        email="owner@example.test", display_name="Owner", store_name="Fixture Store"), "synthetic", settings.auth_operator_key)
    holder = []
    provisioning.issue(IssueCredentialCommand(request_reference=str(uuid4()), evidence_reference="synthetic-owner",
        verified_email="owner@example.test", user_id=owner.user_id, purpose="SETUP"),
        "synthetic", settings.auth_operator_key, lambda address, secret: holder.append(secret.get_secret_value()))
    auth.complete(CredentialCompletion(token=holder[0], password=PASSWORD), "owner-setup")
    owner_context = post(env, "login", dict(email="owner@example.test", password=PASSWORD)).json()["data"]
    client.app.state.staff = StaffUseCases(auth, settings)
    r = client.post(f"/api/v1/stores/{owner.store_id}/staff-invitations", headers={"Origin": ORIGIN,
        "X-CSRF-Token": owner_context["session"]["csrf_token"], "Idempotency-Key": str(uuid4())},
        json=dict(email=EMAIL, grants=["menu.read"], permission_catalog_version="permissions-v3", reason="Invite fixture holder"))
    assert r.status_code == 201, r.text
    invitation_id = r.json()["data"]["invitation"]["invitation_id"]
    signup(env)
    raw = delivered_token(env)
    assert complete(env, raw).status_code == 200
    assert post(env, "login", dict(email=EMAIL, password=PASSWORD)).status_code == 200
    assert client.get("/api/v1/stores").json()["data"]["items"] == []
    from app.models.staff import StaffInvitation
    from uuid import UUID
    with Session(engine) as fresh:
        uid = fresh.scalar(select(User.id).where(User.email == EMAIL))
        assert fresh.get(StaffInvitation, UUID(invitation_id)).status == "pending"
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(StoreMembership.user_id == uid)) == 0


def test_pending_delivery_recovered_in_fresh_process(env):
    import json
    import os
    import subprocess
    import sys
    engine, clock, _, _, _, dispatcher, _, settings = env
    signup(env)
    with Session(engine) as fresh:
        identifier = fresh.scalar(select(EmailVerificationDelivery.id))
    dispatcher.claim(identifier)  # Simulate process dying after durable claim.
    clock[0] += timedelta(seconds=61)
    code = '''
import json, os
from datetime import datetime
from pydantic import SecretStr
from app.config import Settings
from scripts.dev import validate_reset_target
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.auth_crypto import digest
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.email_verification_delivery import EmailVerificationDispatcher
s = Settings(_env_file=None, environment="test", database_url=os.environ["B1_TEST_URL"], auth_delivery_encryption_key=SecretStr(os.environ["B1_TEST_KEY"]))
validate_reset_target(s)
engine = create_database_engine(s)
auth = AuthUseCases(engine, clock=lambda: datetime.fromisoformat(os.environ["B1_TEST_NOW"]))
class Sink:
    available = True
    def __call__(self, address, secret):
        assert address == "holder@example.test" and engine.pool.checkedout() == 0
sink = Sink()
try:
    print(json.dumps(EmailVerificationDispatcher(auth, s, sink).dispatch()))
finally:
    engine.dispose()
'''
    child_env = dict(os.environ, B1_TEST_URL=settings.database_url,
        B1_TEST_KEY=settings.auth_delivery_encryption_key.get_secret_value(), B1_TEST_NOW=clock[0].isoformat())
    result = subprocess.run([sys.executable, "-c", code], env=child_env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["delivered"] == 1
    with Session(engine) as fresh:
        intent = fresh.get(EmailVerificationDelivery, identifier)
        assert intent.status == "delivered" and intent.attempts == 2 and intent.ciphertext is None


def test_concurrent_ip_limit_commits_exact_budget(env):
    use_cases = env[4]
    def request(i):
        try:
            use_cases.request(PublicEmailRequest(email=f"absent-{i}@example.test"), "shared-concurrent-ip")
            return 202
        except AuthError as error:
            return error.status
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(request, range(24)))
    assert results.count(202) == 20 and results.count(429) == 4


def test_native_lifespan_dispatches_to_fake_transport_and_stops_thread(env):
    from threading import Event
    engine, _, auth, transport, use_cases, dispatcher, _, settings = env
    transport.sent = Event()
    app = create_app(settings.model_copy(update={"auth_email_delivery_enabled": True}))
    app.state.auth, app.state.email_verification = auth, use_cases
    app.state.email_verification_dispatcher = dispatcher
    with TestClient(app, base_url="https://backend.example.test") as client:
        r = client.post("/api/v1/auth/register", json=dict(email=EMAIL, display_name="Holder"), headers={"Origin": ORIGIN})
        assert r.status_code == 202
        assert transport.sent.wait(timeout=5)
    # Lifespan stopped and joined the worker before checking its committed outcome.
    with Session(engine) as fresh:
        assert fresh.scalar(select(EmailVerificationDelivery)).status == "delivered"
        assert fresh.scalar(select(AuthAccount)).verified_at is None


def test_expired_pending_secret_scrubbed_even_when_email_service_unavailable(env):
    engine, clock, _, transport, _, dispatcher, _, _ = env
    signup(env)
    with Session(engine) as fresh:
        identifier = fresh.scalar(select(EmailVerificationDelivery.id))
        assert fresh.get(EmailVerificationDelivery, identifier).ciphertext is not None
    clock[0] += timedelta(minutes=30)
    transport.available = False
    dispatcher.dispatch()
    with Session(engine) as fresh:
        intent = fresh.get(EmailVerificationDelivery, identifier)
        assert intent.ciphertext is None and intent.status == "failed" and intent.error_code == "TOKEN_EXPIRED"
        assert fresh.scalar(select(AuthAccount)).verified_at is None
