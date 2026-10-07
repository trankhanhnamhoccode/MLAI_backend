from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class InventoryMovement(Base):
    """Lot change history; inserting a row does not automatically change balance."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        ForeignKeyConstraint(["lot_id", "store_id", "ingredient_id"], ["inventory_lots.id", "inventory_lots.store_id", "inventory_lots.ingredient_id"], name="fk_inventory_movements_lot_store_ingredient", ondelete="RESTRICT"),
        CheckConstraint("movement_type IN ('RECEIPT', 'USAGE', 'WASTE', 'EXPIRED', 'COUNT_CORRECTION', 'MANUAL_ADJUSTMENT')", name="ck_inventory_movements_type"),
        CheckConstraint("quantity_delta <> 0 AND quantity_delta NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_inventory_movements_delta"),
        CheckConstraint("(movement_type = 'RECEIPT' AND quantity_delta > 0) OR (movement_type IN ('USAGE', 'WASTE', 'EXPIRED') AND quantity_delta < 0) OR movement_type IN ('COUNT_CORRECTION', 'MANUAL_ADJUSTMENT')", name="ck_inventory_movements_sign"),
        CheckConstraint("(reference_type IS NULL AND reference_id IS NULL) OR (reference_type IS NOT NULL AND reference_id IS NOT NULL AND reference_type ~ '[^[:space:]]' AND reference_id ~ '[^[:space:]]')", name="ck_inventory_movements_reference_pair"),
        Index("ix_inventory_movements_lot_occurred", "lot_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    lot_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    ingredient_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    movement_type: Mapped[Literal["RECEIPT", "USAGE", "WASTE", "EXPIRED", "COUNT_CORRECTION", "MANUAL_ADJUSTMENT"]] = mapped_column(String(24), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
