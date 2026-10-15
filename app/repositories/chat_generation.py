"""Concrete purpose-specific generation reads/writes; no transaction ownership."""
from sqlalchemy import select,func
from app.models.chat_generation import ChatGenerationRow
from app.application.planning_serialization import digest,exact_json


class ChatGenerationRepository:
    def __init__(self,session):self.session=session

    def get(self,actor,store,run,key,*,lock=False):
        q=select(ChatGenerationRow).where(ChatGenerationRow.actor_id==actor,ChatGenerationRow.store_id==store,
            ChatGenerationRow.run_id==run,ChatGenerationRow.key_digest==key)
        if lock:q=q.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(q)

    def accept(self,record):
        row=ChatGenerationRow(id=record.generation_id,actor_id=record.actor_id,store_id=record.store_id,run_id=record.run_id,
            key_digest=record.key_digest,request_digest=record.request_digest,record_digest=digest('chat-generation',record),
            status=record.status,created_at=record.created_at,record_json=exact_json(record))
        self.session.add(row);self.session.flush();return row

    def save(self,row,record):
        row.status=record.status;row.record_json=exact_json(record);row.record_digest=digest('chat-generation',record)

    def running_count(self,store):
        return self.session.scalar(select(func.count()).select_from(ChatGenerationRow).where(
            ChatGenerationRow.store_id==store,ChatGenerationRow.status=='running'))
