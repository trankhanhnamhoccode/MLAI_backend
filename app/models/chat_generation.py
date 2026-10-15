"""One accepted provider claim per actor/Store/Run/key; immutable terminal state."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import ForeignKey,String,DateTime,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.infrastructure.database.base import Base


class ChatGenerationRow(Base):
    __tablename__='chat_generations'
    __table_args__=(UniqueConstraint('actor_id','store_id','run_id','key_digest',name='uq_chat_generation_key'),
        CheckConstraint("status IN ('running','completed','failed')",name='ck_chat_generation_status'),
        CheckConstraint("jsonb_typeof(record_json)='object'",name='ck_chat_generation_record'))
    id: Mapped[UUID]=mapped_column(primary_key=True)
    actor_id: Mapped[UUID]=mapped_column(ForeignKey('users.id',ondelete='RESTRICT'),nullable=False)
    store_id: Mapped[UUID]=mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False)
    run_id: Mapped[UUID]=mapped_column(ForeignKey('planning_runs.id',ondelete='RESTRICT'),nullable=False)
    key_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    request_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    record_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    status: Mapped[str]=mapped_column(String(16),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    record_json: Mapped[dict]=mapped_column(JSONB(none_as_null=True),nullable=False)
