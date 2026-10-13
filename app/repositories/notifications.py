"""Enqueue in the caller's Session; never commit a business transaction here."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.domain.notifications import NotificationEvent, EventType
from app.models.notifications import NotificationIntent


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
