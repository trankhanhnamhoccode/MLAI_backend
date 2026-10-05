from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class SupplierTerm(Base):
    """Dated supplier/ingredient pack inputs; no procurement computation."""

    __tablename__ = "supplier_terms"
    __table_args__ = (
        ForeignKeyConstraint(["supplier_id", "store_id"], ["suppliers.id", "suppliers.store_id"], name="fk_supplier_terms_supplier_store", ondelete="RESTRICT"),
        ForeignKeyConstraint(["ingredient_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], name="fk_supplier_terms_ingredient_store_unit", ondelete="RESTRICT"),
        UniqueConstraint("supplier_id", "ingredient_id", "version", name="uq_supplier_terms_pair_version"),
        CheckConstraint("version > 0", name="ck_supplier_terms_version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_supplier_terms_period"),
        CheckConstraint("pack_size_base_quantity > 0 AND pack_size_base_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_supplier_terms_pack_size"),
        CheckConstraint("minimum_order_packs >= 1", name="ck_supplier_terms_minimum_packs"),
        CheckConstraint("pack_cost >= 0 AND pack_cost NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_supplier_terms_pack_cost"),
        CheckConstraint("lead_time_days >= 0", name="ck_supplier_terms_lead_time"),
        CheckConstraint("shelf_life_days IS NULL OR shelf_life_days >= 0", name="ck_supplier_terms_shelf_life"),
        ExcludeConstraint(("supplier_id", "="), ("ingredient_id", "="), (text("daterange(effective_from, effective_to, '[]')"), "&&"), where=text("active"), name="ex_supplier_terms_pair_period", using="gist"),
        Index("ix_supplier_terms_ingredient_id", "ingredient_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    ingredient_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    pack_size_base_quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    minimum_order_packs: Mapped[int] = mapped_column(Integer, nullable=False)
    pack_cost: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
