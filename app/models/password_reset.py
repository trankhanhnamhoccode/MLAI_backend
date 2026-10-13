"""Private transport history for existing RESET credential tokens."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PasswordResetDelivery(Base):
    __tablename__ = "password_reset_deliveries"
    __table_args__ = (CheckConstraint("status IN ('queued','delivered','failed') AND attempts >= 0 AND proof_revision >= 1", name="ck_password_reset_delivery_status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(ForeignKey("credential_tokens.digest", ondelete="RESTRICT"), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    proof_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim: Mapped[UUID | None] = mapped_column()
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(40))
