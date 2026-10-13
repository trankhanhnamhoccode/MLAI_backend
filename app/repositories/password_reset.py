"""Concrete RESET intent queries; caller owns account fences and transactions."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import select, update, or_
from sqlalchemy.orm import Session
from app.models.auth import CredentialToken
from app.models.password_reset import PasswordResetDelivery


class PasswordResetRepository:
    def __init__(self, session: Session):
        self.session = session

    def latest_issue(self, user_id: UUID) -> datetime | None:
        return self.session.scalar(select(CredentialToken.issued_at).where(
            CredentialToken.user_id == user_id, CredentialToken.purpose == "RESET")
            .order_by(CredentialToken.issued_at.desc()).limit(1))

    def delivery(self, identifier: UUID) -> PasswordResetDelivery | None:
        return self.session.get(PasswordResetDelivery, identifier)

    def lock_delivery(self, token_digest: str) -> PasswordResetDelivery | None:
        return self.session.scalar(select(PasswordResetDelivery).where(PasswordResetDelivery.token_digest == token_digest)
            .with_for_update().execution_options(populate_existing=True))

    def expired(self, now: datetime, limit: int) -> tuple[UUID, ...]:
        return tuple(self.session.scalars(select(PasswordResetDelivery.id).where(
            PasswordResetDelivery.ciphertext.is_not(None), PasswordResetDelivery.expires_at <= now).limit(limit)))

    def pending(self, now: datetime, limit: int) -> tuple[UUID, ...]:
        return tuple(self.session.scalars(select(PasswordResetDelivery.id).where(
            PasswordResetDelivery.status == "queued",
            or_(PasswordResetDelivery.claim.is_(None), PasswordResetDelivery.claim_expires_at <= now))
            .order_by(PasswordResetDelivery.id).limit(limit)))

    def invalidate(self, user_id: UUID, now: datetime, *, except_digest: str | None = None) -> None:
        old = select(CredentialToken.digest).where(CredentialToken.user_id == user_id, CredentialToken.purpose == "RESET")
        if except_digest is not None:
            old = old.where(CredentialToken.digest != except_digest)
        self.session.execute(update(PasswordResetDelivery).where(PasswordResetDelivery.token_digest.in_(old),
            PasswordResetDelivery.status == "queued").values(status="failed", ciphertext=None, error_code="TOKEN_INVALIDATED"))
        self.session.execute(update(CredentialToken).where(CredentialToken.digest.in_(old),
            CredentialToken.consumed_at.is_(None)).values(consumed_at=now))
