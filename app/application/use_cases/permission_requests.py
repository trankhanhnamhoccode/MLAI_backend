"""PR01--PR04 own/Owner authority and atomic union through the existing grants boundary."""
import json
from uuid import uuid4
from app.repositories.collaboration import CollaborationRepository
from app.application.contracts.auth import AuthError
from app.application.contracts import permission_requests as dto
from app.application.contracts.collaboration import WorkflowError, NotificationDelivery
from app.application.use_cases.auth import membership_version
from app.application.use_cases.collaboration_paging import mutation_headers, page
from app.application.use_cases.staff import descriptors
from app.domain.permissions import CATALOGUE, CATALOG_VERSION
from app.domain.collaboration import permission_request_state, grant_union
from app.domain.notifications import NotificationEvent, EventType
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.auth_session import auth_session
from app.models import StoreMembership, Store, User
from app.models.collaboration import PermissionRequestRecord, PermissionRequestAudit
from app.models.staff import StaffRequestReceipt
from app.repositories.auth import AuthRepository
from app.repositories.staff import StaffRepository
from app.repositories import notifications


def owners(s, store):
    return CollaborationRepository(s).active_owners(store)


def validate_permissions(keys):
    catalogue = {item.key: item for item in CATALOGUE}
    if not set(keys) <= catalogue.keys():
        raise AuthError("UNKNOWN_PERMISSION", 422)
    if any(not catalogue[key].grantable_to_staff for key in keys):
        raise AuthError("NON_DELEGABLE_PERMISSION", 422)


def effective_state(s, row, member, grants):
    if row.state != "pending":
        return row.state
    user = s.get(User, row.requester_user_id)
    store = s.get(Store, row.store_id)
    return permission_request_state(row.state, tuple(row.facts["requested_permissions"]), grants,
        eligible=member.active and member.role == "STAFF" and user.active and store.active)


def request_audit(s, row, actor, now, kind, reason, request_id, decision_id=None):
    identity = uuid4()
    s.flush()
    s.add(PermissionRequestAudit(id=identity, request_id=row.id, occurred_at=now,
        record=dict(actor_user_id=str(actor) if actor else None, kind=kind, reason=reason,
                    version=row.version, request_id=request_id, decision_id=str(decision_id) if decision_id else None)))
    return identity


def reconcile_member(s, member, now, actor=None, request_id="reconciliation"):
    """Caller holds Store/membership fence; no commit, no grant or notification."""
    grants = AuthRepository(s).grants(member.id)
    for row in CollaborationRepository(s).pending_requests(member.id):
        state = effective_state(s, row, member, grants)
        if state != "pending":
            row.state, row.version, row.updated_at = state, str(uuid4()), now
            request_audit(s, row, actor, now, state.upper(), "Current membership/grants reconciliation", request_id)


