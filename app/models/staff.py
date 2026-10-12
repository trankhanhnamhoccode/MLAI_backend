"""S4.2 additive storage. Workflow rules stay in application use cases."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"
    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','revoked','expired')", name="ck_staff_invitations_status"),
        CheckConstraint("jsonb_typeof(offered_grants) = 'array'", name="ck_staff_invitations_grants"),
        Index("uq_staff_invitations_pending", "store_id", "target_email", unique=True, postgresql_where=text("status = 'pending'")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_email: Mapped[str] = mapped_column(String(320), nullable=False)
    issuer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    offered_grants: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    permission_catalog_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False)


class PermissionEventRecord(Base):
    __tablename__ = "permission_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("store_memberships.id", ondelete="RESTRICT"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InvitationEventRecord(Base):
    __tablename__ = "invitation_events"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    invitation_id: Mapped[UUID] = mapped_column(ForeignKey("staff_invitations.id", ondelete="RESTRICT"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class StaffRequestReceipt(Base):
    __tablename__ = "staff_request_receipts"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(200), primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InvitationDeliveryIntent(Base):
    __tablename__ = "invitation_delivery_intents"
    __table_args__ = (CheckConstraint("status IN ('queued','delivered','failed')", name="ck_invitation_delivery_status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    invitation_id: Mapped[UUID] = mapped_column(ForeignKey("staff_invitations.id", ondelete="RESTRICT"), nullable=False, index=True)
    invitation_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim: Mapped[UUID | None] = mapped_column()
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
