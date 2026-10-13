"""B1 public signup: email control proves identity, never Store authority."""
from datetime import timedelta
from uuid import uuid4
from app.application.contracts.auth import (
    AuthError, CompletedCredential, CredentialCompletion, PublicEmailAcceptance,
    PublicEmailRequest, RegistrationRequest,
)
from app.application.use_cases.auth import AuthUseCases
from app.infrastructure.auth_crypto import HASHER, digest, new_token
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.invitation_secret import InvitationSecret
from app.config import Settings
from app.models.auth import AuthAccount
from app.models.email_verification import EmailVerificationToken, EmailVerificationDelivery
from app.repositories.auth import AuthRepository
from app.repositories.email_verification import EmailVerificationRepository


def delivery_identity(token_digest: str, attempt_id) -> str:
    return "email-verify/1:" + token_digest + ":" + str(attempt_id)


class EmailVerification:
    def __init__(self, auth: AuthUseCases, settings: Settings, delivery):
        self.auth, self.settings, self.delivery = auth, settings, delivery

    def request(self, request: PublicEmailRequest, ip: str, *, request_id: str | None = None) -> PublicEmailAcceptance:
        cls = RegistrationRequest if isinstance(request, RegistrationRequest) else PublicEmailRequest
        request = cls.model_validate(request.model_dump())
        # Capability is service-wide, checked without querying any account.
        if not self.delivery.available:
            raise AuthError("EMAIL_DELIVERY_UNAVAILABLE", 503, 60)
        cipher = InvitationSecret(self.settings.auth_delivery_encryption_key)
        now = self.auth.clock()
        error = None
        with auth_session(self.auth.engine) as s:
            error = self.auth._rate(s, "public-email-ip:" + ip, 20, now)
            email_limit = self.auth._rate(s, "public-email:" + request.email, 3, now) if error is None else None
            if error is None and email_limit is None:
                repo = EmailVerificationRepository(s)
                repo.lock_email(request.email)
                if isinstance(request, RegistrationRequest):
                    created = repo.create_unset_user(request.email, request.display_name)
                    if created is not None:
                        s.add(AuthAccount(user_id=created, credential_revision=1, credential_ready=False,
                            proof_revision=1, verified_at=None, verified_email=None, verification_reference=None))
                        s.flush()
                        self.auth._audit(s, "SELF_SERVICE_REGISTERED", created, now,
                            evidence_reference="EMAIL_VERIFY;proof_revision=1;credential_revision=1;actor=unverified_request",
                            request_reference=(request_id + ":register") if request_id else None)
                user = AuthRepository(s).lock_user_by_email(request.email)
                account = AuthRepository(s).lock_account(user.id) if user is not None else None
                if user is not None and user.active and account is None:
                    # Stored S1 identity/opaque hash is not an assisted verified proof.
                    # Preserve that identity and name; only its actual mailbox holder
                    # can establish a usable credential through completion.
                    account = AuthAccount(user_id=user.id, credential_revision=1, credential_ready=False,
                        proof_revision=1, verified_at=None, verified_email=None, verification_reference=None)
                    s.add(account)
                    s.flush()
                now = self.auth.clock()
                if user is not None and user.active and account is not None and account.verified_at is None:
                    last = repo.latest_issue(user.id)
                    if last is None or now >= last + timedelta(seconds=60):
                        raw, attempt_id = new_token(), uuid4()
                        token_digest = digest(raw)
                        expiry = now + timedelta(minutes=30)
                        s.add(EmailVerificationToken(digest=token_digest, user_id=user.id, email=user.email,
                            purpose="EMAIL_VERIFY", proof_revision=account.proof_revision,
                            credential_revision=account.credential_revision, issued_at=now, expires_at=expiry))
                        s.flush()
                        s.add(EmailVerificationDelivery(id=attempt_id, token_digest=token_digest, status="queued",
                            attempts=0, ciphertext=cipher.seal(raw, delivery_identity(token_digest, attempt_id)), expires_at=expiry))
                        s.flush()  # New durable intent accepted before superseding old tokens.
                        repo.invalidate(user.id, now, except_digest=token_digest)
                        self.auth._audit(s, "EMAIL_VERIFICATION_ISSUED", user.id, now,
                            evidence_reference=f"EMAIL_VERIFY;delivery={attempt_id};proof_revision={account.proof_revision};credential_revision={account.credential_revision};actor=unverified_request",
                            request_reference=(request_id + ":issue") if request_id else None)
            s.commit()
        if error is not None:
            raise error
        return PublicEmailAcceptance()

    def complete(self, request: CredentialCompletion, ip: str, *, request_id: str | None = None) -> CompletedCredential:
        request = CredentialCompletion.model_validate(request.model_dump())
        with auth_session(self.auth.engine) as s:
            error = self.auth._rate(s, "credential-ip:" + ip, 10, self.auth.clock())
            s.commit()
        if error is not None:
            raise error
        with auth_session(self.auth.engine) as s:
            repo = EmailVerificationRepository(s)
            uid = repo.token_user(digest(request.token))
            user = AuthRepository(s).lock_user(uid) if uid else None
            account = AuthRepository(s).lock_account(uid) if uid else None
            token = repo.lock_token(digest(request.token))
            delivery_id = repo.delivery_id(token.digest) if token is not None else None
            now = self.auth.clock()
            if (user is None or not user.active or account is None or token is None or delivery_id is None
                or token.purpose != "EMAIL_VERIFY" or token.consumed_at is not None or now >= token.expires_at
                or token.email != user.email or account.verified_at is not None
                or account.proof_revision != token.proof_revision
                or account.credential_revision != token.credential_revision):
                raise AuthError("EMAIL_VERIFICATION_TOKEN_INVALID", 400)
            user.password_hash = HASHER.hash(request.password)
            account.verified_at, account.verified_email = now, user.email
            account.verification_reference = "email-verification-delivery:" + str(delivery_id)
            account.proof_revision += 1
            account.credential_revision += 1
            account.credential_ready = True
            token.consumed_at = now
            repo.invalidate(uid, now)
            AuthRepository(s).invalidate_user_tokens(uid, now)
            AuthRepository(s).revoke_user_sessions(uid, now)
            self.auth._audit(s, "EMAIL_VERIFICATION_COMPLETED", uid, now,
                evidence_reference=f"EMAIL_VERIFY;delivery={delivery_id};proof_revision={account.proof_revision};credential_revision={account.credential_revision};actor=holder",
                request_reference=(request_id + ":complete") if request_id else None)
            s.commit()
        return CompletedCredential(completed_at=now)
