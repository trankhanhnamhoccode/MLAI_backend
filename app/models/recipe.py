from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Numeric, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Recipe(Base):
    """Dated recipe version; stores BOM inputs but performs no computation."""

    __tablename__ = "recipes"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "store_id"], ["products.id", "products.store_id"], name="fk_recipes_product_store", ondelete="RESTRICT"),
        UniqueConstraint("product_id", "version", name="uq_recipes_product_version"),
        UniqueConstraint("id", "store_id", name="uq_recipes_id_store"),
        CheckConstraint("version > 0", name="ck_recipes_version"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_recipes_period"),
        CheckConstraint("yield_quantity > 0 AND yield_quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_recipes_yield"),
        CheckConstraint("process_loss_rate >= 0 AND process_loss_rate < 1", name="ck_recipes_loss"),
        ExcludeConstraint(("product_id", "="), (text("daterange(effective_from, effective_to, '[]')"), "&&"), name="ex_recipes_product_period", using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", name="fk_recipes_store", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    yield_quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    process_loss_rate: Mapped[Decimal] = mapped_column(Numeric(), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
