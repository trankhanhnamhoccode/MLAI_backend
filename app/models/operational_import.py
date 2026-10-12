"""Scoped operational source facts and stock mutation receipts, not engine state."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class SupplierSourceRecord(Base):
    __tablename__ = "supplier_source_records"
    __table_args__ = (ForeignKeyConstraint(["supplier_id", "store_id"], ["suppliers.id", "suppliers.store_id"], ondelete="RESTRICT"),)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True)
    source_system_key: Mapped[str] = mapped_column(String(1000), primary_key=True)
    source_record_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    supplier_id: Mapped[UUID] = mapped_column(nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)


class TermSourceRecord(Base):
    __tablename__ = "term_source_records"
    __table_args__ = (ForeignKeyConstraint(["id", "store_id"], ["supplier_terms.id", "supplier_terms.store_id"], ondelete="RESTRICT"),)
    id: Mapped[UUID] = mapped_column(ForeignKey("supplier_terms.id", ondelete="RESTRICT"), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PayableFeeRecord(Base):
    __tablename__ = "payable_fee_records"
    __table_args__ = (UniqueConstraint("store_id", "source_system_key", "source_record_hash", "version"), CheckConstraint("version > 0"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resolved_references: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ScopeDeclarationRecord(Base):
    __tablename__ = "scope_declaration_records"
    __table_args__ = (UniqueConstraint("store_id", "source_system_key", "source_record_hash", "version"), CheckConstraint("version > 0"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dependency_digest: Mapped[str] = mapped_column(String(100), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InventoryReceiptRecord(Base):
    __tablename__ = "inventory_receipt_records"
    __table_args__ = (
        UniqueConstraint("store_id", "source_system_key", "source_record_key"),
        UniqueConstraint("lot_id"),
        ForeignKeyConstraint(["lot_id", "store_id", "ingredient_id"], ["inventory_lots.id", "inventory_lots.store_id", "inventory_lots.ingredient_id"], ondelete="RESTRICT"),
        CheckConstraint("origin IN ('OPENING_STOCK','ACTUAL_RECEIPT')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_system_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(128), nullable=False)
    ingredient_id: Mapped[UUID] = mapped_column(nullable=False)
    lot_id: Mapped[UUID] = mapped_column(nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(100), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InventoryThreshold(Base):
    __tablename__ = "inventory_thresholds"
    __table_args__ = (
        ForeignKeyConstraint(["ingredient_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], ondelete="RESTRICT"),
        CheckConstraint("minimum_usable_quantity IS NULL OR (minimum_usable_quantity >= 0 AND minimum_usable_quantity NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))"),
    )
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True)
    ingredient_id: Mapped[UUID] = mapped_column(primary_key=True)
    minimum_usable_quantity: Mapped[Decimal | None] = mapped_column(Numeric())
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class StockRequestReceipt(Base):
    __tablename__ = "stock_request_receipts"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(200), primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(100), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InventoryAudit(Base):
    __tablename__ = "inventory_audit"
    __table_args__ = (UniqueConstraint("movement_id"), ForeignKeyConstraint(["movement_id", "store_id"], ["inventory_movements.id", "inventory_movements.store_id"], ondelete="RESTRICT"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    movement_id: Mapped[UUID | None] = mapped_column(ForeignKey("inventory_movements.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
