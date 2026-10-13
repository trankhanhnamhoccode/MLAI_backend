"""RESET queue using the same encrypted, bounded local dispatch loop as B1."""
from datetime import timedelta
from uuid import uuid4
from app.application.use_cases.durable_delivery import DeliveryAttempt, dispatch
from app.application.use_cases.password_reset import delivery_identity
from app.infrastructure.database.auth_session import auth_session
from app.repositories.auth import AuthRepository
from app.repositories.password_reset import PasswordResetRepository


class PasswordResetDispatcher:
    def __init__(self, auth, settings, transport):
        self.auth, self.settings, self.transport = auth, settings, transport

    def dispatch(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid dispatch limit")
        if not self.transport.available:
            self.expire(limit)
            return dict(delivered=0, failed=0, cancelled=0)
        return dispatch(self, self.settings.auth_delivery_encryption_key, self.transport, limit=limit)

    def _lock(self, session, identifier):
        repo, auth_repo = PasswordResetRepository(session), AuthRepository(session)
        observed = repo.delivery(identifier)
        if observed is None:
            return None
        uid = auth_repo.token_user(observed.token_digest)
        user, account = auth_repo.lock_user(uid), auth_repo.lock_account(uid)
        token = auth_repo.lock_token(observed.token_digest)
        intent = repo.lock_delivery(observed.token_digest)
        return user, account, token, intent

    def expire(self, limit):
        with auth_session(self.auth.engine) as session:
            identifiers = PasswordResetRepository(session).expired(self.auth.clock(), limit)
        for identifier in identifiers:
            with auth_session(self.auth.engine) as session:
                rows = self._lock(session, identifier)
                if rows is None:
                    continue
                intent = rows[-1]
                if self.auth.clock() >= intent.expires_at:
                    intent.ciphertext = None
                    if intent.status == "queued":
                        intent.status, intent.error_code = "failed", "TOKEN_EXPIRED"
                session.commit()

    def pending(self, limit):
        with auth_session(self.auth.engine) as session:
            return PasswordResetRepository(session).pending(self.auth.clock(), limit)

    def claim(self, identifier):
        with auth_session(self.auth.engine) as session:
            rows = self._lock(session, identifier)
            if rows is None:
                return None
            user, account, token, intent = rows
            now = self.auth.clock()
            if intent.status != "queued" or (intent.claim is not None and now < intent.claim_expires_at):
                return None
            if (now >= intent.expires_at or token.consumed_at is not None or token.purpose != "RESET"
                or not user.active or account.verified_at is None or not account.verification_reference
                or intent.email != user.email or account.verified_email != user.email
                or token.revision != account.credential_revision or intent.proof_revision != account.proof_revision
                or intent.attempts >= 3):
                intent.status, intent.ciphertext, intent.error_code = "failed", None, "TOKEN_UNAVAILABLE"
                session.commit()
                return "cancelled"
            intent.claim, intent.claim_expires_at = uuid4(), now + timedelta(seconds=60)
            intent.attempts += 1
            attempt = DeliveryAttempt(identifier, intent.claim, intent.email, intent.ciphertext,
                delivery_identity(token.digest, identifier))
            session.commit()
            return attempt

    def settle(self, attempt, outcome):
        with auth_session(self.auth.engine) as session:
            rows = self._lock(session, attempt.identifier)
            if rows is None:
                return False
            intent = rows[-1]
            if intent.claim != attempt.claim or intent.status != "queued":
                return False
            intent.status, intent.ciphertext = outcome, None
            intent.error_code = "EMAIL_DELIVERY_FAILED" if outcome == "failed" else None
            self.auth._audit(session, "PASSWORD_RESET_DELIVERY_" + outcome.upper(), rows[0].id, self.auth.clock(),
                evidence_reference=f"RESET;delivery={intent.id};attempt={intent.attempts};actor=system")
            session.commit()
            return True
