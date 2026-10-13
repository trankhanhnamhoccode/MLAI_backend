"""B2 public RESET issuance; credential/session changes belong to existing N7."""
from datetime import timedelta
from uuid import uuid4
from app.application.contracts.auth import AuthError, PublicEmailAcceptance, PublicEmailRequest
from app.application.use_cases.auth import AuthUseCases
from app.config import Settings
from app.infrastructure.auth_crypto import digest, new_token
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.invitation_secret import InvitationSecret
from app.models.auth import CredentialToken
from app.models.password_reset import PasswordResetDelivery
from app.repositories.auth import AuthRepository
from app.repositories.password_reset import PasswordResetRepository


def delivery_identity(token_digest: str, identifier) -> str:
    return "password-reset/1:" + token_digest + ":" + str(identifier)


class PasswordReset:
    def __init__(self, auth: AuthUseCases, settings: Settings, delivery):
        self.auth, self.settings, self.delivery = auth, settings, delivery

    def request(self, request: PublicEmailRequest, ip: str, *, request_id: str | None = None) -> PublicEmailAcceptance:
        request = PublicEmailRequest.model_validate(request.model_dump())
        if not self.delivery.available:
            raise AuthError("EMAIL_DELIVERY_UNAVAILABLE", 503, 60)
        cipher = InvitationSecret(self.settings.auth_delivery_encryption_key)
        now = self.auth.clock()
        with auth_session(self.auth.engine) as session:
            error = self.auth._rate(session, "public-email-ip:" + ip, 20, now)
            email_limit = self.auth._rate(session, "public-email:" + request.email, 3, now) if error is None else None
            if error is None and email_limit is None:
                auth_repo, repo = AuthRepository(session), PasswordResetRepository(session)
                user = auth_repo.lock_user_by_email(request.email)
                account = auth_repo.lock_account(user.id) if user is not None else None
                now = self.auth.clock()
                if (user is not None and user.active and account is not None and account.verified_at is not None
                    and account.verification_reference and account.verified_email == user.email):
                    last = repo.latest_issue(user.id)
                    if last is None or now >= last + timedelta(seconds=60):
                        raw, identifier = new_token(), uuid4()
                        token_digest, expires = digest(raw), now + timedelta(minutes=30)
                        session.add(CredentialToken(digest=token_digest, user_id=user.id, revision=account.credential_revision,
                            purpose="RESET", issued_at=now, expires_at=expires))
                        session.flush()
                        session.add(PasswordResetDelivery(id=identifier, token_digest=token_digest, email=user.email,
                            proof_revision=account.proof_revision, status="queued", attempts=0, expires_at=expires,
                            ciphertext=cipher.seal(raw, delivery_identity(token_digest, identifier))))
                        session.flush()  # Preserve old token until the new encrypted intent is accepted.
                        repo.invalidate(user.id, now, except_digest=token_digest)
                        self.auth._audit(session, "PASSWORD_RESET_ISSUED", user.id, now,
                            evidence_reference=f"RESET;delivery={identifier};proof_revision={account.proof_revision};credential_revision={account.credential_revision};actor=unverified_request",
                            request_reference=(request_id + ":reset-issue") if request_id else None)
            session.commit()
        if error is not None:
            raise error
        return PublicEmailAcceptance()
