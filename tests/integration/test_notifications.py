"""C1 real PostgreSQL, public HTTP and fresh-session persistence; no providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import OperationalError, IntegrityError, DBAPIError
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, provision, login, ORIGIN
from tests.integration.test_staff_public import staff_env, create, accept_http, owner_session, target_session
from app.application.contracts.notifications import ReadRequest
from app.application.use_cases.notifications import Notifications
from app.application.use_cases.notification_delivery import NotificationDispatcher
from app.domain.notifications import NotificationEvent, EventType
from app.repositories.notifications import enqueue
from app.models import User, Store, StoreMembership
from app.models.auth import MembershipGrant
from app.models.staff import PermissionEventRecord
from app.models.staff import StaffRequestReceipt
from app.models.notifications import NotificationIntent, NotificationRecord, NotificationReadReceipt


def emit(env, recipient, store_id=None, object_id=None, event_type=EventType.GRANTS_CHANGED, event_id=None):
    event = NotificationEvent(event_id=event_id or uuid4(), event_type=event_type, occurred_at=env[4][0],
        object_id=object_id or uuid4(), recipients=(recipient,), store_id=store_id,
        decision_id=uuid4() if event_type.value.rsplit(".", 1)[1] in {"approved", "rejected", "changes_requested"} else None)
    with Session(env[1]) as s, s.begin():
        ids = enqueue(s, event)
    return event, ids[0]


def dispatcher(env):
    return NotificationDispatcher(env[1], clock=lambda: env[4][0])


def patch(env, item, read, *, key=None, match=None, headers=None):
    return env[5].patch(f"/api/v1/notifications/{item['notification_id']}",
        headers={"Origin": ORIGIN, "X-CSRF-Token": env[5].get("/api/v1/auth/me").json()["data"]["session"]["csrf_token"],
            "Idempotency-Key": key or str(uuid4()), "If-Match": match or '"' + item["version"] + '"', **(headers or {})}, json={"read": read})


def test_event_intent_delivery_list_count_read_replay_and_noop(env):
    owner = setup(env)
    login(env)
    with Session(env[1]) as s:
        member = s.scalar(select(StoreMembership).where(StoreMembership.user_id == owner.user_id))
        mid = member.id
    event, iid = emit(env, owner.user_id, owner.store_id, mid)
    with Session(env[1]) as s, s.begin():
        assert enqueue(s, event) == (iid,)
    assert env[5].get("/api/v1/notifications").json()["data"] == {"items": []}
    assert dispatcher(env).dispatch() == 1
    wire = env[5].get("/api/v1/notifications").json()
    item = wire["data"]["items"][0]
    assert item["store"]["store_id"] == str(owner.store_id)
    assert item["link"] == {"path": f"/stores/{owner.store_id}", "availability": "available"}
    count = env[5].get("/api/v1/notifications/unread-count", params={"snapshot_id": wire["meta"]["snapshot_id"]})
    assert count.status_code == 200 and count.json()["data"]["unread_count"] == 1
    key = str(uuid4())
    result = patch(env, item, True, key=key)
    assert result.status_code == 200
    assert result.headers["etag"] == '"' + result.json()["data"]["version"] + '"'
    assert patch(env, item, True, key=key).json()["data"] == result.json()["data"]
    assert patch(env, item, False, key=key).status_code == 409
    assert patch(env, item, False).json()["error"]["code"] == "NOTIFICATION_REVISION_CONFLICT"
    changed = result.json()["data"]
    assert patch(env, changed, True).json()["data"] == changed
    assert env[5].get("/api/v1/notifications/unread-count", params={"snapshot_id": wire["meta"]["snapshot_id"]}).status_code == 409
    unread = patch(env, changed, False).json()["data"]
    assert unread["read_at"] is None
    env[4][0] += timedelta(seconds=3)
    reread = patch(env, unread, True).json()["data"]
    assert reread["read_at"] != changed["read_at"]
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(NotificationRecord)) == 1
        assert fresh.scalar(select(func.count()).select_from(NotificationReadReceipt)) == 4
        assert fresh.get(NotificationRecord, UUID(item["notification_id"])).read_at is not None
        assert fresh.get(StoreMembership, mid).role == "OWNER"
        assert fresh.scalar(select(func.count()).select_from(MembershipGrant)) == 0
    with Session(env[1]) as s:
        receipt = s.scalar(select(NotificationReadReceipt))
        assert receipt.actor_id == owner.user_id and receipt.request_id and receipt.occurred_at
        receipt.record = {"modified": True}
        with pytest.raises(DBAPIError, match="immutable"):
            s.commit()


def test_visibility_account_store_switch_foreign_revoke_replay_and_suppression(env):
    owner, other = setup(env), setup(env, "other@example.test")
    login(env)
    emit(env, owner.user_id, owner.store_id)
    emit(env, owner.user_id)
    emit(env, other.user_id, other.store_id)
    assert dispatcher(env).dispatch() == 3
    client = env[5]
    items = client.get("/api/v1/notifications").json()["data"]["items"]
    assert len(items) == 2 and any(i["store"] is None and i["link"] is None for i in items)
    assert client.get("/api/v1/notifications/unread-count").json()["data"]["unread_count"] == 2
    assert len(client.get("/api/v1/notifications", params={"store_id": str(owner.store_id)}).json()["data"]["items"]) == 1
    assert client.get("/api/v1/notifications", params={"store_id": str(other.store_id)}).status_code == 404
    with Session(env[1]) as s:
        foreign = s.scalar(select(NotificationRecord).where(NotificationRecord.recipient_user_id == other.user_id))
        foreign_id = foreign.id
    assert patch(env, dict(notification_id=str(foreign_id), version="foreign"), True).status_code == 404
    own = next(i for i in items if i["store"])
    key = str(uuid4())
    assert patch(env, own, True, key=key).status_code == 200
    _, pending = emit(env, owner.user_id, owner.store_id)
    with Session(env[1]) as s, s.begin():
        s.scalar(select(StoreMembership).where(StoreMembership.user_id == owner.user_id)).active = False
    wire = client.get("/api/v1/notifications")
    assert len(wire.json()["data"]["items"]) == 1 and str(owner.store_id) not in wire.text
    assert client.get("/api/v1/notifications/unread-count").json()["data"]["unread_count"] == 1
    assert patch(env, own, True, key=key).status_code == 404
    assert dispatcher(env).dispatch() == 1
    with Session(env[1]) as s, s.begin():
        assert s.get(NotificationIntent, pending).outcome == "suppressed"
        s.scalar(select(StoreMembership).where(StoreMembership.user_id == owner.user_id)).active = True
    assert dispatcher(env).dispatch() == 0
    assert len(client.get("/api/v1/notifications").json()["data"]["items"]) == 2


def test_multi_store_account_only_and_current_membership_link_authority(env):
    owner = setup(env)
    second = provision(env, existing=owner.user_id)
    account = setup(env, "account@example.test", store=False)
    login(env)
    emit(env, owner.user_id, owner.store_id)
    emit(env, owner.user_id, second.store_id)
    emit(env, account.user_id)
    dispatcher(env).dispatch()
    items = env[5].get("/api/v1/notifications").json()["data"]["items"]
    assert {i["store"]["store_id"] for i in items} == {str(owner.store_id), str(second.store_id)}
    assert all(i["link"] is None for i in items)  # Foreign/nonexistent target membership never becomes a link.
    scoped = env[5].get("/api/v1/notifications", params={"store_id": str(second.store_id)}).json()
    assert len(scoped["data"]["items"]) == 1
    assert env[5].get("/api/v1/notifications/unread-count", params={"store_id": str(second.store_id),
        "snapshot_id": scoped["meta"]["snapshot_id"]}).json()["data"]["unread_count"] == 1
    login(env, "account@example.test")
    assert env[5].get("/api/v1/notifications").json()["data"]["items"][0]["store"] is None
    assert env[5].get("/api/v1/notifications/unread-count").json()["data"]["unread_count"] == 1
    assert env[5].get("/api/v1/notifications", params={"store_id": str(second.store_id)}).status_code == 404


def test_materialization_rollback_restart_immutable_evidence_and_bad_payload(env, monkeypatch):
    from sqlalchemy import event as orm_event
    from app.repositories.notifications import encode_event, payload_hash
    owner = setup(env)
    ev, iid = emit(env, owner.user_id)
    armed = [True]
    def fail_after_flush(s, context):
        if armed[0] and any(isinstance(row, NotificationRecord) for row in s.new):
            armed[0] = False
            raise OperationalError("synthetic", {}, Exception("synthetic crash"))
    orm_event.listen(Session, "after_flush", fail_after_flush)
    try:
        assert dispatcher(env).dispatch() == 0
    finally:
        orm_event.remove(Session, "after_flush", fail_after_flush)
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(NotificationRecord)) == 0
        assert fresh.get(NotificationIntent, iid).status == "pending"
    env[4][0] += timedelta(seconds=1)
    assert dispatcher(env).dispatch() == 1
    with Session(env[1]) as s:
        row = s.get(NotificationIntent, iid)
        row.payload = row.payload | {"body": "SYNTHETIC-SECRET"}
        with pytest.raises(DBAPIError, match="immutable"):
            s.commit()
    with Session(env[1]) as s:
        row = s.scalar(select(NotificationRecord))
        row.record = row.record | {"title": "SYNTHETIC-SECRET"}
        with pytest.raises(DBAPIError, match="immutable"):
            s.commit()
    with Session(env[1]) as s:
        s.delete(s.scalar(select(NotificationRecord)))
        with pytest.raises(DBAPIError, match="retention"):
            s.commit()
    payload = encode_event(ev) | {"cells": "SYNTHETIC-SECRET"}
    payload["event_id"] = str(uuid4())
    bad_id = uuid4()
    with Session(env[1]) as s, s.begin():
        s.add(NotificationIntent(id=bad_id, event_id=UUID(payload["event_id"]), recipient_user_id=owner.user_id,
            store_id=None, event_type=ev.event_type.value, payload_version=1, payload=payload,
            payload_digest=payload_hash(payload), status="pending", attempt=0, created_at=env[4][0]))
    assert dispatcher(env).dispatch() == 0
    with Session(env[1]) as fresh:
        assert fresh.get(NotificationIntent, bad_id).status == "failed"
        assert fresh.scalar(select(func.count()).select_from(NotificationRecord)) == 1
    with pytest.raises(ValueError):
        dispatcher(env).retry_failed(bad_id)


def test_read_mapping_notification_does_not_complete_real_import_batch(env):
    from app.application.use_cases.import_staging import ImportStaging
    env[5].app.state.import_staging = ImportStaging(env[2], env[0])
    owner = setup(env)
    logged = login(env).json()["data"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": logged["session"]["csrf_token"], "Idempotency-Key": str(uuid4())}
    response = env[5].post(f"/api/v1/stores/{owner.store_id}/imports", headers=headers, json={"data_date": "2026-10-09"})
    assert response.status_code == 201
    bid = UUID(response.json()["data"]["import_id"])
    from app.models.import_staging import ImportBatch, ImportProfileVersion
    with Session(env[1]) as fresh:
        batch = fresh.get(ImportBatch, bid)
        before = (batch.status, batch.revision, batch.imported_at, batch.analysis_id, batch.active_job_id)
        profiles = fresh.scalar(select(func.count()).select_from(ImportProfileVersion))
    emit(env, owner.user_id, owner.store_id, event_type=EventType.MAPPING_APPROVED)
    dispatcher(env).dispatch()
    item = env[5].get("/api/v1/notifications").json()["data"]["items"][0]
    assert patch(env, item, True).status_code == 200
    with Session(env[1]) as fresh:
        batch = fresh.get(ImportBatch, bid)
        assert (batch.status, batch.revision, batch.imported_at, batch.analysis_id, batch.active_job_id) == before
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == profiles


def test_paging_order_filter_snapshot_grant_changes_and_safe_templates(env):
    owner = setup(env)
    login(env)
    for _ in range(3):
        emit(env, owner.user_id, owner.store_id, event_type=EventType.MAPPING_APPROVED)
    dispatcher(env).dispatch()
    client = env[5]
    first = client.get("/api/v1/notifications", params={"limit": 2, "unread": "true"}).json()
    assert first["meta"]["pagination"]["total_count"] == 3
    cursor = first["meta"]["pagination"]["next_cursor"]
    second = client.get("/api/v1/notifications", params={"limit": 2, "unread": "true", "cursor": cursor}).json()
    rows = first["data"]["items"] + second["data"]["items"]
    assert len({i["notification_id"] for i in rows}) == 3
    assert [i["notification_id"] for i in rows] == sorted(i["notification_id"] for i in rows)
    assert second["meta"]["pagination"]["next_cursor"] is None
    assert all(i["link"] is None and i["body"] == "Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập." for i in rows)
    assert client.get("/api/v1/notifications", params={"limit": 1, "unread": "true", "cursor": cursor}).status_code == 422
    assert client.get("/api/v1/notifications", params={"limit": 2, "cursor": "bad"}).status_code == 422
    assert client.get("/api/v1/notifications?unread=1").status_code == 422
    assert client.get("/api/v1/notifications?limit=0").status_code == 422
    assert client.get("/api/v1/notifications?unknown=x").status_code == 422
    with Session(env[1]) as s, s.begin():
        member = s.scalar(select(StoreMembership).where(StoreMembership.user_id == owner.user_id))
        member.authorization_revision += 1
    assert client.get("/api/v1/notifications", params={"limit": 2, "unread": "true", "cursor": cursor}).status_code == 409


def test_concurrent_delivery_restart_uncertain_ack_and_read_cas(env, monkeypatch):
    owner = setup(env)
    login(env)
    _, iid = emit(env, owner.user_id, owner.store_id)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: dispatcher(env).dispatch(), range(2)))
    assert sum(results) == 1
    assert dispatcher(env).dispatch() == 0
    # ACK lost after a real committed transaction; fresh reconciliation leaves delivered.
    emit(env, owner.user_id)
    d = dispatcher(env)
    original = d.deliver
    def lost_ack(identity):
        original(identity)
        raise OperationalError("synthetic", {}, Exception("synthetic"))
    monkeypatch.setattr(d, "deliver", lost_ack)
    assert d.dispatch() == 0
    assert dispatcher(env).dispatch() == 0
    with Session(env[1]) as s:
        assert s.scalar(select(func.count()).select_from(NotificationRecord)) == 2
        assert all(i.status == "delivered" for i in s.scalars(select(NotificationIntent)))
    item = env[5].get("/api/v1/notifications").json()["data"]["items"][0]
    token = env[5].cookies.get("__Host-shelfcash_session")
    csrf = env[5].get("/api/v1/auth/me").json()["data"]["session"]["csrf_token"]
    def update(_):
        try:
            Notifications(env[2]).read(token, csrf, UUID(item["notification_id"]), ReadRequest(read=True),
                '"' + item["version"] + '"', str(uuid4()), "concurrent")
            return 200
        except Exception as e:
            return e.status
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(update, range(2))) == [200, 412]


def test_delivery_retry_failed_payload_recovery_and_identity_conflict(env, monkeypatch):
    owner = setup(env)
    event, iid = emit(env, owner.user_id)
    d = dispatcher(env)
    def fail(_):
        raise OperationalError("synthetic", {}, Exception("private error"))
    monkeypatch.setattr(d, "deliver", fail)
    assert d.dispatch() == 0
    with Session(env[1]) as s:
        row = s.get(NotificationIntent, iid)
        assert row.status == "pending" and row.attempt == 1 and row.error_code == "PERSISTENCE_UNAVAILABLE"
        assert row.next_attempt_at == env[4][0] + timedelta(seconds=1)
    assert dispatcher(env).dispatch() == 0
    env[4][0] += timedelta(seconds=1)
    assert dispatcher(env).dispatch() == 1
    _, poisoned = emit(env, owner.user_id)
    import app.application.use_cases.notification_delivery as delivery
    decode = delivery.decode_event
    def broken_decoder(payload):
        raise ValueError("INVALID_NOTIFICATION_PAYLOAD")
    monkeypatch.setattr(delivery, "decode_event", broken_decoder)
    assert dispatcher(env).dispatch() == 0
    with Session(env[1]) as s:
        row = s.get(NotificationIntent, poisoned)
        assert row.status == "failed" and row.error_code == "INVALID_NOTIFICATION_PAYLOAD"
    monkeypatch.setattr(delivery, "decode_event", decode)
    dispatcher(env).retry_failed(poisoned)
    assert dispatcher(env).dispatch() == 1
    from dataclasses import replace
    with Session(env[1]) as s, pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        enqueue(s, replace(event, object_id=uuid4()))
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(NotificationIntent)) == 2
        assert fresh.scalar(select(func.count()).select_from(NotificationRecord)) == 2


def test_nf03_guards_strict_json_headers_foreign_and_unavailable(env, monkeypatch):
    owner = setup(env)
    assert env[5].get("/api/v1/notifications").status_code == 401
    login(env)
    emit(env, owner.user_id)
    dispatcher(env).dispatch()
    item = env[5].get("/api/v1/notifications").json()["data"]["items"][0]
    assert patch(env, item, True, headers={"Origin": "https://evil.example.test"}).status_code == 403
    assert patch(env, item, True, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    assert env[5].patch(f"/api/v1/notifications/{item['notification_id']}",
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4()), "If-Match": '"' + item["version"] + '"'},
        json={"read": True}).status_code == 403
    assert patch(env, item, True, headers={"If-Match": "unquoted"}).status_code == 400
    assert patch(env, item, True, headers={"Idempotency-Key": "not-a-uuid"}).status_code == 400
    assert patch(env, item, "true").status_code == 422
    assert env[5].patch(f"/api/v1/notifications/{item['notification_id']}", headers={"Origin": ORIGIN}, content="{").status_code == 400
    response = env[5].patch(f"/api/v1/notifications/{item['notification_id']}", headers={"Origin": ORIGIN}, json={"read": True})
    assert response.status_code == 428
    assert env[5].patch(f"/api/v1/notifications/{item['notification_id']}", headers={"Origin": ORIGIN}, content='{"read":true,"extra":"' + 'x' * 65536 + '"}').status_code == 413
    def unavailable(*args):
        raise OperationalError("synthetic", {}, Exception("SYNTHETIC-PRIVATE-SENTINEL"))
    monkeypatch.setattr(Notifications, "_projection", unavailable)
    result = env[5].get("/api/v1/notifications/unread-count")
    assert result.status_code == 503 and result.json()["data"] is None
    assert "SYNTHETIC-PRIVATE-SENTINEL" not in result.text


def test_real_grants_producer_business_audit_intent_atomic_and_read_does_not_grant(staff_env, monkeypatch):
    ctx = staff_env
    env, staff, owner, target, _, headers = ctx
    data, raw = create(ctx)
    accepted = accept_http(ctx, data, raw).json()["data"]
    owner_session(ctx)
    mid = UUID(accepted["membership_id"])
    member = staff.memberships(ctx[4], owner.store_id)[0].items[0]
    with Session(env[1]) as fresh:
        audit_count = fresh.scalar(select(func.count()).select_from(PermissionEventRecord))
        receipt_count = fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))
    path = f"/api/v1/stores/{owner.store_id}/memberships/{mid}/permissions"
    request_headers = {**headers, "Idempotency-Key": str(uuid4()), "If-Match": member.version}
    from app.repositories import notifications as repo
    original = repo.enqueue
    def reject(s, event):
        original(s, event)
        raise IntegrityError("synthetic intent error", {}, Exception("synthetic"))
    monkeypatch.setattr(repo, "enqueue", reject)
    result = env[5].put(path, headers=request_headers, json={"grants": ["inventory.read"], "reason": "Synthetic update"})
    assert result.status_code == 503
    with Session(env[1]) as fresh:
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id == mid))) == ("menu.read",)
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord)) == audit_count
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == receipt_count
        assert fresh.scalar(select(func.count()).select_from(NotificationIntent)) == 0
    monkeypatch.setattr(repo, "enqueue", original)
    result = env[5].put(path, headers=request_headers, json={"grants": ["inventory.read"], "reason": "Synthetic update"})
    assert result.status_code == 200
    eid = UUID(result.json()["data"]["event_id"])
    with Session(env[1]) as fresh:
        intent = fresh.scalar(select(NotificationIntent))
        assert intent.event_id == eid and intent.recipient_user_id == target.user_id
        assert fresh.get(PermissionEventRecord, eid) and intent.status == "pending"
    d = dispatcher(env)
    def after_commit_failure(identity):
        raise OperationalError("synthetic", {}, Exception("synthetic"))
    monkeypatch.setattr(d, "deliver", after_commit_failure)
    assert d.dispatch() == 0
    with Session(env[1]) as fresh:
        assert fresh.get(PermissionEventRecord, eid)
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id == mid))) == ("inventory.read",)
        assert fresh.scalar(select(NotificationIntent)).status == "pending"
    env[4][0] += timedelta(seconds=1)
    assert dispatcher(env).dispatch() == 1
    target_session(ctx)
    item = env[5].get("/api/v1/notifications").json()["data"]["items"][0]
    assert item["event_type"] == "membership.grants_changed" and "inventory.read" not in str(item)
    assert patch(env, item, True).status_code == 200
    with Session(env[1]) as fresh:
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id == mid))) == ("inventory.read",)
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord)) == audit_count + 1


def test_additive_upgrade_metadata_and_retention_guard(database_settings):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.infrastructure.database.base import Base
    from app.infrastructure.database.engine import create_database_engine
    from scripts.dev import migration_config
    engine = create_database_engine(database_settings)
    try:
        with engine.connect() as c:
            assert c.scalar(text("SELECT current_database()")) == "shelfcash_notifications_test"
            assert c.scalar(text("SELECT current_user")) == "shelfcash_notifications_tester"
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0025_notifications_foundation"
            assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []
        command.downgrade(migration_config(), "0024_integrate_import_auth")
        with Session(engine) as s, s.begin():
            user = User(email="migration@example.test", display_name="Retained", password_hash="!UNSET")
            s.add(user)
            s.flush()
            uid = user.id
        command.upgrade(migration_config(), "head")
        with Session(engine) as fresh:
            assert fresh.get(User, uid).display_name == "Retained"
        event = NotificationEvent(event_id=uuid4(), event_type=EventType.GRANTS_CHANGED,
            occurred_at=datetime.now(timezone.utc), object_id=uuid4(), recipients=(uid,))
        with Session(engine) as s, s.begin():
            enqueue(s, event)
        with pytest.raises(RuntimeError, match="retention"):
            command.downgrade(migration_config(), "0024_integrate_import_auth")
        with Session(engine) as fresh:
            assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == "0025_notifications_foundation"
            assert fresh.scalar(select(func.count()).select_from(NotificationIntent)) == 1
    finally:
        engine.dispose()
