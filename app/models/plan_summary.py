"""Purpose-specific summary generation and immutable idempotency receipts."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import ForeignKey, String, DateTime, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PlanSummaryGeneration(Base):
    __tablename__ = 'plan_summary_generations'
    __table_args__ = (
        Index('uq_plan_summary_identity','actor_id','store_id','run_id','identity_digest',unique=True,postgresql_where=text("status <> 'failed'")),
        CheckConstraint("status IN ('running','completed','failed')",name='ck_plan_summary_status'),
        CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_plan_summary_record'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False)
    identity_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    record_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    status: Mapped[str] = mapped_column(String(16),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB(none_as_null=True),nullable=False)


class PlanSummaryReceipt(Base):
    __tablename__ = 'plan_summary_receipts'
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('planning_runs.id',ondelete='RESTRICT'),primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64),primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    generation_id: Mapped[UUID] = mapped_column(ForeignKey('plan_summary_generations.id',ondelete='RESTRICT'),nullable=False)
