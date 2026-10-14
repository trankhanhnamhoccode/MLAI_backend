"""Durable intents, inbox projection and separate read audit receipts."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class NotificationIntent(Base):
    __tablename__ = "notification_intents"
    __table_args__ = (
        UniqueConstraint("event_id", "recipient_user_id", "event_type", name="uq_notification_identity"),
        CheckConstraint("status IN ('pending','delivered','failed')", name="ck_notification_intent_status"),
        CheckConstraint("attempt >= 0 AND payload_version = 1", name="ck_notification_intent_version"),
        Index("ix_notification_due", "status", "next_attempt_at", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_version: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationRecord(Base):
    __tablename__ = "notifications"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_notification_revision"),
                     Index("ix_notifications_recipient_order", "recipient_user_id", "created_at", "id"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    intent_id: Mapped[UUID] = mapped_column(ForeignKey("notification_intents.id", ondelete="RESTRICT"), unique=True, nullable=False)
    recipient_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(nullable=False)


class NotificationReadReceipt(Base):
    __tablename__ = "notification_read_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "notification_id", "key_digest", name="uq_notification_read_receipt"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notification_id: Mapped[UUID] = mapped_column(ForeignKey("notifications.id", ondelete="RESTRICT"), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False)
