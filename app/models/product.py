from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Product(Base):
    """Store-scoped menu item; no pricing or CRUD behavior."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("store_id", "sku", name="uq_products_store_sku"),
        UniqueConstraint("id", "store_id", name="uq_products_id_store"),
        CheckConstraint("name ~ '[^[:space:]]'", name="ck_products_name_nonblank"),
        CheckConstraint("sku IS NULL OR sku ~ '[^[:space:]]'", name="ck_products_sku_nonblank"),
        CheckConstraint("selling_unit ~ '[^[:space:]]'", name="ck_products_selling_unit_nonblank"),
        CheckConstraint("price IS NULL OR (price >= 0 AND price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))", name="ck_products_price"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", name="fk_products_store", ondelete="RESTRICT"), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    selling_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
