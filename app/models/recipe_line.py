from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class RecipeLine(Base):
    """One ingredient quantity; store/unit witness columns enforce graph integrity."""

    __tablename__ = "recipe_lines"
    __table_args__ = (
        ForeignKeyConstraint(["recipe_id", "store_id"], ["recipes.id", "recipes.store_id"], name="fk_recipe_lines_recipe_store", ondelete="RESTRICT"),
        ForeignKeyConstraint(["ingredient_id", "store_id", "unit"], ["ingredients.id", "ingredients.store_id", "ingredients.base_unit"], name="fk_recipe_lines_ingredient_store_unit", ondelete="RESTRICT"),
        UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_lines_recipe_ingredient"),
        CheckConstraint("quantity > 0 AND quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_recipe_lines_quantity"),
        Index("ix_recipe_lines_ingredient_id", "ingredient_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    recipe_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    ingredient_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
