"""Synchronous auth/application boundary. Never authorizes from caller identity."""
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Engine
from sqlalchemy.orm import Session
from app.repositories.auth import AuthRepository

from app.application.contracts.auth import (
    AuthContext, AuthError, CompletedCredential, CredentialCompletion, LoginRequest,
    MembershipContext, Pagination, SessionSummary, StoreContext, StoreList,
    StoreSummary, UserSummary,
)
from app.domain.permissions import effective_permissions
from app.infrastructure.auth_crypto import HASHER, CursorSigner, digest, new_token, verify_password
from app.infrastructure.database.auth_session import auth_session
from app.models.auth import AuthAccount, AuthSession, AuthAudit


@dataclass(frozen=True)
class Actor:
    """Produced only by authenticated lookup, never accepted from HTTP payload."""
    user_id: UUID
    session_digest: str = field(repr=False)


def now_utc():
    return datetime.now(timezone.utc)


def version(value) -> str:
    return "auth-" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def membership_version(member, grants):
    return version([str(member.id), member.authorization_revision, member.role, member.active, effective_permissions(member.role, grants)])


class AuthUseCases:
    def __init__(self, engine: Engine, clock=now_utc):
        if not isinstance(engine, Engine):
            raise TypeError("Auth requires an owned Engine")
        self.engine, self.clock = engine, clock
        self.cursor_signer = CursorSigner()
        # Equal-cost verification for absent/inactive/unconfigured accounts.
        self._dummy_hash = HASHER.hash(new_token())

    def _audit(self, s, kind, user_id, now):
        s.add(AuthAudit(id=uuid4(), kind=kind, user_id=user_id,
                        request_reference=str(uuid4()), request_digest=digest(kind), occurred_at=now))

    def _rate(self, s, scope, limit, now, *, increment=True, window=timedelta(minutes=15)):
        key = digest(scope)
        row = AuthRepository(s).lock_rate_window(key, now + window)
        if now >= row.expires_at:
            row.attempts, row.expires_at = 0, now + window
        if row.attempts >= limit:
            return AuthError("RATE_LIMITED", 429, max(1, int((row.expires_at-now).total_seconds())))
        if increment:
            row.attempts += 1
        return None

    def login(self, request: LoginRequest, ip: str, previous: str | None = None) -> tuple[AuthContext, str]:
        request = LoginRequest.model_validate(request.model_dump())
        now, secret = self.clock(), new_token()
        error = None
        with auth_session(self.engine) as s:
            # Persistent fixed windows; stable lock order across requests.
            error = self._rate(s, "login-ip:" + ip, 100, now)
            account_key = "login-account:" + request.email + ":" + ip
            error = error or self._rate(s, account_key, 5, now, increment=False)
            if error is None:
                user = AuthRepository(s).lock_user_by_email(request.email)
                account = s.get(AuthAccount, user.id) if user is not None else None
                usable = user is not None and user.active and account is not None and account.credential_ready and account.verified_email == user.email
                correct = verify_password(user.password_hash if usable else self._dummy_hash, request.password)
                if not (usable and correct):
                    self._rate(s, account_key, 5, now)
                    error = AuthError("INVALID_CREDENTIALS", 401)
                else:
                    now = self.clock()
                    if previous:
                        AuthRepository(s).revoke_session(digest(previous), now)
                    row = AuthSession(digest=digest(secret), user_id=user.id, credential_revision=account.credential_revision,
                        csrf_token=new_token(), remember_me=request.remember_me, issued_at=now,
                        idle_expires_at=now + (timedelta(days=7) if request.remember_me else timedelta(minutes=30)),
                        absolute_expires_at=now + (timedelta(days=30) if request.remember_me else timedelta(hours=8)))
                    s.add(row)
                    self._audit(s, "LOGIN", user.id, now)
                    context = self._context(s, user, row)
            s.commit()
        if error:
            raise error
        return context, secret

    def _resolve(self, s, token, csrf=None):
        if not token or len(token.encode()) > 512:
            raise AuthError("UNAUTHENTICATED", 401)
        # User lock first, consistent with reset/login; then session lock.
        uid = AuthRepository(s).session_user(digest(token))
        user = AuthRepository(s).lock_user(uid) if uid else None
        row = AuthRepository(s).lock_session(digest(token))
        account = s.get(AuthAccount, uid) if uid else None
        now = self.clock()
        if not user or not user.active or not account or not account.credential_ready or account.verified_email != user.email or not row or row.revoked_at or row.credential_revision != account.credential_revision or now >= min(row.idle_expires_at, row.absolute_expires_at):
            raise AuthError("UNAUTHENTICATED", 401)
        if csrf is not None and not hmac.compare_digest(row.csrf_token.encode(), csrf.encode()):
            raise AuthError("CSRF_CHECK_FAILED")
        row.idle_expires_at = min(row.absolute_expires_at, now + (timedelta(days=7) if row.remember_me else timedelta(minutes=30)))
        return user, row

    def _memberships(self, s, user_id):
        return AuthRepository(s).accessible_memberships(user_id)

    def _summary(self, s, store, membership):
        grants = AuthRepository(s).grants(membership.id)
        permissions = effective_permissions(membership.role, grants)
        v = membership_version(membership, grants)
        return StoreSummary(store_id=store.id, name=store.name, timezone=store.timezone, currency=store.currency,
                            role=membership.role, membership_id=membership.id, authorization_version=v), permissions

    def _context(self, s, user, row):
        summaries = [self._summary(s, store, member)[0] for store, member in self._memberships(s, user.id)]
        return AuthContext(user=UserSummary(user_id=user.id, email=user.email, display_name=user.display_name),
            session=SessionSummary(expires_at=min(row.idle_expires_at, row.absolute_expires_at), absolute_expires_at=row.absolute_expires_at, csrf_token=row.csrf_token),
            default_store_id=summaries[0].store_id if len(summaries)==1 else None, accessible_store_count=len(summaries),
            authorization_version=version([row.credential_revision, [(str(x.store_id), x.authorization_version) for x in summaries]]))

    def me(self, token: str | None) -> AuthContext:
        with auth_session(self.engine) as s:
            user, row = self._resolve(s, token)
            context = self._context(s, user, row)
            s.commit()
        return context

    def logout(self, token: str | None, csrf: str | None) -> None:
        with auth_session(self.engine) as s:
            try:
                user, row = self._resolve(s, token, csrf or "")
            except AuthError as error:
                if error.status == 401:
                    return
                raise
            row.revoked_at = self.clock()
            self._audit(s, "LOGOUT", user.id, self.clock())
            s.commit()

    def stores(self, token: str | None, limit: int = 50, cursor: str | None = None) -> tuple[StoreList, Pagination]:
        with auth_session(self.engine) as s:
            user, row = self._resolve(s, token)
            items = tuple(self._summary(s, store, member)[0] for store, member in self._memberships(s, user.id))
            fingerprint = version([i.model_dump(mode="json") for i in items])
            offset = 0
            if cursor:
                try:
                    payload, signature = cursor.split(".")
                    expected = self.cursor_signer.sign(token, "stores", payload)
                    if not hmac.compare_digest(expected, signature):
                        raise ValueError()
                    data = json.loads(base64.urlsafe_b64decode(payload))
                    if data["actor"] != str(user.id) or data["fingerprint"] != fingerprint or data["limit"] != limit:
                        raise ValueError()
                    offset = data["offset"]
                    if type(offset) is not int or not 0 < offset < len(items):
                        raise ValueError()
                except (ValueError, KeyError, TypeError):
                    raise AuthError("INVALID_CURSOR", 422) from None
            next_cursor = None
            if offset + limit < len(items):
                payload = base64.urlsafe_b64encode(json.dumps(dict(actor=str(user.id), fingerprint=fingerprint, limit=limit, offset=offset+limit)).encode()).decode()
                next_cursor = payload + "." + self.cursor_signer.sign(token, "stores", payload)
            s.commit()
        return StoreList(items=items[offset:offset+limit]), Pagination(limit=limit, next_cursor=next_cursor, total_count=len(items))

    def authorize_in_session(self, s: Session, token: str | None, store_id: UUID,
                             required: tuple[str, ...] = (), *, owner_only: bool = False,
                             csrf: str | None = None) -> tuple[Actor, StoreSummary, tuple[str, ...]]:
        """Commit fence seam: caller owns transaction, locks retained until commit.

        Future grant/revoke writers MUST lock the same User/Store/membership rows.
        This function does not commit, close, or accept caller-declared roles.
        """
        user, row = self._resolve(s, token, csrf)
        store = AuthRepository(s).lock_store(store_id)
        member = AuthRepository(s).lock_membership(store_id, user.id)
        if not store or not store.active or not member or not member.active:
            raise AuthError("RESOURCE_NOT_FOUND", 404)
        summary, permissions = self._summary(s, store, member)
        if (owner_only and member.role != "OWNER") or not set(required) <= set(permissions):
            raise AuthError("PERMISSION_DENIED")
        return Actor(user.id, row.digest), summary, permissions

    def authorize_resource(self, token: str | None, store_id: UUID, model: type,
                           resource_id: UUID, required: tuple[str, ...] = (), *, owner_only: bool = False) -> Actor:
        """Server-side scoped resource lookup. Trusted composition supplies model."""
        with auth_session(self.engine) as s:
            actor, _, _ = self.authorize_in_session(s, token, store_id, required, owner_only=owner_only)
            if not required and not owner_only:
                raise AuthError("PERMISSION_DENIED")
            found = AuthRepository(s).scoped_resource_id(store_id, model, resource_id)
            if found is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            s.commit()
        return actor

    def store_context(self, token: str | None, store_id: UUID) -> StoreContext:
        with auth_session(self.engine) as s:
            _, summary, permissions = self.authorize_in_session(s, token, store_id)
            now = self.clock()
            result = StoreContext(**summary.model_dump(), server_now=now, as_of_date=now.astimezone(ZoneInfo(summary.timezone)).date(),
                membership=MembershipContext(membership_id=summary.membership_id, role=summary.role,
                    authorization_version=summary.authorization_version, effective_permissions=permissions))
            s.commit()
        return result

    def complete(self, request: CredentialCompletion, ip: str) -> CompletedCredential:
        request = CredentialCompletion.model_validate(request.model_dump())
        now = self.clock()
        with auth_session(self.engine) as s:
            error = self._rate(s, "credential-ip:" + ip, 20, now)
            s.commit()
        if error:
            raise error
        # Read digest only to identify lock order; all validity rechecked under locks.
        with auth_session(self.engine) as s:
            uid = AuthRepository(s).token_user(digest(request.token))
            user = AuthRepository(s).lock_user(uid) if uid else None
            account = s.get(AuthAccount, uid) if uid else None
            token = AuthRepository(s).lock_token(digest(request.token))
            now = self.clock()  # Recheck time after waiting for concurrent locks.
            if not user or not user.active or not account or account.verified_email != user.email or not token or token.consumed_at or now >= token.expires_at or token.revision != account.credential_revision:
                raise AuthError("CREDENTIAL_TOKEN_INVALID", 400)
            user.password_hash = HASHER.hash(request.password)
            token.consumed_at = now
            account.credential_revision += 1
            account.credential_ready = True
            AuthRepository(s).revoke_user_sessions(uid, now)
            self._audit(s, "CREDENTIAL_COMPLETED", uid, now)
            s.commit()
        return CompletedCredential(completed_at=now)