class PermissionRequests:
    def __init__(self, staff):
        self.staff, self.auth, self.engine, self.clock = staff, staff.auth, staff.engine, staff.clock

    def _scope(self, s, token, store, csrf=None):
        return self.auth.authorize_in_session(s, token, store, csrf=csrf)

    def _target(self, s, row):
        return StaffRepository(s).lock_member_id(row.store_id, row.requester_membership_id)

    def _row(self, s, identity, store, actor, summary):
        row = CollaborationRepository(s).request(identity, store, None if summary.role == 'OWNER' else actor.user_id)
        if row is None:
            raise AuthError("RESOURCE_NOT_FOUND", 404)
        return row

    def _dto(self, s, row, actor, summary):
        member = self._target(s, row)
        grants = AuthRepository(s).grants(member.id)
        state = effective_state(s, row, member, grants)
        actions = ("approve", "reject") if summary.role == "OWNER" else ("cancel",)
        return dto.PermissionRequest(request_id=row.id, store_id=row.store_id,
            requester_membership_id=row.requester_membership_id, requester_user_id=row.requester_user_id,
            **row.facts, current_grants=grants, current_grants_version=membership_version(member, grants),
            approved_permissions=row.approved_permissions, actually_added_permissions=row.actually_added_permissions,
            version=row.version, state=state, created_at=row.created_at, updated_at=row.updated_at,
            decision=row.decision, allowed_actions=actions if state == "pending" else ())

    def _receipt(self, s, actor, store, op, kd, fp):
        row = s.get(StaffRequestReceipt, (actor.user_id, store, op, kd))
        if row and row.request_digest != fp:
            raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
        return row.record_json if row else None

    def _save(self, s, actor, store, op, kd, fp, result):
        self.staff._save(s, actor, store, op, kd, fp, result)

    def submit(self, token, store, body, key, csrf, request_id):
        kd, _ = mutation_headers(key)
        fp = digest(json.dumps(body.model_dump(mode="json"), sort_keys=True))
        op = f"POST /stores/{store}/permission-requests"
        with auth_session(self.engine) as s:
            actor, summary, _ = self._scope(s, token, store, csrf or "")
            if summary.role != "STAFF":
                raise AuthError("PERMISSION_DENIED")
            member = s.get(StoreMembership, summary.membership_id)
            old = self._receipt(s, actor, store, op, kd, fp)
            if old:
                s.commit()
                return dto.PermissionRequest.model_validate(old)
            if body.permission_catalog_version != CATALOG_VERSION:
                raise AuthError("PERMISSION_CATALOG_CHANGED", 409)
            validate_permissions(body.requested_permissions)
            grants = AuthRepository(s).grants(member.id)
            if body.expected_grants_version != membership_version(member, grants):
                raise AuthError("GRANTS_VERSION_CONFLICT", 409)
            reconcile_member(s, member, self.clock(), actor.user_id, request_id)
            duplicate = CollaborationRepository(s).pending_request(store, member.id)
            if duplicate:
                raise WorkflowError("PERMISSION_REQUEST_ALREADY_PENDING", existing_request_id=duplicate.id)
            if set(body.requested_permissions) <= set(grants):
                raise AuthError("PERMISSIONS_ALREADY_GRANTED", 409)
            now = self.clock()
            row = PermissionRequestRecord(id=uuid4(), store_id=store, requester_membership_id=member.id,
                requester_user_id=actor.user_id, facts=dict(requested_permissions=list(body.requested_permissions),
                    grants_at_submission=list(grants), permission_catalog_version=CATALOG_VERSION,
                    grants_version_at_submission=membership_version(member, grants), reason=body.reason),
                state="pending", version=str(uuid4()), decision=None, approved_permissions=[],
                actually_added_permissions=[], created_at=now, updated_at=now)
            s.add(row)
            event_id = request_audit(s, row, actor.user_id, now, "SUBMITTED", body.reason, request_id)
            recipients = owners(s, store)
            if recipients:
                notifications.enqueue(s, NotificationEvent(event_id, EventType.PERMISSION_SUBMITTED, now, row.id,
                    recipients, store_id=store, object_revision=row.version))
            result = self._dto(s, row, actor, summary)
            self._save(s, actor, store, op, kd, fp, result)
            s.commit()
            return result

    def list(self, token, store, state=None, limit=50, cursor=None):
        with auth_session(self.engine) as s:
            actor, summary, _ = self._scope(s, token, store)
            rows = CollaborationRepository(s).requests(store, None if summary.role == 'OWNER' else actor.user_id)
            all_items = tuple(self._dto(s, row, actor, summary) for row in rows)
            items = tuple(item for item in all_items if state is None or item.state == state)
            items, meta = page(self.auth, token, f"permission-requests:{store}", items, summary.authorization_version,
                [str(store), state], limit, cursor, fingerprint_facts=[CATALOG_VERSION, [i.model_dump(mode="json") for i in all_items]])
            result = dto.RequestList(items=items, permission_catalog_version=CATALOG_VERSION, permission_catalog=descriptors())
            s.commit()
            return result, meta

    def detail(self, token, store, identity):
        with auth_session(self.engine) as s:
            actor, summary, _ = self._scope(s, token, store)
            result = self._dto(s, self._row(s, identity, store, actor, summary), actor, summary)
            s.commit()
            return result

    def action(self, token, store, identity, body, key, match, csrf, request_id):
        kd, expected = mutation_headers(key, match, cas=True)
        fp = digest(json.dumps([body.model_dump(mode="json"), match], sort_keys=True))
        op = f"POST /stores/{store}/permission-requests/{identity}/actions"
        with auth_session(self.engine) as s:
            actor, summary, _ = self._scope(s, token, store, csrf or "")
            row = self._row(s, identity, store, actor, summary)
            member = self._target(s, row)
            if body.action == "cancel":
                if row.requester_user_id != actor.user_id:
                    raise AuthError("PERMISSION_DENIED")
            elif summary.role != "OWNER":
                raise AuthError("PERMISSION_DENIED")
            if not member.active or not s.get(User, member.user_id).active:
                if row.state == "pending":
                    reconcile_member(s, member, self.clock(), actor.user_id, request_id)
                    s.commit()
                raise AuthError("MEMBERSHIP_INACTIVE", 409)
            old = self._receipt(s, actor, store, op, kd, fp)
            if old:
                s.commit()
                return dto.ActionResult.model_validate(old)
            if row.version != expected:
                raise AuthError("PERMISSION_REQUEST_REVISION_CONFLICT", 412)
            current = AuthRepository(s).grants(member.id)
            state = effective_state(s, row, member, current)
            if state != "pending":
                if row.state == "pending":
                    reconcile_member(s, member, self.clock(), actor.user_id, request_id)
                    s.commit()
                raise AuthError("PERMISSION_REQUEST_SATISFIED" if state == "satisfied" and body.action == "approve" else "PERMISSION_REQUEST_STATE_CONFLICT", 409)
            now, decision_id, permission_event = self.clock(), uuid4(), None
            if body.action == "approve":
                if body.permission_catalog_version != CATALOG_VERSION:
                    raise AuthError("PERMISSION_CATALOG_CHANGED", 409)
                validate_permissions(body.approved_permissions)
                if not set(body.approved_permissions) <= set(row.facts["requested_permissions"]):
                    raise AuthError("VALIDATION_ERROR", 422)
                if body.expected_grants_version != membership_version(member, current):
                    raise AuthError("GRANTS_VERSION_CONFLICT", 409)
                union = grant_union(tuple(row.facts["requested_permissions"]), body.approved_permissions, current)
                from app.application.use_cases.staff import change_grants
                permission_event = change_grants(s, member, union.grants,
                    actor=actor.user_id, now=now, reason=body.reason, request_id=request_id,
                    source="PERMISSION_REQUEST_APPROVAL", permission_request_id=row.id, decision_id=decision_id)
                row.approved_permissions, row.actually_added_permissions = list(body.approved_permissions), list(union.added)
            row.state = {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}[body.action]
            row.version, row.updated_at = str(uuid4()), now
            row.decision = dto.RequestDecision(decision_id=decision_id, actor_user_id=actor.user_id,
                reason=body.reason, decided_at=now, permission_event_id=permission_event.event_id if permission_event else None).model_dump(mode="json")
            event_id = request_audit(s, row, actor.user_id, now, row.state.upper(), body.reason, request_id, decision_id)
            if body.action != "cancel":
                notifications.enqueue(s, NotificationEvent(event_id, EventType("permission_request." + row.state), now,
                    row.id, (row.requester_user_id,), store_id=store, object_revision=row.version, decision_id=decision_id))
            result = dto.ActionResult(request=self._dto(s, row, actor, summary), notification_delivery=NotificationDelivery(
                status="not_required" if body.action == "cancel" else "pending", event_id=None if body.action == "cancel" else event_id))
            self._save(s, actor, store, op, kd, fp, result)
            s.commit()
            return result
