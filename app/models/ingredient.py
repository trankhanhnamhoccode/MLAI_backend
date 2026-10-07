from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Ingredient(Base):
    """Canonical store ingredient; exact base unit without conversion behavior."""

    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("store_id", "sku", name="uq_ingredients_store_sku"),
        UniqueConstraint("id", "store_id", "base_unit", name="uq_ingredients_id_store_unit"),
        CheckConstraint("name ~ '[^[:space:]]'", name="ck_ingredients_name_nonblank"),
        CheckConstraint("sku IS NULL OR sku ~ '[^[:space:]]'", name="ck_ingredients_sku_nonblank"),
        CheckConstraint("base_unit ~ '[^[:space:]]'", name="ck_ingredients_base_unit_nonblank"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", name="fk_ingredients_store", ondelete="RESTRICT"), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    expiry_tracking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
