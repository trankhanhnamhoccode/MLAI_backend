from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class BusinessConstraint(Base):
    """Controlled numeric planning inputs; no arbitrary constraint vocabulary."""

    __tablename__ = "business_constraints"
    __table_args__ = (
        ForeignKeyConstraint(["scope_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], name="fk_business_constraints_ingredient_scope_unit", ondelete="RESTRICT"),
        UniqueConstraint("store_id", "scope_type", "scope_id", "constraint_type", "version", name="uq_business_constraints_scope_version", postgresql_nulls_not_distinct=True),
        CheckConstraint("(scope_type = 'STORE' AND scope_id IS NULL AND constraint_type = 'BUDGET_LIMIT' AND unit ~ '^[A-Z]{3}$') OR (scope_type = 'INGREDIENT' AND scope_id IS NOT NULL AND constraint_type = 'MIN_SAFETY_STOCK')", name="ck_business_constraints_registry_scope"),
        CheckConstraint("numeric_value >= 0 AND numeric_value NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_business_constraints_numeric_value"),
        CheckConstraint("version > 0", name="ck_business_constraints_version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_business_constraints_period"),
        ExcludeConstraint(("store_id", "="), ("scope_type", "="), (text("coalesce(scope_id, store_id)"), "="), ("constraint_type", "="), (text("daterange(effective_from, effective_to, '[]')"), "&&"), where=text("active"), name="ex_business_constraints_scope_period", using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", name="fk_business_constraints_store", ondelete="RESTRICT"), nullable=False)
    scope_type: Mapped[Literal["STORE", "INGREDIENT"]] = mapped_column(String(10), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    constraint_type: Mapped[Literal["BUDGET_LIMIT", "MIN_SAFETY_STOCK"]] = mapped_column(String(24), nullable=False)
    numeric_value: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
