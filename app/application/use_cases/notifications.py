"""Own-recipient reads, current authority, pinned snapshots and CAS receipts."""
import base64
from datetime import datetime
import hashlib
import hmac
import json
from uuid import UUID, uuid4
from sqlalchemy import or_, select
from app.application.contracts.auth import AuthError
from app.application.contracts import notifications as dto
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.auth_session import auth_session
from app.models.notifications import NotificationRecord, NotificationReadReceipt
from app.repositories.auth import AuthRepository


def row_version(row):
    return f"notification-{row.id}-{row.revision}"


class Notifications:
    def __init__(self, auth):
        self.auth, self.engine, self.clock = auth, auth.engine, auth.clock

    def _scope(self, s, user, store_id):
        members = AuthRepository(s).accessible_memberships(user.id)
        accessible = {store.id: (store, member) for store, member in members}
        if store_id is not None and store_id not in accessible:
            raise AuthError("RESOURCE_NOT_FOUND", 404)
        return accessible

    def _item(self, row, accessible):
        store = accessible[row.store_id][0] if row.store_id else None
        link = None
        # C2 target authorization is not implemented. Never invent PR/MQ authority.
        # Membership locator opens T02's currently authorized Store context only.
        if store and row.record["object"]["type"] == "membership":
            member = accessible[row.store_id][1]
            if str(member.id) == row.record["object"]["id"]:
                link = dto.NotificationLink(path=f"/stores/{store.id}", availability="available")
        return dto.Notification(notification_id=row.id, recipient_user_id=row.recipient_user_id,
            store=dto.NotificationStore(store_id=store.id, name=store.name) if store else None,
            **row.record, created_at=row.created_at, read_at=row.read_at, link=link, version=row_version(row))

    def _projection(self, s, user, store_id):
        accessible = self._scope(s, user, store_id)
        query = select(NotificationRecord).where(NotificationRecord.recipient_user_id == user.id)
        if store_id is not None:
            query = query.where(NotificationRecord.store_id == store_id)
        else:
            query = query.where(or_(NotificationRecord.store_id.is_(None), NotificationRecord.store_id.in_(accessible)))
        rows = list(s.scalars(query.order_by(NotificationRecord.created_at.desc(), NotificationRecord.id).with_for_update()))
        items = tuple(self._item(row, accessible) for row in rows)
        # Current grants, Store names, membership set and every visible read/content revision.
        authority = [self.auth._summary(s, store, member)[0].model_dump(mode="json")
                     for store, member in accessible.values()]
        fingerprint = hashlib.sha256(json.dumps([authority, [i.model_dump(mode="json") for i in items]],
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return items, fingerprint

    def _snapshot(self, token, store_id, fingerprint, snapshot=None):
        domain = "notifications-snapshot:" + str(store_id)
        if snapshot:
            try:
                old, observed, signature = snapshot.split("|")
                payload = old + "|" + observed
                if len(snapshot.encode()) > 256 or not hmac.compare_digest(signature, self.auth.cursor_signer.sign(token, domain, payload)):
                    raise ValueError()
                timestamp = datetime.fromisoformat(observed)
                if timestamp.utcoffset() is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise AuthError("INVALID_FILTER", 422) from None
            if old != fingerprint:
                raise AuthError("SNAPSHOT_NOT_AVAILABLE", 409)
            return snapshot, timestamp
        observed = self.clock()
        payload = fingerprint + "|" + observed.isoformat()
        return payload + "|" + self.auth.cursor_signer.sign(token, domain, payload), observed

    def _cursor(self, token, payload):
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        return encoded + "." + self.auth.cursor_signer.sign(token, "notifications-page", encoded)

    def list(self, token, *, store_id=None, unread=None, limit=50, cursor=None):
        binding = [str(store_id), unread, limit]
        offset, snapshot = 0, None
        if cursor:
            try:
                encoded, signature = cursor.split(".")
                if len(cursor.encode()) > 4096 or not hmac.compare_digest(signature, self.auth.cursor_signer.sign(token or "", "notifications-page", encoded)):
                    raise ValueError()
                payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                if payload["binding"] != binding or type(payload["offset"]) is not int or payload["offset"] < 1:
                    raise ValueError()
                offset, snapshot = payload["offset"], payload["snapshot"]
            except (ValueError, TypeError, KeyError):
                raise AuthError("INVALID_CURSOR", 422) from None
        with auth_session(self.engine) as s:
            user, _ = self.auth._resolve(s, token)
            items, fingerprint = self._projection(s, user, store_id)
            snapshot, observed = self._snapshot(token, store_id, fingerprint, snapshot)
            filtered = tuple(i for i in items if unread is None or (i.read_at is None) == unread)
            end = offset + limit
            next_cursor = self._cursor(token, dict(binding=binding, offset=end, snapshot=snapshot)) if end < len(filtered) else None
            result = dto.Inbox(items=filtered[offset:end]), dict(snapshot_id=snapshot, observed_at=observed,
                pagination=dict(limit=limit, next_cursor=next_cursor, total_count=len(filtered)))
            s.commit()
            return result

    def count(self, token, *, store_id=None, snapshot_id=None):
        with auth_session(self.engine) as s:
            user, _ = self.auth._resolve(s, token)
            items, fingerprint = self._projection(s, user, store_id)
            snapshot, observed = self._snapshot(token, store_id, fingerprint, snapshot_id)
            result = dto.UnreadCount(unread_count=sum(i.read_at is None for i in items),
                scope="store" if store_id else "accessible", store_id=store_id), dict(snapshot_id=snapshot, observed_at=observed)
            s.commit()
            return result

    def read(self, token, csrf, identity, body, match, key, request_id):
        if match is None:
            raise AuthError("PRECONDITION_REQUIRED", 428)
        try:
            if key is None or str(UUID(key)) != key or not 1 <= len(match.encode()) <= 258:
                raise ValueError()
            if len(match) < 3 or match[0] != '"' or match[-1] != '"' or '"' in match[1:-1]:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AuthError("INVALID_REQUEST", 400) from None
        with auth_session(self.engine) as s:
            user, _ = self.auth._resolve(s, token, csrf or "")
            accessible = self._scope(s, user, None)
            row = s.scalar(select(NotificationRecord).where(NotificationRecord.id == identity,
                NotificationRecord.recipient_user_id == user.id).with_for_update())
            if row is None or (row.store_id and row.store_id not in accessible):
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            checksum = digest(json.dumps([body.read, match], separators=(",", ":")))
            receipt = s.scalar(select(NotificationReadReceipt).where(NotificationReadReceipt.actor_id == user.id,
                NotificationReadReceipt.notification_id == identity, NotificationReadReceipt.key_digest == digest(key)))
            if receipt:
                if receipt.request_digest != checksum:
                    raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
                result = dto.ReadState(**receipt.record)
                s.commit()
                return result
            if match[1:-1] != row_version(row):
                raise AuthError("NOTIFICATION_REVISION_CONFLICT", 412)
            if (row.read_at is not None) != body.read:
                row.read_at = self.clock() if body.read else None
                row.revision += 1
            result = dto.ReadState(notification_id=row.id, read_at=row.read_at, version=row_version(row))
            s.add(NotificationReadReceipt(id=uuid4(), actor_id=user.id, notification_id=row.id,
                key_digest=digest(key), request_digest=checksum, record=result.model_dump(mode="json"),
                occurred_at=self.clock(), request_id=request_id))
            s.commit()
            return result
