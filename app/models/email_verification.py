"""Account-scoped email verification and encrypted transport evidence."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        CheckConstraint("purpose = 'EMAIL_VERIFY' AND proof_revision >= 1 AND credential_revision >= 1", name="ck_email_verification_binding"),
        CheckConstraint("expires_at > issued_at", name="ck_email_verification_expiry"),
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth_accounts.user_id", ondelete="RESTRICT"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    proof_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationDelivery(Base):
    __tablename__ = "email_verification_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('queued','delivered','failed') AND attempts >= 0", name="ck_email_verification_delivery_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(ForeignKey("email_verification_tokens.digest", ondelete="RESTRICT"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim: Mapped[UUID | None] = mapped_column()
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(40))
