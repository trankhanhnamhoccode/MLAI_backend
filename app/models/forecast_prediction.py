from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Numeric, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ForecastPrediction(Base):
    """Explicit quantiles, not procurement strategies or a forecasting algorithm."""

    __tablename__ = "forecast_predictions"
    __table_args__ = (
        ForeignKeyConstraint(["forecast_run_id", "store_id"], ["forecast_runs.id", "forecast_runs.store_id"], name="fk_forecast_predictions_run_store", ondelete="RESTRICT"),
        ForeignKeyConstraint(["product_id", "store_id"], ["products.id", "products.store_id"], name="fk_forecast_predictions_product_store", ondelete="RESTRICT"),
        UniqueConstraint("forecast_run_id", "product_id", "forecast_date", name="uq_forecast_predictions_run_product_date"),
        CheckConstraint("0 <= p25 AND p25 <= p50 AND p50 <= p75 AND p25 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND p50 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND p75 NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_forecast_predictions_quantiles"),
        Index("ix_forecast_predictions_run_date", "forecast_run_id", "forecast_date"),
        Index("ix_forecast_predictions_product", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    forecast_run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    p25: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    p50: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    p75: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
