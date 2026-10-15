"""Create/reuse a synthetic Staff in Local Test Store through invitation consent."""
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.contracts.auth import CredentialCompletion, LoginRequest
from app.application.contracts.provisioning import IssueCredentialCommand, VerifiedAccountCommand
from app.application.contracts.staff import AcceptInvitation, CreateInvitation
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.use_cases.staff import StaffUseCases
from app.domain.permissions import CATALOG_VERSION
from app.infrastructure.invitation_secret import InvitationSecret
from app.models import StoreMembership
from app.models.auth import AuthAccount
from scripts import local_runtime
from scripts.dev import inspect_database, require_head
from scripts.seed_local_owner import EVIDENCE, seed_owner

EMAIL = "staff.local@example.test"
OPERATOR = "synthetic-local-staff-tool"


def save_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def seed_staff(engine, settings, private: Path):
    owner = seed_owner(engine, settings, private / "test-owner.json")
    path = private / "test-staff.json"
    if not path.exists():
        save_new(path, {"email": EMAIL, "password": "Local!" + secrets.token_urlsafe(24)})
    credentials = json.loads(path.read_text(encoding="utf-8"))
    if credentials.get("email") != EMAIL:
        raise ValueError("Unexpected synthetic identity")
    login = LoginRequest(**credentials)
    key = SecretStr(secrets.token_urlsafe(32))
    configured = settings.model_copy(update={"auth_operator_id": OPERATOR, "auth_operator_key": key})
    # Validate encryption before accepting an invitation or queuing delivery.
    crypto = InvitationSecret(configured.auth_delivery_encryption_key)
    provisioning = AssistedProvisioning(engine, configured)
    account = provisioning.provision(VerifiedAccountCommand(
        request_reference="synthetic-local-staff-v1", evidence_reference=EVIDENCE,
        email=EMAIL, display_name="Local Test Staff",
    ), OPERATOR, key)
    auth = AuthUseCases(engine)
    with Session(engine) as fresh:
        ready = fresh.get(AuthAccount, account.user_id).credential_ready
    if not ready:
        delivered = []
        provisioning.issue(IssueCredentialCommand(
            user_id=account.user_id, purpose="SETUP", verified_email=EMAIL,
            request_reference=str(uuid4()), evidence_reference=EVIDENCE,
        ), OPERATOR, key, lambda address, token: delivered.append(token.get_secret_value()))
        auth.complete(CredentialCompletion(token=delivered[0], password=login.password), "local-staff-tool")
    context, token = auth.login(login, "local-staff-tool")
    try:
        with Session(engine) as fresh:
            member = fresh.scalar(select(StoreMembership).where(
                StoreMembership.user_id == account.user_id, StoreMembership.store_id == owner.store_id))
            exists = member is not None
        if not exists:
            owner_login = LoginRequest(**json.loads((private / "test-owner.json").read_text(encoding="utf-8")))
            owner_context, owner_token = auth.login(owner_login, "local-staff-tool")
            staff = StaffUseCases(auth, configured)
            try:
                created = staff.create(owner_token, owner.store_id, CreateInvitation(
                    email=EMAIL, grants=("menu.read",), permission_catalog_version=CATALOG_VERSION,
                    reason="User-requested synthetic local Staff; initial menu.read only",
                ), "synthetic-local-staff-invitation-v1", owner_context.session.csrf_token, str(uuid4()))
                invitation = created.invitation
                delivery_path = private / f"test-staff-invitation-{invitation.invitation_id}.json"
                if not delivery_path.exists():
                    queue = InvitationDispatcher(engine, configured, auth.clock)
                    attempt = queue.claim(created.delivery.attempt_id)
                    if attempt is None or attempt == "cancelled":
                        raise ValueError("Private invitation delivery unavailable; preserve state for recovery")
                    raw = crypto.open(attempt.ciphertext, attempt.identity).get_secret_value()
                    save_new(delivery_path, {"token": raw})
                    if not queue.settle(attempt, "delivered"):
                        raise ValueError("Private invitation delivery changed")
                raw = json.loads(delivery_path.read_text(encoding="utf-8"))["token"]
                staff.accept(token, invitation.invitation_id, AcceptInvitation(token=raw, accept=True),
                    "synthetic-local-staff-accept-v1", invitation.version, context.session.csrf_token,
                    "local-staff-tool", str(uuid4()))
            finally:
                auth.logout(owner_token, owner_context.session.csrf_token)
        current = auth.store_context(token, owner.store_id)
        if current.membership.role != "STAFF":
            raise ValueError("Unexpected synthetic membership role")
        return current
    finally:
        auth.logout(token, context.session.csrf_token)


def main() -> int:
    engine = None
    try:
        settings, _ = local_runtime.configuration()
        engine = local_runtime.engine(settings.database_url)
        with engine.connect() as connection:
            local_runtime.guard(connection, local_runtime.DB, local_runtime.RUNTIME)
        require_head(inspect_database(settings))
        staff = seed_staff(engine, settings, local_runtime.PRIVATE)
        print(f"Local Staff ready: {EMAIL}; Store: {staff.store_id}")
        print("Current permissions: " + ", ".join(staff.membership.effective_permissions))
        print("Login credentials: runtime/local/private/test-staff.json")
        return 0
    except Exception:
        print("Local Staff setup failed; preserve private files and check local configuration/state. No credentials logged.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
