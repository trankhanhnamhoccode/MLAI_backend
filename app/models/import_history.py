"""Append-only revisions of recorded history; no inventory or engine state."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class ImportHistoryRecord(Base):
    __tablename__ = 'import_history_records'
    __table_args__ = (
        UniqueConstraint('store_id', 'domain', 'source_system_key', 'report_type', 'source_record_hash', 'version'),
        CheckConstraint('version > 0'),
        CheckConstraint("domain IN ('calendar_events','promotion_observations','usage_history','purchase_history')"),
        CheckConstraint("jsonb_typeof(payload) = 'object' AND jsonb_typeof(provenance) = 'object'"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system_key: Mapped[str] = mapped_column(String(128), nullable=False)
    report_type: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
