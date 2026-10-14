"""Enqueue in the caller's Session; never commit a business transaction here."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID, uuid4
from sqlalchemy import select,or_,text
from sqlalchemy.dialects.postgresql import insert
from app.domain.notifications import NotificationEvent, EventType
from app.models.notifications import NotificationIntent,NotificationRecord,NotificationReadReceipt


class NotificationRepository:
    """Inbox and dispatcher queries in the caller-owned Session."""
    def __init__(self, session):
        self.session=session

    def visible(self, user_id, store_id, accessible_stores):
        query=select(NotificationRecord).where(NotificationRecord.recipient_user_id==user_id)
        query=query.where(NotificationRecord.store_id==store_id) if store_id is not None else query.where(
            or_(NotificationRecord.store_id.is_(None),NotificationRecord.store_id.in_(accessible_stores)))
        return self.session.scalars(query.order_by(NotificationRecord.created_at.desc(),NotificationRecord.id).with_for_update()).all()

    def own_notification(self, identity, user_id):
        return self.session.scalar(select(NotificationRecord).where(NotificationRecord.id==identity,
            NotificationRecord.recipient_user_id==user_id).with_for_update())

    def read_receipt(self, user_id, identity, key_digest):
        return self.session.scalar(select(NotificationReadReceipt).where(NotificationReadReceipt.actor_id==user_id,
            NotificationReadReceipt.notification_id==identity,NotificationReadReceipt.key_digest==key_digest))

    def pending_ids(self, now, limit):
        return self.session.scalars(select(NotificationIntent.id).where(NotificationIntent.status=='pending',
            or_(NotificationIntent.next_attempt_at.is_(None),NotificationIntent.next_attempt_at<=now))
            .order_by(NotificationIntent.created_at,NotificationIntent.id).limit(limit)).all()

    def dispatch_timeouts(self):
        self.session.execute(text("SET LOCAL lock_timeout = '2s'"))
        self.session.execute(text("SET LOCAL statement_timeout = '5s'"))

    def lock_intent(self, identity, *, skip_locked=False):
        return self.session.scalar(select(NotificationIntent).where(NotificationIntent.id==identity)
            .with_for_update(skip_locked=skip_locked).execution_options(populate_existing=True))

    def delivered_notification(self, intent_id):
        return self.session.scalar(select(NotificationRecord).where(NotificationRecord.intent_id==intent_id))


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def encode_event(event: NotificationEvent):
    return dict(payload_version=event.payload_version, event_id=str(event.event_id), event_type=event.event_type.value,
        occurred_at=event.occurred_at.astimezone(timezone.utc).isoformat(), object_id=str(event.object_id),
        recipients=[str(i) for i in event.recipients], store_id=str(event.store_id) if event.store_id else None,
        object_revision=event.object_revision, decision_id=str(event.decision_id) if event.decision_id else None)


def decode_event(payload):
    expected = {"payload_version", "event_id", "event_type", "occurred_at", "object_id", "recipients", "store_id", "object_revision", "decision_id"}
    if set(payload) != expected:
        raise ValueError("INVALID_NOTIFICATION_PAYLOAD")
    return NotificationEvent(event_id=UUID(payload["event_id"]), event_type=EventType(payload["event_type"]),
        occurred_at=datetime.fromisoformat(payload["occurred_at"]), object_id=UUID(payload["object_id"]),
        recipients=tuple(UUID(i) for i in payload["recipients"]),
        store_id=UUID(payload["store_id"]) if payload["store_id"] else None,
        object_revision=payload["object_revision"], decision_id=UUID(payload["decision_id"]) if payload["decision_id"] else None,
        payload_version=payload["payload_version"])


def enqueue(session, event: NotificationEvent) -> tuple[UUID, ...]:
    if not isinstance(event, NotificationEvent):
        raise TypeError("Typed NotificationEvent required")
    payload = encode_event(event)
    checksum = payload_hash(payload)
    ids = []
    # Stable ordering reduces contention between producers with several recipients.
    for recipient in sorted(event.recipients):
        session.execute(insert(NotificationIntent).values(id=uuid4(), event_id=event.event_id,
            recipient_user_id=recipient, store_id=event.store_id, event_type=event.event_type.value,
            payload_version=event.payload_version, payload=payload, payload_digest=checksum,
            status="pending", attempt=0, created_at=event.occurred_at).on_conflict_do_nothing(
                constraint="uq_notification_identity"))
        row = session.scalar(select(NotificationIntent).where(NotificationIntent.event_id == event.event_id,
            NotificationIntent.recipient_user_id == recipient, NotificationIntent.event_type == event.event_type.value))
        if row.payload_digest != checksum or row.payload != payload:
            raise ValueError("NOTIFICATION_IDENTITY_CONFLICT")
        ids.append(row.id)
    return tuple(ids)
