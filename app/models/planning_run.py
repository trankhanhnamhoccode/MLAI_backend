"""Additive planning aggregate; historical S1 DecisionRun is unchanged."""
from datetime import datetime
from uuid import UUID
from typing import Any
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PlanningRun(Base):
    __tablename__ = 'planning_runs'
    __table_args__ = (
        Index('ix_planning_runs_history','store_id','accepted_at','id'),
        UniqueConstraint('actor_id','store_id','operation','key_digest', name='uq_planning_runs_key_scope'),
        CheckConstraint("operation = 'C02'", name='ck_planning_runs_operation'),
        CheckConstraint("status IN ('queued','running','completed','failed')", name='ck_planning_runs_status'),
        CheckConstraint('revision >= 1', name='ck_planning_runs_revision'),
        CheckConstraint("key_digest ~ '^[0-9a-f]{64}$' AND request_digest ~ '^[0-9a-f]{64}$' AND record_digest ~ '^[0-9a-f]{64}$'", name='ck_planning_runs_digests'),
        CheckConstraint("jsonb_typeof(record_json) = 'object' AND record_json ? 'storage_version' AND record_json ? 'package_schema_version' AND jsonb_typeof(record_json->'package_schema_version') = 'number' AND record_json->>'storage_version' = 'planning_storage/1' AND record_json->>'package_schema_version' = '1'", name='ck_planning_runs_record_version'),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    operation: Mapped[str] = mapped_column(String(3),nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    status: Mapped[str] = mapped_column(String(16),nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    revision: Mapped[int] = mapped_column(Integer,nullable=False)
    record_json: Mapped[dict[str,Any]] = mapped_column(JSONB(none_as_null=True),nullable=False)
    record_digest: Mapped[str] = mapped_column(String(64),nullable=False)
