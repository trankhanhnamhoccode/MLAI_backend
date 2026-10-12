"""Retained editor proposals/receipts; no business rules or computed calendar."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class RecipeScheduleChange(Base):
    __tablename__ = "recipe_schedule_changes"
    __table_args__ = (
        ForeignKeyConstraint(["product_id","store_id"],["products.id","products.store_id"],ondelete="RESTRICT"),
        CheckConstraint("(receipt_json IS NULL) = (audit_json IS NULL)",name="ck_recipe_schedule_completion"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id",ondelete="RESTRICT"),index=True)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id",ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    preview_json: Mapped[dict] = mapped_column(JSONB,nullable=False)
    proposal_json: Mapped[dict] = mapped_column(JSONB,nullable=False)
    receipt_json: Mapped[dict | None] = mapped_column(JSONB)
    audit_json: Mapped[dict | None] = mapped_column(JSONB)


class RecipeScheduleRequestReceipt(Base):
    __tablename__ = "recipe_schedule_request_receipts"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id",ondelete="RESTRICT"),primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id",ondelete="RESTRICT"),primary_key=True)
    phase: Mapped[str] = mapped_column(String(10),primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64),primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(100),nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB,nullable=False)
