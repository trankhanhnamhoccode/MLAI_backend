"""Durable account-scoped receipt for atomic Store onboarding."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, String, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class StoreCreationReceipt(Base):
    __tablename__='store_creation_receipts'
    __table_args__=(UniqueConstraint('store_id',name='uq_store_creation_store'),
        CheckConstraint("jsonb_typeof(result)='object'",name='ck_store_creation_result'))
    actor_id: Mapped[UUID]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),primary_key=True)
    key_digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    request_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    store_id: Mapped[UUID]=mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False)
    result: Mapped[dict]=mapped_column(JSONB,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
