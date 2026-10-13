"""Metadata only: atomic invalidation counters, never business completeness."""

from uuid import UUID
from sqlalchemy import BigInteger, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PublicReadRevision(Base):
    __tablename__ = "public_read_revisions"
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )
    menu_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    recipe_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    inventory_revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
