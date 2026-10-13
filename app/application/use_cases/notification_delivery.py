"""Local row-lock ownership; bounded batches, durable retry and restart recovery."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.domain.notifications import TEMPLATES, retry_delay
from app.models import User, Store, StoreMembership
from app.models.notifications import NotificationIntent, NotificationRecord
from app.repositories.notifications import decode_event, payload_hash


class NotificationDispatcher:
    def __init__(self, engine, clock=lambda: datetime.now(timezone.utc)):
        self.engine, self.clock = engine, clock

    def dispatch(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("INVALID_DISPATCH_LIMIT")
        with Session(self.engine) as s:
            ids = list(s.scalars(select(NotificationIntent.id).where(NotificationIntent.status == "pending",
                or_(NotificationIntent.next_attempt_at.is_(None), NotificationIntent.next_attempt_at <= self.clock()))
                .order_by(NotificationIntent.created_at, NotificationIntent.id).limit(limit)))
        completed = 0
        for identity in ids:
            try:
                completed += self.deliver(identity)
            except SQLAlchemyError:
                # Uncertain commit is reconciled by status/identity in a fresh transaction.
                self._defer(identity)
        return completed

    def deliver(self, identity):
        with Session(self.engine) as s, s.begin():
            s.execute(text("SET LOCAL lock_timeout = '2s'"))
            s.execute(text("SET LOCAL statement_timeout = '5s'"))
            candidate = s.get(NotificationIntent, identity)
            if candidate is None:
                return 0
            # Same authority lock order as HTTP: user -> Store/membership -> intent.
            user = s.scalar(select(User).where(User.id == candidate.recipient_user_id).with_for_update())
            store = member = None
            if candidate.store_id:
                store = s.scalar(select(Store).where(Store.id == candidate.store_id).with_for_update())
                member = s.scalar(select(StoreMembership).where(StoreMembership.store_id == candidate.store_id,
                    StoreMembership.user_id == candidate.recipient_user_id).with_for_update())
            row = s.scalar(select(NotificationIntent).where(NotificationIntent.id == identity)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True))
            if row is None or row.status != "pending" or (row.next_attempt_at and row.next_attempt_at > self.clock()):
                return 0
            row.attempt += 1
            try:
                event = decode_event(row.payload)
                if (event.event_id != row.event_id or event.event_type.value != row.event_type or
                    event.store_id != row.store_id or row.recipient_user_id not in event.recipients or
                    event.payload_version != row.payload_version or payload_hash(row.payload) != row.payload_digest):
                    raise ValueError("INVALID_NOTIFICATION_PAYLOAD")
            except (ValueError, TypeError, KeyError, AttributeError):
                row.status, row.error_code = "failed", "INVALID_NOTIFICATION_PAYLOAD"
                row.next_attempt_at = None
                return 0
            owner_event = event.event_type.value.endswith(".submitted")
            if not user or not user.active or (row.store_id and (not store or not store.active or not member or not member.active or (owner_event and member.role != "OWNER"))):
                row.status, row.outcome = "delivered", "suppressed"
                row.error_code, row.next_attempt_at = None, None
                return 1
            title, body = TEMPLATES[event.event_type]
            record = dict(event_id=str(event.event_id), decision_id=str(event.decision_id) if event.decision_id else None,
                event_type=event.event_type.value, occurred_at=event.occurred_at.isoformat(), title=title, body=body,
                object=dict(type=event.object_type, id=str(event.object_id), revision=event.object_revision))
            existing = s.scalar(select(NotificationRecord).where(NotificationRecord.intent_id == row.id))
            if existing:
                if existing.record != record or existing.recipient_user_id != row.recipient_user_id or existing.store_id != row.store_id:
                    row.status, row.error_code = "failed", "NOTIFICATION_IDENTITY_CONFLICT"
                    return 0
            else:
                s.add(NotificationRecord(id=uuid4(), intent_id=row.id, recipient_user_id=row.recipient_user_id,
                    store_id=row.store_id, record=record, created_at=self.clock(), read_at=None, revision=1))
                s.flush()
            row.status, row.outcome = "delivered", "materialized"
            row.error_code, row.next_attempt_at = None, None
            return 1

    def _defer(self, identity):
        with Session(self.engine) as s, s.begin():
            s.execute(text("SET LOCAL lock_timeout = '2s'"))
            s.execute(text("SET LOCAL statement_timeout = '5s'"))
            row = s.scalar(select(NotificationIntent).where(NotificationIntent.id == identity).with_for_update())
            if row and row.status == "pending":
                row.attempt += 1
                row.error_code = "PERSISTENCE_UNAVAILABLE"
                row.next_attempt_at = self.clock() + timedelta(seconds=retry_delay(row.attempt))

    def retry_failed(self, identity):
        """Explicit operator retry after dispatcher repair, retaining event identity/evidence."""
        with Session(self.engine) as s, s.begin():
            row = s.scalar(select(NotificationIntent).where(NotificationIntent.id == identity).with_for_update())
            if not row or row.status != "failed":
                raise ValueError("FAILED_INTENT_REQUIRED")
            decode_event(row.payload)
            if payload_hash(row.payload) != row.payload_digest:
                raise ValueError("INVALID_NOTIFICATION_PAYLOAD")
            row.status, row.next_attempt_at = "pending", self.clock()
            # Keep the previous safe error until the next successful dispatch.
