"""Current Store setup and immutable point-in-time evidence; no business rules."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PlanningDefault(Base):
    __tablename__ = 'planning_defaults'
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    requirements_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanningBudget(Base):
    __tablename__ = 'planning_budgets'
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[str] = mapped_column(String(37), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)


class SavedRequirement(Base):
    __tablename__ = 'saved_requirements'
    __table_args__ = (UniqueConstraint('id', 'store_id'),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    requirements_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    default_reference_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)


class PlanningConfigurationEvent(Base):
    __tablename__ = 'planning_configuration_events'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PlanningConfigurationRevision(Base):
    __tablename__ = 'planning_configuration_revisions'
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), primary_key=True)
    resource: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


class PlanningConfigurationReceipt(Base):
    __tablename__ = 'planning_configuration_receipts'
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey('stores.id', ondelete='RESTRICT'), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(100), nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False)
    record_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
