"""Immutable-by-application retained input, separate from model binaries/metrics."""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ForecastRunInput(Base):
    __tablename__ = 'forecast_run_inputs'
    __table_args__ = (
        ForeignKeyConstraint(['forecast_run_id', 'store_id'], ['forecast_runs.id', 'forecast_runs.store_id'],
                             name='fk_forecast_run_inputs_run_store', ondelete='RESTRICT'),
        CheckConstraint("jsonb_typeof(prepared_json) = 'object'", name='ck_forecast_run_inputs_object'),
        CheckConstraint('serialization_version > 0', name='ck_forecast_run_inputs_version'),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name='ck_forecast_run_inputs_digest'),
    )

    forecast_run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    prepared_json: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    serialization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
