from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class DecisionRun(Base):
    """Historical input/output storage; no decision computation or immutable writer."""

    __tablename__ = "decision_runs"
    __table_args__ = (
        ForeignKeyConstraint(["forecast_run_id", "store_id"], ["forecast_runs.id", "forecast_runs.store_id"], name="fk_decision_runs_forecast_store", ondelete="RESTRICT"),
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_decision_runs_status"),
        CheckConstraint("planning_start_date <= planning_end_date", name="ck_decision_runs_planning_window"),
        CheckConstraint("package_schema_version IS NULL OR package_schema_version > 0", name="ck_decision_runs_package_version"),
        CheckConstraint("decision_package_json IS NULL OR package_schema_version IS NOT NULL", name="ck_decision_runs_package_version_required"),
        CheckConstraint("input_fingerprint IS NULL OR input_fingerprint ~ '[^[:space:]]'", name="ck_decision_runs_fingerprint"),
        CheckConstraint("input_snapshot_json IS NULL OR jsonb_typeof(input_snapshot_json) = 'object'", name="ck_decision_runs_snapshot_object"),
        CheckConstraint("decision_package_json IS NULL OR jsonb_typeof(decision_package_json) = 'object'", name="ck_decision_runs_package_object"),
        CheckConstraint("recommended_strategy IS NULL OR recommended_strategy IN ('LEAN', 'BALANCED', 'PROTECTED')", name="ck_decision_runs_strategy"),
        CheckConstraint("completed_at IS NULL OR completed_at >= started_at", name="ck_decision_runs_timestamps"),
        CheckConstraint("(status = 'RUNNING' AND completed_at IS NULL AND decision_package_json IS NULL AND recommended_strategy IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'COMPLETED' AND package_schema_version IS NOT NULL AND input_fingerprint IS NOT NULL AND input_snapshot_json IS NOT NULL AND decision_package_json IS NOT NULL AND recommended_strategy IS NOT NULL AND completed_at IS NOT NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND decision_package_json IS NULL AND recommended_strategy IS NULL AND error_code IS NOT NULL AND error_summary IS NOT NULL)", name="ck_decision_runs_state"),
        CheckConstraint("(error_code IS NULL OR error_code ~ '[^[:space:]]') AND (error_summary IS NULL OR error_summary ~ '[^[:space:]]')", name="ck_decision_runs_error_nonblank"),
        Index("ix_decision_runs_store_created", "store_id", "created_at"),
        Index("ix_decision_runs_forecast", "forecast_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    forecast_run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    planning_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planning_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    package_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    decision_package_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    recommended_strategy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
