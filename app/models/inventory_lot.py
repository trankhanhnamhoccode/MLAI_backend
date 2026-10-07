from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class InventoryLot(Base):
    """Current received lot state; mutations/auditing are future application work."""

    __tablename__ = "inventory_lots"
    __table_args__ = (
        ForeignKeyConstraint(["ingredient_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], name="fk_inventory_lots_ingredient_store_unit", ondelete="RESTRICT"),
        ForeignKeyConstraint(["supplier_id", "store_id"], ["suppliers.id", "suppliers.store_id"], name="fk_inventory_lots_supplier_store", ondelete="RESTRICT"),
        UniqueConstraint("id", "store_id", "ingredient_id", name="uq_inventory_lots_id_store_ingredient"),
        CheckConstraint("on_hand_quantity >= 0 AND on_hand_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_inventory_lots_on_hand"),
        CheckConstraint("received_date IS NULL OR expiry_date IS NULL OR expiry_date >= received_date", name="ck_inventory_lots_expiry"),
        CheckConstraint("unit_cost IS NULL OR (unit_cost >= 0 AND unit_cost NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))", name="ck_inventory_lots_unit_cost"),
        CheckConstraint("lot_code IS NULL OR lot_code ~ '[^[:space:]]'", name="ck_inventory_lots_code_nonblank"),
        Index("ix_inventory_lots_store_ingredient_expiry", "store_id", "ingredient_id", "expiry_date"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    ingredient_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    lot_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    on_hand_quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
