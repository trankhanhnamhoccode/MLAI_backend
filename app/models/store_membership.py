from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base
from app.models.store import Store
from app.models.user import User


class StoreMembership(Base):
    """Stored relationship; application checks current account, Store, membership and grants."""

    __tablename__ = "store_memberships"
    __table_args__ = (
        UniqueConstraint("store_id", "user_id", name="uq_store_memberships_store_user"),
        CheckConstraint("role IN ('OWNER', 'STAFF')", name="ck_store_memberships_role"),
        CheckConstraint("delegated_permissions = '[]'::jsonb", name="ck_store_memberships_permissions_reserved"),
        CheckConstraint("authorization_revision >= 1", name="ck_store_memberships_authorization_revision"),
        Index("ix_store_memberships_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", name="fk_store_memberships_store", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", name="fk_store_memberships_user", ondelete="RESTRICT"), nullable=False)
    role: Mapped[Literal["OWNER", "STAFF"]] = mapped_column(String(5), nullable=False)
    delegated_permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    authorization_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship()
    store: Mapped[Store] = relationship()
