from datetime import datetime, timezone
from dataclasses import FrozenInstanceError
from uuid import uuid4
import pytest
from app.domain.notifications import NotificationEvent, EventType, TEMPLATES, retry_delay
from app.repositories.notifications import encode_event, decode_event
from app.config import Settings
from scripts.dev import validate_reset_target


def event(**changes):
    return NotificationEvent(**(dict(event_id=uuid4(), event_type=EventType.MAPPING_APPROVED,
        occurred_at=datetime.now(timezone.utc), object_id=uuid4(), recipients=(uuid4(),), decision_id=uuid4()) | changes))


def test_immutable_typed_versioned_safe_templates():
    value = event()
    assert decode_event(encode_event(value)) == value
    with pytest.raises(FrozenInstanceError):
        value.payload_version = 2
    assert TEMPLATES[EventType.MAPPING_APPROVED] == ("Profile đã được duyệt", "Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập.")
    assert not any("<" in title + body for title, body in TEMPLATES.values())
    with pytest.raises(TypeError):
        TEMPLATES[EventType.MAPPING_APPROVED] = ("PRIVATE", "PRIVATE")
    with pytest.raises(TypeError):
        event(link="https://arbitrary.example.test")


@pytest.mark.parametrize("changes", [{"payload_version": 2}, {"event_type": "unknown"},
    {"recipients": ()}, {"recipients": ("not-a-uuid",)}, {"occurred_at": datetime(2026, 1, 1)},
    {"object_revision": "x" * 257}, {"object_id": "fake"}, {"payload_version": True}, {"decision_id": None}])
def test_payload_rejected(changes):
    with pytest.raises(ValueError):
        event(**changes)


def test_extra_payload_cannot_supply_finance_or_url():
    payload = encode_event(event())
    for name in ("title", "body", "link", "budget", "cells", "token"):
        with pytest.raises(ValueError):
            decode_event(payload | {name: "PRIVATE-SENTINEL"})


def test_backoff_bounded_and_dedicated_reset_guard():
    assert [retry_delay(i) for i in range(1, 8)] == [1, 5, 30, 60, 300, 300, 300]
    assert Settings(_env_file=None).notification_worker_enabled is False
    for role in ("admin", "shelfcash", "shelfcash_notifications_tester"):
        settings = Settings(_env_file=None, environment="test",
            database_url=f"postgresql+psycopg://{role}:synthetic@127.0.0.1:5433/shelfcash_notifications_test")
        if role == "shelfcash_notifications_tester":
            validate_reset_target(settings)
        else:
            with pytest.raises(ValueError):
                validate_reset_target(settings)
