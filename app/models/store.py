from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class Store(Base):
    """Mutable store context, without public CRUD or tenancy enforcement."""

    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint("name ~ '[^[:space:]]'", name="ck_stores_name_nonblank"),
        CheckConstraint("timezone ~ '[^[:space:]]'", name="ck_stores_timezone_nonblank"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_stores_currency_shape"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'Asia/Ho_Chi_Minh'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'VND'"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
