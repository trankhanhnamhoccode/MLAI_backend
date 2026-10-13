"""Explicit account/token fences; caller owns transactions."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import select, update, text, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.infrastructure.auth_crypto import digest
from app.models import User
from app.models.email_verification import EmailVerificationToken, EmailVerificationDelivery


class EmailVerificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_email(self, email: str) -> None:
        # Absence must serialize too; User's unique key remains the final guard.
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"),
                             {"key": int(digest("public-email:" + email)[:15], 16)})

    def create_unset_user(self, email: str, display_name: str) -> UUID | None:
        # Concurrent assisted creation must not abort the acceptance transaction.
        return self.session.scalar(insert(User).values(id=uuid4(), email=email,
            display_name=display_name, password_hash="!UNSET")
            .on_conflict_do_nothing(index_elements=[User.email]).returning(User.id))

    def token_user(self, token_digest: str) -> UUID | None:
        return self.session.scalar(select(EmailVerificationToken.user_id).where(EmailVerificationToken.digest == token_digest))

    def lock_token(self, token_digest: str) -> EmailVerificationToken | None:
        return self.session.scalar(select(EmailVerificationToken).where(EmailVerificationToken.digest == token_digest)
            .with_for_update().execution_options(populate_existing=True))

    def latest_issue(self, user_id: UUID) -> datetime | None:
        return self.session.scalar(select(EmailVerificationToken.issued_at).where(EmailVerificationToken.user_id == user_id)
            .order_by(EmailVerificationToken.issued_at.desc()).limit(1))

    def delivery_id(self, token_digest: str) -> UUID | None:
        return self.session.scalar(select(EmailVerificationDelivery.id).where(EmailVerificationDelivery.token_digest == token_digest))

    def get_delivery(self, identifier: UUID) -> EmailVerificationDelivery | None:
        return self.session.get(EmailVerificationDelivery, identifier)

    def lock_delivery(self, identifier: UUID) -> EmailVerificationDelivery | None:
        return self.session.scalar(select(EmailVerificationDelivery).where(EmailVerificationDelivery.id == identifier)
            .with_for_update().execution_options(populate_existing=True))

    def expired_deliveries(self, now: datetime, limit: int) -> tuple[UUID, ...]:
        return tuple(self.session.scalars(select(EmailVerificationDelivery.id).where(
            EmailVerificationDelivery.ciphertext.is_not(None), EmailVerificationDelivery.expires_at <= now).limit(limit)))

    def pending_deliveries(self, now: datetime, limit: int) -> tuple[UUID, ...]:
        return tuple(self.session.scalars(select(EmailVerificationDelivery.id).where(
            EmailVerificationDelivery.status == "queued",
            or_(EmailVerificationDelivery.claim.is_(None), EmailVerificationDelivery.claim_expires_at <= now))
            .order_by(EmailVerificationDelivery.id).limit(limit)))

    def invalidate(self, user_id: UUID, now: datetime, *, except_digest: str | None = None) -> None:
        old = select(EmailVerificationToken.digest).where(EmailVerificationToken.user_id == user_id)
        if except_digest is not None:
            old = old.where(EmailVerificationToken.digest != except_digest)
        self.session.execute(update(EmailVerificationDelivery).where(EmailVerificationDelivery.token_digest.in_(old),
            EmailVerificationDelivery.status == "queued").values(status="failed", ciphertext=None, error_code="TOKEN_INVALIDATED"))
        self.session.execute(update(EmailVerificationToken).where(EmailVerificationToken.digest.in_(old),
            EmailVerificationToken.consumed_at.is_(None)).values(consumed_at=now))
