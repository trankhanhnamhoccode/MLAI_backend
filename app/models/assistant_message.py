"""Immutable deterministic message receipts; no provider work queue."""
from uuid import UUID
from sqlalchemy import ForeignKey, String, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class AssistantMessage(Base):
    __tablename__='assistant_messages'
    __table_args__=(CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_assistant_message_record'),)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('planning_runs.id',ondelete='RESTRICT'),primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64),primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    record_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB(none_as_null=True),nullable=False)
