"""Retained permission requests/audits and immutable full-spec mapping submissions."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class PermissionRequestRecord(Base):
    __tablename__ = "permission_requests"
    __table_args__ = (CheckConstraint("state IN ('pending','approved','rejected','cancelled','satisfied','invalidated')", name="ck_permission_request_state"),
        Index("uq_permission_request_pending", "store_id", "requester_membership_id", unique=True, postgresql_where=text("state='pending'")))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    requester_membership_id: Mapped[UUID] = mapped_column(ForeignKey("store_memberships.id", ondelete="RESTRICT"), nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[dict | None] = mapped_column(JSONB)
    approved_permissions: Mapped[list] = mapped_column(JSONB, nullable=False)
    actually_added_permissions: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PermissionRequestAudit(Base):
    __tablename__ = "permission_request_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("permission_requests.id", ondelete="RESTRICT"), nullable=False)
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MappingSubmissionRecord(Base):
    __tablename__ = "mapping_submissions"
    __table_args__ = (CheckConstraint("state IN ('submitted','changes_requested','approved','rejected','stale','withdrawn')", name="ck_mapping_submission_state"),
        Index("uq_mapping_submission_live", "profile_id", unique=True, postgresql_where=text("state='submitted'")))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("import_profiles.id", ondelete="RESTRICT"), nullable=False)
    import_id: Mapped[UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    submitted_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[dict | None] = mapped_column(JSONB)
    reviewed_version: Mapped[str | None] = mapped_column(String(128))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
