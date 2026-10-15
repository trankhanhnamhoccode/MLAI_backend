"""One atomic immutable receipt per actor/Store/Run/chat/key."""
from sqlalchemy.dialects.postgresql import insert
from app.models.assistant_message import AssistantMessage
from app.application.planning_serialization import digest, exact_json
from sqlalchemy import text


class MessageRepository:
    def __init__(self, session): self.session=session

    def get(self, actor, store, run, key):
        return self.session.get(AssistantMessage,(actor,store,run,key))

    def lock_key(self,actor,store,run,key):
        # Same short transaction fence for legacy deterministic and provider
        # acceptance. Never held while waiting on a model.
        value=int(digest('AS03-key-lock',[actor,store,run,key])[:15],16)
        self.session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':value})

    def accept(self, actor, store, run, key, request_digest, record):
        self.session.execute(insert(AssistantMessage).values(actor_id=actor,store_id=store,run_id=run,
            key_digest=key,request_digest=request_digest,record_digest=digest('assistant-message',record),
            record_json=exact_json(record)).on_conflict_do_nothing())
        self.session.expire_all()
        return self.get(actor,store,run,key)
