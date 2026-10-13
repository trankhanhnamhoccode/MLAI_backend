"""Concrete auth persistence. Caller owns transaction/commit and authorization."""
from uuid import UUID
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert
from app.models import User, Store, StoreMembership
from app.models.auth import AuthAccount, AuthAudit, AuthRateLimit, AuthSession, CredentialToken, MembershipGrant


class AuthRepository:
    def __init__(self, session):
        self.session = session

    def lock_rate_window(self, key, expires_at):
        self.session.execute(insert(AuthRateLimit).values(key=key, attempts=0, expires_at=expires_at).on_conflict_do_nothing())
        return self.session.scalar(select(AuthRateLimit).where(AuthRateLimit.key == key).with_for_update())

    def lock_user_by_email(self, email):
        return self.session.scalar(select(User).where(User.email == email).with_for_update())

    def lock_user(self, user_id):
        return self.session.scalar(select(User).where(User.id == user_id).with_for_update())

    def user(self, user_id):
        return self.session.get(User, user_id)

    def account(self, user_id: UUID) -> AuthAccount | None:
        return self.session.get(AuthAccount, user_id)

    def lock_account(self, user_id: UUID) -> AuthAccount | None:
        return self.session.scalar(select(AuthAccount).where(AuthAccount.user_id == user_id)
            .with_for_update().execution_options(populate_existing=True))

    def session_user(self, digest):
        return self.session.scalar(select(AuthSession.user_id).where(AuthSession.digest == digest))

    def lock_session(self, digest):
        return self.session.scalar(select(AuthSession).where(AuthSession.digest == digest).with_for_update())

    def revoke_session(self, digest, now):
        self.session.execute(update(AuthSession).where(AuthSession.digest == digest).values(revoked_at=now))

    def revoke_user_sessions(self, user_id, now):
        self.session.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))

    def accessible_memberships(self, user_id):
        return self.session.execute(select(Store, StoreMembership).join(StoreMembership, StoreMembership.store_id == Store.id)
            .where(StoreMembership.user_id == user_id, StoreMembership.active.is_(True), Store.active.is_(True))
            .order_by(Store.name, Store.id).with_for_update(of=(Store, StoreMembership))).all()

    def grants(self, membership_id):
        return tuple(self.session.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id == membership_id).order_by(MembershipGrant.permission)))

    def lock_store(self, store_id):
        return self.session.scalar(select(Store).where(Store.id == store_id).with_for_update())

    def lock_membership(self, store_id, user_id):
        return self.session.scalar(select(StoreMembership).where(StoreMembership.store_id == store_id,
            StoreMembership.user_id == user_id).with_for_update())

    def scoped_resource_id(self, store_id, model, resource_id):
        return self.session.scalar(select(model.id).where(model.id == resource_id, model.store_id == store_id))

    def token_user(self, digest):
        return self.session.scalar(select(CredentialToken.user_id).where(CredentialToken.digest == digest))

    def lock_token(self, digest):
        return self.session.scalar(select(CredentialToken).where(CredentialToken.digest == digest).with_for_update())

    def lock_operator_request(self, reference, key):
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        return self.audit_by_reference(reference)

    def audit_by_reference(self, reference):
        return self.session.scalar(select(AuthAudit).where(AuthAudit.request_reference == reference))

    def user_id_by_email(self, email):
        return self.session.scalar(select(User.id).where(User.email == email))

    def invalidate_user_tokens(self, user_id, now):
        self.session.execute(update(CredentialToken).where(CredentialToken.user_id == user_id, CredentialToken.consumed_at.is_(None)).values(consumed_at=now))

    def invalidate_token(self, digest, now):
        self.session.execute(update(CredentialToken).where(CredentialToken.digest == digest).values(consumed_at=now))
