"""Owned synchronous transactions for canonical Staff consent and permissions."""
import base64
from dataclasses import asdict
from datetime import timedelta
import hashlib
import hmac
import json
from uuid import uuid4

from app.application.contracts.auth import AuthError, Pagination, UserSummary
from app.application.contracts import staff as dto
from app.application.use_cases.auth import membership_version, version
from app.domain.permissions import CATALOGUE, CATALOG_VERSION
from app.infrastructure.auth_crypto import digest, new_token
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.invitation_secret import InvitationSecret
from app.models import StoreMembership
from app.models.auth import AuthAccount
from app.models.staff import (StaffInvitation, StaffRequestReceipt, PermissionEventRecord,
                             InvitationEventRecord, InvitationDeliveryIntent)
from app.repositories.auth import AuthRepository
from app.repositories.staff import StaffRepository


def descriptors(keys=None):
    return tuple(dto.PermissionDescriptor(**asdict(p)) for p in CATALOGUE if keys is None or p.key in keys)


def permission_event(s, member, *, actor, now, reason, before, before_version,
                     after, request_id, source, operator=None, issuer=None):
    result = dto.PermissionEvent(event_id=uuid4(), store_id=member.store_id,
        target_membership_id=member.id, actor_user_id=actor, occurred_at=now, reason=reason,
        before_grants=before, after_grants=after, before_version=before_version,
        after_version=membership_version(member, after), request_id=request_id,
        source=source, operator_reference=operator, issuer_user_id=issuer)
    s.add(PermissionEventRecord(id=result.event_id, store_id=member.store_id,
        membership_id=member.id, occurred_at=now, record_json=result.model_dump(mode="json")))
    return result


def invitation_event(s, row, *, actor, now, kind, before_version=None,
                     before_grants=None, recipient=None, attempt=None, reason=None):
    result = dto.InvitationEvent(event_id=uuid4(), invitation_id=row.id, store_id=row.store_id,
        actor_user_id=actor, occurred_at=now, kind=kind, reason=reason,
        before_version=before_version, after_version=row.version,
        before_offered_grants=before_grants, after_offered_grants=tuple(row.offered_grants),
        recipient_user_id=recipient, delivery_attempt_id=attempt)
    s.add(InvitationEventRecord(id=result.event_id, invitation_id=row.id,
        store_id=row.store_id, occurred_at=now, record_json=result.model_dump(mode="json")))
    return result


def delivery_identity(row, attempt):
    return f"{row.store_id}:{row.id}:{row.target_email}:{row.version}:{attempt}"


