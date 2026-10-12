"""Additive auth persistence; no business or cryptographic rules in ORM."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.domain.permissions import PERMISSIONS


class AuthAccount(Base):
    __tablename__ = "auth_accounts"
    __table_args__ = (CheckConstraint("credential_revision >= 1", name="ck_auth_accounts_revision"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    credential_ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_email: Mapped[str] = mapped_column(String(320), nullable=False)
    verification_reference: Mapped[str] = mapped_column(String(1000), nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (CheckConstraint("absolute_expires_at > issued_at AND idle_expires_at > issued_at", name="ck_auth_sessions_expiry"),)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    credential_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    remember_me: Mapped[bool] = mapped_column(Boolean, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CredentialToken(Base):
    __tablename__ = "credential_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('SETUP','RESET') AND revision >= 1", name="ck_credential_tokens_purpose_revision"),)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(5), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MembershipGrant(Base):
    __tablename__ = "membership_grants"
    __table_args__ = (CheckConstraint("permission IN (" + ",".join("'" + k + "'" for k in sorted(PERMISSIONS)) + ")", name="ck_membership_grants_catalogue"),)
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("store_memberships.id", ondelete="RESTRICT"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)


class AuthAudit(Base):
    __tablename__ = "auth_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[UUID | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    operator_reference: Mapped[str | None] = mapped_column(String(200))
    evidence_reference: Mapped[str | None] = mapped_column(String(1000))
    request_reference: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
