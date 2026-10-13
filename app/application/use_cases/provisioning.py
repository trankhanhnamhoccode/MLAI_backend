"""Assisted commands with deployment-operator authorization and audited proof."""
from collections.abc import Callable
from datetime import timedelta
import hmac
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import Engine
from app.repositories.auth import AuthRepository

from app.application.contracts.auth import AuthError
from app.application.contracts.provisioning import (
    DeliveryReceipt, IssueCredentialCommand, ProvisionReceipt,
    ProvisionStoreCommand, VerifiedAccountCommand,
)
from app.application.use_cases.auth import now_utc
from app.config import Settings
from app.infrastructure.auth_crypto import digest, new_token
from app.infrastructure.database.auth_session import auth_session
from app.models import Store, StoreMembership, User
from app.models.auth import AuthAccount, AuthAudit, CredentialToken


class AssistedProvisioning:
    def __init__(self, engine: Engine, settings: Settings, clock=now_utc):
        if not isinstance(engine, Engine):
            raise TypeError("Provisioning requires an owned Engine")
        self.engine, self.settings, self.clock = engine, settings, clock

    def _operator(self, operator_id: str, key: SecretStr):
        expected = self.settings.auth_operator_key
        if not expected or not self.settings.auth_operator_id or operator_id != self.settings.auth_operator_id or not hmac.compare_digest(key.get_secret_value().encode(), expected.get_secret_value().encode()):
            raise AuthError("OPERATOR_NOT_AUTHORIZED")
        return operator_id

    def provision(self, command: VerifiedAccountCommand, operator_id: str, key: SecretStr) -> ProvisionReceipt:
        operator = self._operator(operator_id, key)
        kind = "STORE_PROVISIONED" if isinstance(command, ProvisionStoreCommand) else "ACCOUNT_PROVISIONED"
        cls = ProvisionStoreCommand if kind == "STORE_PROVISIONED" else VerifiedAccountCommand
        command = cls.model_validate(command.model_dump())
        fingerprint = digest(command.model_dump_json() + kind + operator)
        with auth_session(self.engine) as s:
            # Transaction advisory lock serializes retries without speculative receipts.
            old = AuthRepository(s).lock_operator_request(command.request_reference, int(digest(command.request_reference)[:15], 16))
            if old:
                if old.request_digest != fingerprint or old.kind != kind:
                    raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
                return ProvisionReceipt(user_id=old.user_id, store_id=old.store_id, audit_id=old.id)
            if command.existing_user_id is None:
                if AuthRepository(s).user_id_by_email(command.email):
                    raise AuthError("EXISTING_ACCOUNT_REQUIRES_VERIFICATION", 409)
                user = User(id=uuid4(), email=command.email, display_name=command.display_name, password_hash="!UNSET")
                s.add(user)
                s.flush()
                account = AuthAccount(user_id=user.id, credential_revision=1, credential_ready=False,
                    verified_at=self.clock(), verified_email=command.email, verification_reference=command.evidence_reference)
                s.add(account)
            else:
                user = AuthRepository(s).lock_user(command.existing_user_id)
                if not user or not user.active or user.email != command.email:
                    raise AuthError("IDENTITY_VERIFICATION_MISMATCH", 409)
                account = s.get(AuthAccount, user.id)
                if account is None:
                    # Existing S1 opaque hashes never become usable by inference.
                    account = AuthAccount(user_id=user.id, credential_revision=1, credential_ready=False,
                        verified_at=self.clock(), verified_email=command.email, verification_reference=command.evidence_reference)
                    s.add(account)
                else:
                    account.proof_revision += 1
                    account.verified_at, account.verification_reference = self.clock(), command.evidence_reference
                    account.verified_email = command.email
            store_id = None
            if isinstance(command, ProvisionStoreCommand):
                store = Store(id=uuid4(), name=command.store_name, timezone=command.timezone, currency=command.currency)
                s.add(store)
                s.flush()
                store_id = store.id
                member = StoreMembership(id=uuid4(), user_id=user.id, store_id=store.id, role="OWNER")
                s.add(member)
                s.flush()
                from app.application.use_cases.staff import permission_event
                from app.domain.permissions import PERMISSIONS
                permission_event(s, member, actor=None, now=self.clock(), reason="Assisted Store provisioning",
                    before=(), before_version=None, after=tuple(sorted(PERMISSIONS)),
                    request_id=command.request_reference, source="ASSISTED_PROVISIONING", operator=operator)
            event = AuthAudit(id=uuid4(), kind=kind, user_id=user.id, store_id=store_id,
                operator_reference=operator, evidence_reference=command.evidence_reference,
                request_reference=command.request_reference, request_digest=fingerprint, occurred_at=self.clock())
            s.add(event)
            s.commit()
            return ProvisionReceipt(user_id=user.id, store_id=store_id, audit_id=event.id)

    def issue(self, command: IssueCredentialCommand, operator_id: str, key: SecretStr,
              deliver: Callable[[str, SecretStr], None]) -> DeliveryReceipt:
        """Delivery receives only the verified account address and in-memory secret.

        No token recovery API. Delivery/commit uncertainty requires a NEW issuance;
        SMTP is not atomic with PostgreSQL. Failures invalidate this revision.
        """
        operator = self._operator(operator_id, key)
        command = IssueCredentialCommand.model_validate(command.model_dump())
        now, raw = self.clock(), new_token()
        with auth_session(self.engine) as s:
            user = AuthRepository(s).lock_user(command.user_id)
            account = s.get(AuthAccount, command.user_id)
            if not user or not user.active or not account or user.email != command.verified_email:
                raise AuthError("IDENTITY_VERIFICATION_MISMATCH", 409)
            if (command.purpose == "SETUP") == account.credential_ready:
                raise AuthError("CREDENTIAL_PURPOSE_CONFLICT", 409)
            if AuthRepository(s).audit_by_reference(command.request_reference):
                raise AuthError("CREDENTIAL_ISSUANCE_REQUIRES_NEW_REFERENCE", 409)
            now = self.clock()
            account.verified_email, account.verified_at = command.verified_email, now
            account.proof_revision += 1
            account.verification_reference = command.evidence_reference
            AuthRepository(s).invalidate_user_tokens(user.id, now)
            s.add(CredentialToken(digest=digest(raw), user_id=user.id, revision=account.credential_revision,
                purpose=command.purpose, issued_at=now, expires_at=now+timedelta(minutes=30)))
            event = AuthAudit(id=uuid4(), kind="CREDENTIAL_ISSUED", user_id=user.id,
                operator_reference=operator, evidence_reference=command.evidence_reference,
                request_reference=command.request_reference, request_digest=digest(command.model_dump_json()), occurred_at=now)
            s.add(event)
            s.commit()
            event_id = event.id
        try:
            deliver(command.verified_email, SecretStr(raw))
        except Exception:
            with auth_session(self.engine) as s:
                AuthRepository(s).invalidate_token(digest(raw), self.clock())
                s.add(AuthAudit(id=uuid4(), kind="CREDENTIAL_DELIVERY_FAILED", user_id=command.user_id,
                    operator_reference=operator, request_reference=str(uuid4()), request_digest=digest(str(event_id)), occurred_at=self.clock()))
                s.commit()
            return DeliveryReceipt(audit_id=event_id, status="failed")
        with auth_session(self.engine) as s:
            s.add(AuthAudit(id=uuid4(), kind="CREDENTIAL_DELIVERED", user_id=command.user_id,
                operator_reference=operator, request_reference=str(uuid4()), request_digest=digest(str(event_id)), occurred_at=self.clock()))
            s.commit()
        return DeliveryReceipt(audit_id=event_id, status="delivered")
