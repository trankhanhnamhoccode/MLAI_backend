from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ForecastRun(Base):
    """Forecast provenance storage; application/repository enforce lifecycle writes."""

    __tablename__ = "forecast_runs"
    __table_args__ = (
        UniqueConstraint("id", "store_id", name="uq_forecast_runs_id_store"),
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_forecast_runs_status"),
        CheckConstraint("training_start_date <= training_end_date", name="ck_forecast_runs_training_window"),
        CheckConstraint("forecast_start_date <= forecast_end_date", name="ck_forecast_runs_horizon"),
        CheckConstraint("model_type ~ '[^[:space:]]' AND model_version ~ '[^[:space:]]'", name="ck_forecast_runs_model_metadata"),
        CheckConstraint("artifact_key IS NULL OR artifact_key ~ '[^[:space:]]'", name="ck_forecast_runs_artifact_key"),
        CheckConstraint("input_fingerprint IS NULL OR input_fingerprint ~ '[^[:space:]]'", name="ck_forecast_runs_fingerprint"),
        CheckConstraint("metrics_json IS NULL OR jsonb_typeof(metrics_json) = 'object'", name="ck_forecast_runs_metrics_object"),
        CheckConstraint("completed_at IS NULL OR completed_at >= started_at", name="ck_forecast_runs_timestamps"),
        CheckConstraint("(status = 'RUNNING' AND completed_at IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'COMPLETED' AND completed_at IS NOT NULL AND input_fingerprint IS NOT NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND error_code IS NOT NULL AND error_summary IS NOT NULL)", name="ck_forecast_runs_state"),
        CheckConstraint("(error_code IS NULL OR error_code ~ '[^[:space:]]') AND (error_summary IS NULL OR error_summary ~ '[^[:space:]]')", name="ck_forecast_runs_error_nonblank"),
        Index("ix_forecast_runs_store_created", "store_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), ForeignKey("stores.id", name="fk_forecast_runs_store", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    training_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    training_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_type: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
