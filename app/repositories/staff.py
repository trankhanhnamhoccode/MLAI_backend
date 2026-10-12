"""Concrete, scoped S4.2 persistence; never commits or closes caller Session."""
from sqlalchemy import select, delete, update
from app.models import User, StoreMembership
from app.models.auth import MembershipGrant
from app.models.staff import StaffInvitation, StaffRequestReceipt, InvitationEventRecord, PermissionEventRecord, InvitationDeliveryIntent


class StaffRepository:
    def __init__(self, session):
        self.session = session

    def lock_users(self, identifiers):
        return self.session.scalars(select(User).where(User.id.in_(set(identifiers))).order_by(User.id).with_for_update()).all()

    def members(self, store_id):
        return self.session.execute(select(StoreMembership, User).join(User, User.id==StoreMembership.user_id)
            .where(StoreMembership.store_id==store_id, StoreMembership.role=="STAFF")
            .order_by(User.display_name, StoreMembership.id).with_for_update(of=StoreMembership)).all()

    def lock_member_id(self, store_id, membership_id):
        return self.session.scalar(select(StoreMembership).where(StoreMembership.store_id==store_id, StoreMembership.id==membership_id).with_for_update())

    def membership_for_email(self, store_id, email):
        return self.session.scalar(select(StoreMembership).join(User, User.id==StoreMembership.user_id).where(StoreMembership.store_id==store_id, User.email==email))

    def replace_grants(self, membership_id, grants):
        existing = set(self.session.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==membership_id)))
        removed, added = existing-set(grants), set(grants)-existing
        if removed:
            self.session.execute(delete(MembershipGrant).where(MembershipGrant.membership_id==membership_id, MembershipGrant.permission.in_(removed)))
        for key in sorted(added):
            self.session.add(MembershipGrant(membership_id=membership_id, permission=key))
        self.session.flush()

    def invitation(self, invitation_id, store_id=None, *, locked=False):
        statement = select(StaffInvitation).where(StaffInvitation.id==invitation_id)
        if store_id is not None:
            statement = statement.where(StaffInvitation.store_id==store_id)
        if locked:
            statement = statement.with_for_update()
        return self.session.scalar(statement.execution_options(populate_existing=True))

    def pending_for_email(self, store_id, email):
        return self.session.scalar(select(StaffInvitation).where(StaffInvitation.store_id==store_id,
            StaffInvitation.target_email==email, StaffInvitation.status=="pending").with_for_update())

    def invitations(self, store_id):
        return self.session.scalars(select(StaffInvitation).where(StaffInvitation.store_id==store_id).order_by(StaffInvitation.issued_at.desc(), StaffInvitation.id)).all()

    def permission_events(self, store_id, membership_id=None):
        statement = select(PermissionEventRecord).where(PermissionEventRecord.store_id==store_id)
        if membership_id is not None:
            statement = statement.where(PermissionEventRecord.membership_id==membership_id)
        return self.session.scalars(statement.order_by(PermissionEventRecord.occurred_at.desc(), PermissionEventRecord.id)).all()

    def invitation_events(self, store_id, invitation_id):
        return self.session.scalars(select(InvitationEventRecord).where(InvitationEventRecord.store_id==store_id,
            InvitationEventRecord.invitation_id==invitation_id).order_by(InvitationEventRecord.occurred_at.desc(), InvitationEventRecord.id)).all()

    def receipt(self, actor_id, store_id, operation, key_digest):
        return self.session.get(StaffRequestReceipt, (actor_id, store_id, operation, key_digest))

    def cancel_delivery(self, invitation_id):
        self.session.execute(update(InvitationDeliveryIntent).where(InvitationDeliveryIntent.invitation_id==invitation_id,
            InvitationDeliveryIntent.status=="queued").values(status="failed", ciphertext=None))

    def lock_intent(self, attempt_id):
        # A pre-read establishes invitation->intent lock order. Refresh after any
        # lock wait, otherwise the identity map could retain an unclaimed row.
        return self.session.scalar(select(InvitationDeliveryIntent).where(InvitationDeliveryIntent.id==attempt_id)
            .with_for_update().execution_options(populate_existing=True))

    def queued_intents(self, now, limit=100):
        return tuple(self.session.scalars(select(InvitationDeliveryIntent.id).where(InvitationDeliveryIntent.status=="queued",
            InvitationDeliveryIntent.claim.is_(None)).order_by(InvitationDeliveryIntent.id).limit(limit)))

    def expired_intents(self, now, limit=100):
        return tuple(self.session.scalars(select(InvitationDeliveryIntent.id).where(
            InvitationDeliveryIntent.ciphertext.is_not(None), InvitationDeliveryIntent.expires_at <= now)
            .order_by(InvitationDeliveryIntent.id).limit(limit)))