class StaffUseCases:
    def __init__(self, auth, settings):
        self.auth, self.engine, self.settings, self.clock = auth, auth.engine, settings, auth.clock

    def _member(self, s, member, user):
        grants = AuthRepository(s).grants(member.id)
        return dto.StaffMembership(membership_id=member.id,
            user=UserSummary(user_id=user.id, email=user.email, display_name=user.display_name),
            active=member.active, grants=grants, version=membership_version(member, grants), updated_at=member.updated_at)

    def _invitation(self, row):
        state = "expired" if row.status == "pending" and self.clock() >= row.expires_at else row.status
        return dto.Invitation(invitation_id=row.id, store_id=row.store_id, target_email=row.target_email,
            offered_grants=tuple(row.offered_grants), permission_catalog_version=row.permission_catalog_version,
            version=row.version, status=state, issuer_user_id=row.issuer_user_id, created_at=row.created_at,
            issued_at=row.issued_at, expires_at=row.expires_at, accepted_at=row.accepted_at,
            revoked_at=row.revoked_at, reason=row.reason, delivery_status=row.delivery_status)

    def _page(self, items, token, actor, summary, filters, limit, cursor):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise AuthError("INVALID_FILTER", 422)
        binding = [str(actor.user_id), str(summary.store_id), summary.authorization_version, filters, limit]
        fingerprint, offset = version([i.model_dump(mode="json") for i in items]), 0
        if cursor:
            try:
                payload, signature = cursor.split(".")
                expected = self.auth.cursor_signer.sign(token, "staff", payload)
                if not hmac.compare_digest(expected, signature):
                    raise ValueError()
                data = json.loads(base64.urlsafe_b64decode(payload))
                if data["binding"] != binding:
                    raise ValueError()
                if data["fingerprint"] != fingerprint:
                    raise AuthError("LIST_VERSION_CHANGED", 409)
                offset = data["offset"]
                if type(offset) is not int or not 0 < offset < len(items):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise AuthError("INVALID_CURSOR", 422) from None
        next_cursor = None
        if offset + limit < len(items):
            payload = base64.urlsafe_b64encode(json.dumps(dict(binding=binding,
                fingerprint=fingerprint, offset=offset+limit)).encode()).decode()
            next_cursor = payload + "." + self.auth.cursor_signer.sign(token, "staff", payload)
        return tuple(items[offset:offset+limit]), Pagination(limit=limit, next_cursor=next_cursor, total_count=len(items))

    def memberships(self, token, store_id, active="all", limit=50, cursor=None):
        if active not in {"all", "true", "false"}:
            raise AuthError("INVALID_FILTER", 422)
        with auth_session(self.engine) as s:
            actor, summary, _ = self.auth.authorize_in_session(s, token, store_id, owner_only=True)
            items = tuple(self._member(s, m, u) for m, u in StaffRepository(s).members(store_id)
                          if active == "all" or m.active == (active == "true"))
            items, page = self._page(items, token, actor, summary, ["memberships", active], limit, cursor)
            s.commit()
        return dto.MembershipList(items=items, permission_catalog=descriptors()), page

    def events(self, token, store_id, membership_id=None, limit=50, cursor=None):
        with auth_session(self.engine) as s:
            actor, summary, _ = self.auth.authorize_in_session(s, token, store_id, owner_only=True)
            repo = StaffRepository(s)
            if membership_id is not None and repo.lock_member_id(store_id, membership_id) is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            items = tuple(dto.PermissionEvent.model_validate(r.record_json) for r in repo.permission_events(store_id, membership_id))
            items, page = self._page(items, token, actor, summary, ["permissions", str(membership_id)], limit, cursor)
            s.commit()
        return dto.PermissionEvents(items=items), page

    def _request(self, body, key, match=None, *, cas=False):
        if not key or not key.strip() or len(key.encode()) > 128:
            raise AuthError("VALIDATION_ERROR", 422)
        if cas and match is None:
            raise AuthError("PRECONDITION_REQUIRED", 428)
        if match is not None:
            if match.startswith('"') and match.endswith('"'):
                match = match[1:-1]
            if not match or any(c in match for c in ('"', ',', '*')) or match.startswith("W/"):
                raise AuthError("VALIDATION_ERROR", 422)
        data = body.model_dump(mode="json")
        if "token" in data:
            data["token"] = digest(data["token"])
        return digest(key), digest(json.dumps([data, match], sort_keys=True)), match

    def _old(self, s, actor, store, operation, kd, fingerprint):
        row = StaffRepository(s).receipt(actor.user_id, store, operation, kd)
        if row and row.request_digest != fingerprint:
            raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
        return row.record_json if row else None

    def _save(self, s, actor, store, operation, kd, fingerprint, result):
        s.add(StaffRequestReceipt(actor_id=actor.user_id, store_id=store, operation=operation,
            key_digest=kd, request_digest=fingerprint, record_json=result.model_dump(mode="json")))

    def _owner_rate(self, token, store, csrf, operation, kd, fp):
        # Persist throttle even when the later mutation fails CAS/validation.
        with auth_session(self.engine) as s:
            actor, _, _ = self.auth.authorize_in_session(s, token, store, owner_only=True, csrf=csrf or "")
            old = self._old(s, actor, store, operation, kd, fp)
            error = None if old else self.auth._rate(s, "invitation-mutation:"+str(store), 10,
                self.clock(), window=timedelta(minutes=10))
            s.commit()
        if error:
            raise error

    def replace(self, token, store, membership, body, key, match, csrf, request_id):
        body = dto.GrantsRequest.model_validate(body.model_dump())
        kd, fp, match = self._request(body, key, match, cas=True)
        op = f"PUT /stores/{store}/memberships/{membership}/permissions"
        with auth_session(self.engine) as s:
            actor, _, _ = self.auth.authorize_in_session(s, token, store, owner_only=True, csrf=csrf or "")
            repo = StaffRepository(s)
            member = repo.lock_member_id(store, membership)
            if member is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            if member.role != "STAFF":
                raise AuthError("INVALID_TARGET", 422)
            if not member.active:
                raise AuthError("MEMBERSHIP_INACTIVE", 409)
            old = self._old(s, actor, store, op, kd, fp)
            if old:
                result = dto.PermissionUpdate.model_validate(old)
            else:
                user = AuthRepository(s).user(member.user_id)
                current = self._member(s, member, user)
                if match != current.version:
                    raise AuthError("PERMISSION_REVISION_CONFLICT", 412)
                event = None
                if current.grants != body.grants:
                    repo.replace_grants(member.id, body.grants)
                    s.refresh(member)
                    member.updated_at = self.clock()
                    event = permission_event(s, member, actor=actor.user_id, now=self.clock(), reason=body.reason,
                        before=current.grants, before_version=current.version, after=body.grants,
                        request_id=request_id, source="OWNER_CHANGE")
                result = dto.PermissionUpdate(membership=self._member(s, member, user),
                    event_id=event.event_id if event else None, changed=event is not None)
                self._save(s, actor, store, op, kd, fp, result)
            s.commit()
        return result

    def _catalog(self, catalog):
        if catalog != CATALOG_VERSION:
            raise AuthError("PERMISSION_CATALOG_CHANGED", 409)

    def _issue(self, s, row):
        raw, attempt = new_token(), uuid4()
        row.token_digest = digest(raw)
        row.delivery_status = "queued"
        crypto = InvitationSecret(self.settings.auth_delivery_encryption_key)
        ciphertext = crypto.seal(raw, delivery_identity(row, attempt))
        # Concrete FK order; no ORM relationship is needed for this workflow.
        s.flush()
        s.add(InvitationDeliveryIntent(id=attempt, invitation_id=row.id, invitation_version=row.version,
            status="queued", ciphertext=ciphertext, expires_at=row.expires_at))
        return dto.DeliveryReceipt(status="queued", attempt_id=attempt)

    def create(self, token, store, body, key, csrf, request_id):
        body = dto.CreateInvitation.model_validate(body.model_dump())
        kd, fp, _ = self._request(body, key)
        op = f"POST /stores/{store}/staff-invitations"
        self._owner_rate(token, store, csrf, op, kd, fp)
        with auth_session(self.engine) as s:
            actor, _, _ = self.auth.authorize_in_session(s, token, store, owner_only=True, csrf=csrf or "")
            repo = StaffRepository(s)
            old = self._old(s, actor, store, op, kd, fp)
            if old:
                result = dto.InvitationCreation.model_validate(old)
            else:
                self._catalog(body.permission_catalog_version)
                if repo.membership_for_email(store, body.email):
                    raise AuthError("MEMBERSHIP_ALREADY_EXISTS", 409)
                pending = repo.pending_for_email(store, body.email)
                if pending:
                    if self.clock() < pending.expires_at:
                        raise AuthError("INVITATION_ALREADY_PENDING", 409)
                    pending.status = "expired"
                    repo.cancel_delivery(pending.id)
                    s.flush()
                now = self.clock()
                row = StaffInvitation(id=uuid4(), store_id=store, target_email=body.email,
                    issuer_user_id=actor.user_id, version=str(uuid4()), token_digest="",
                    offered_grants=list(body.grants), permission_catalog_version=body.permission_catalog_version,
                    status="pending", created_at=now, issued_at=now, expires_at=now+timedelta(days=7),
                    accepted_at=None, revoked_at=None, reason=body.reason, delivery_status="queued")
                s.add(row)
                delivery = self._issue(s, row)
                s.flush()
                invitation_event(s, row, actor=actor.user_id, now=now, kind="CREATED", reason=body.reason)
                result = dto.InvitationCreation(invitation=self._invitation(row), delivery=delivery)
                self._save(s, actor, store, op, kd, fp, result)
            s.commit()
        return result

    def action(self, token, store, identifier, body, key, match, csrf, request_id):
        cls = dto.ReissueInvitation if body.action == "reissue" else dto.RevokeInvitation
        body = cls.model_validate(body.model_dump())
        kd, fp, match = self._request(body, key, match, cas=True)
        op = f"POST /stores/{store}/staff-invitations/{identifier}/actions/{body.action}"
        self._owner_rate(token, store, csrf, op, kd, fp)
        with auth_session(self.engine) as s:
            actor, _, _ = self.auth.authorize_in_session(s, token, store, owner_only=True, csrf=csrf or "")
            repo = StaffRepository(s)
            row = repo.invitation(identifier, store, locked=True)
            if row is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            old = self._old(s, actor, store, op, kd, fp)
            if old:
                result = dto.InvitationAction.model_validate(old)
            else:
                if match != row.version:
                    raise AuthError("INVITATION_REVISION_CONFLICT", 412)
                state = self._invitation(row).status
                if state == "accepted" or (body.action == "revoke" and state == "expired"):
                    raise AuthError("INVITATION_STATE_CONFLICT", 409)
                event, delivery = None, None
                before_version, before_grants = row.version, tuple(row.offered_grants)
                if body.action == "reissue":
                    self._catalog(body.permission_catalog_version)
                    if repo.membership_for_email(store, row.target_email):
                        raise AuthError("MEMBERSHIP_ALREADY_EXISTS", 409)
                    other = repo.pending_for_email(store, row.target_email)
                    if other and other.id != row.id and self.clock() < other.expires_at:
                        raise AuthError("INVITATION_ALREADY_PENDING", 409)
                    if other and other.id != row.id:
                        other.status = "expired"
                        repo.cancel_delivery(other.id)
                        s.flush()
                    repo.cancel_delivery(row.id)
                    row.version, row.status, row.issuer_user_id = str(uuid4()), "pending", actor.user_id
                    row.offered_grants, row.permission_catalog_version = list(body.grants), body.permission_catalog_version
                    row.issued_at, row.expires_at = self.clock(), self.clock()+timedelta(days=7)
                    row.revoked_at, row.reason = None, body.reason
                    delivery = self._issue(s, row)
                    event = invitation_event(s, row, actor=actor.user_id, now=self.clock(), kind="REISSUED",
                        before_version=before_version, before_grants=before_grants, reason=body.reason)
                elif state != "revoked":
                    row.version, row.status, row.revoked_at, row.reason = str(uuid4()), "revoked", self.clock(), body.reason
                    repo.cancel_delivery(row.id)
                    event = invitation_event(s, row, actor=actor.user_id, now=self.clock(), kind="REVOKED",
                        before_version=before_version, before_grants=before_grants, reason=body.reason)
                result = dto.InvitationAction(invitation=self._invitation(row), delivery=delivery,
                    event_id=event.event_id if event else None)
                self._save(s, actor, store, op, kd, fp, result)
            s.commit()
        return result

    def invitations(self, token, store, *, view="invitations", statuses=(), email=None,
                    invitation_id=None, limit=50, cursor=None):
        with auth_session(self.engine) as s:
            actor, summary, _ = self.auth.authorize_in_session(s, token, store, owner_only=True)
            repo = StaffRepository(s)
            if view == "events":
                if invitation_id is None or repo.invitation(invitation_id, store) is None:
                    raise AuthError("RESOURCE_NOT_FOUND", 404)
                items = tuple(dto.InvitationEvent.model_validate(r.record_json) for r in repo.invitation_events(store, invitation_id))
                result_type = dto.InvitationEvents
            else:
                items = tuple(self._invitation(r) for r in repo.invitations(store))
                items = tuple(i for i in items if (not statuses or i.status in statuses) and (email is None or i.target_email == email))
                result_type = dto.InvitationList
            items, page = self._page(items, token, actor, summary,
                [view, sorted(statuses), email, str(invitation_id)], limit, cursor)
            s.commit()
        return result_type(items=items), page

    def _recipient_rate(self, token, ip):
        with auth_session(self.engine) as s:
            user, _ = self.auth._resolve(s, token)
            error = self.auth._rate(s, f"invitation-recipient:{user.id}:{ip}", 30, self.clock())
            s.commit()
        if error:
            raise error

    def _recipient(self, s, token, identifier, raw, csrf=None):
        # Discovery determines lock order only. Validity is rechecked after locks.
        repo, authrepo = StaffRepository(s), AuthRepository(s)
        actor_id = authrepo.session_user(digest(token)) if token else None
        discovered = repo.invitation(identifier)
        issuer_id = discovered.issuer_user_id if discovered else None
        repo.lock_users([i for i in (actor_id, issuer_id) if i is not None])
        user, session = self.auth._resolve(s, token, csrf)
        # Store fence before invitation; shared with Owner mutations.
        store = authrepo.lock_store(discovered.store_id) if discovered else None
        row = repo.invitation(identifier, locked=True)
        if not row or not raw or len(raw.encode()) > 512 or not hmac.compare_digest(row.token_digest, digest(raw)):
            raise AuthError("INVITATION_NOT_FOUND", 404)
        if user.email != row.target_email:
            raise AuthError("INVITATION_ACCOUNT_MISMATCH")
        account = s.get(AuthAccount, user.id)
        if not account.verified_at or not account.verification_reference or account.verified_email != user.email:
            raise AuthError("ACCOUNT_EMAIL_NOT_VERIFIED")
        if row.issuer_user_id != issuer_id:
            raise AuthError("INVITATION_REVISION_CONFLICT", 412)
        if not store or not store.active:
            raise AuthError("PERMISSION_DENIED")
        from app.application.use_cases.auth import Actor
        return Actor(user.id, session.digest), user, store, row

    def _authority(self, s, row):
        repo = AuthRepository(s)
        issuer = repo.user(row.issuer_user_id)
        member = repo.lock_membership(row.store_id, row.issuer_user_id)
        return bool(issuer and issuer.active and member and member.active and member.role == "OWNER")

    def offer(self, token, identifier, raw, ip):
        if not raw or len(raw.encode()) > 512:
            raise AuthError("INVALID_TOKEN", 422)
        self._recipient_rate(token, ip)
        with auth_session(self.engine) as s:
            actor, user, store, row = self._recipient(s, token, identifier, raw)
            state, reasons = self._invitation(row).status, []
            if state == "accepted":
                member = AuthRepository(s).lock_membership(store.id, actor.user_id)
                if not member or not member.active:
                    raise AuthError("PERMISSION_DENIED")
                reasons.append("INVITATION_ALREADY_ACCEPTED")
            elif state != "pending":
                reasons.append("INVITATION_"+state.upper())
            elif not self._authority(s, row):
                reasons.append("INVITATION_AUTHORITY_CHANGED")
            elif StaffRepository(s).membership_for_email(store.id, user.email):
                reasons.append("MEMBERSHIP_ALREADY_EXISTS")
            if row.permission_catalog_version != CATALOG_VERSION:
                reasons.append("PERMISSION_CATALOG_CHANGED")
            result = dto.OfferRead(invitation=dto.InvitationOffer(invitation_id=row.id,
                store=dto.InvitationStore(store_id=store.id, name=store.name), target_email=row.target_email,
                offered_grants=tuple(row.offered_grants), permission_catalog_version=row.permission_catalog_version,
                permission_descriptors=descriptors(row.offered_grants), version=row.version, status=state,
                issued_at=row.issued_at, expires_at=row.expires_at), can_accept=not reasons, reason_codes=tuple(reasons))
            s.commit()
        return result

    def accept(self, token, identifier, body, key, match, csrf, ip, request_id):
        body = dto.AcceptInvitation.model_validate(body.model_dump())
        kd, fp, match = self._request(body, key, match, cas=True)
        self._recipient_rate(token, ip)
        op = f"POST /staff-invitations/{identifier}/accept"
        with auth_session(self.engine) as s:
            actor, user, store, row = self._recipient(s, token, identifier, body.token, csrf or "")
            member = AuthRepository(s).lock_membership(store.id, actor.user_id)
            old = self._old(s, actor, store.id, op, kd, fp)
            if old:
                if not member or not member.active:
                    raise AuthError("PERMISSION_DENIED")
                result, replay = dto.AcceptanceReceipt.model_validate(old), True
            else:
                state = self._invitation(row).status
                if state == "accepted":
                    raise AuthError("INVITATION_ALREADY_ACCEPTED", 409)
                if state in {"expired", "revoked"}:
                    raise AuthError("INVITATION_"+state.upper(), 410)
                if match != row.version:
                    raise AuthError("INVITATION_REVISION_CONFLICT", 412)
                self._catalog(row.permission_catalog_version)
                if not self._authority(s, row):
                    raise AuthError("INVITATION_AUTHORITY_CHANGED", 409)
                if member:
                    raise AuthError("MEMBERSHIP_ALREADY_EXISTS", 409)
                # Revalidate pinned grants, never add composite prerequisites.
                grants = dto.GrantsRequest(grants=tuple(row.offered_grants), reason=row.reason).grants
                member = StoreMembership(id=uuid4(), user_id=user.id, store_id=store.id, role="STAFF")
                s.add(member)
                s.flush()
                StaffRepository(s).replace_grants(member.id, grants)
                s.refresh(member)
                event = permission_event(s, member, actor=user.id, now=self.clock(), reason=row.reason,
                    before=(), before_version=None, after=grants, request_id=request_id,
                    source="INVITATION_ACCEPTANCE", issuer=row.issuer_user_id)
                before = row.version
                row.version, row.status, row.accepted_at = str(uuid4()), "accepted", self.clock()
                invitation_event(s, row, actor=user.id, now=self.clock(), kind="ACCEPTED",
                    before_version=before, before_grants=grants, recipient=user.id, reason=row.reason)
                StaffRepository(s).cancel_delivery(row.id)
                result = dto.AcceptanceReceipt(invitation_id=row.id, invitation_version_at_acceptance=before,
                    store_id=store.id, membership_id=member.id, accepted_grants=grants,
                    authorization_version_at_acceptance=membership_version(member, grants), accepted_at=row.accepted_at,
                    event_id=event.event_id)
                self._save(s, actor, store.id, op, kd, fp, result)
                replay = False
            s.commit()
        return result, replay
