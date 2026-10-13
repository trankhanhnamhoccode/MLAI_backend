"""Purpose-specific export/job aggregate; no behavior in persistence models."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import ForeignKey,String,Integer,DateTime,UniqueConstraint,CheckConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.infrastructure.database.base import Base


class PlanningExport(Base):
    __tablename__='planning_exports'
    __table_args__=(UniqueConstraint('job_id',name='uq_planning_export_job'),
        Index('ix_planning_exports_queue','status','created_at','id'),
        UniqueConstraint('actor_id','store_id','run_id','key_digest',name='uq_planning_export_key'),
        CheckConstraint("status IN ('queued','running','completed','failed')",name='ck_planning_export_status'),
        CheckConstraint('revision>=1',name='ck_planning_export_revision'),
        CheckConstraint("record_digest ~ '^[0-9a-f]{64}$' AND key_digest ~ '^[0-9a-f]{64}$' AND request_digest ~ '^[0-9a-f]{64}$'",name='ck_planning_export_digests'),
        CheckConstraint("record_json->>'storage_version'='planning_export/1'",name='ck_planning_export_version'))
    id: Mapped[UUID]=mapped_column(primary_key=True)
    job_id: Mapped[UUID]=mapped_column(nullable=False)
    run_id: Mapped[UUID]=mapped_column(ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False,index=True)
    store_id: Mapped[UUID]=mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False,index=True)
    actor_id: Mapped[UUID]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    key_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    request_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    status: Mapped[str]=mapped_column(String(16),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revision: Mapped[int]=mapped_column(Integer,nullable=False)
    record_json: Mapped[dict]=mapped_column(JSONB(none_as_null=True),nullable=False)
    record_digest: Mapped[str]=mapped_column(String(64),nullable=False)
