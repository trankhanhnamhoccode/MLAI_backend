"""Additive import staging. No operational writes or computation in models."""

from datetime import date, datetime
from uuid import UUID
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Boolean,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("id", "store_id", name="uq_import_batch_scope"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    data_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32))
    revision: Mapped[str] = mapped_column(String(128))
    file_set_version: Mapped[str] = mapped_column(String(128))
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_job_id: Mapped[UUID | None] = mapped_column()
    analysis_id: Mapped[UUID | None] = mapped_column()
    mapping_revision: Mapped[str] = mapped_column(String(128))
    analysis_json: Mapped[dict | None] = mapped_column(JSONB)


class ImportFile(Base):
    __tablename__ = "import_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_id", "store_id"],
            ["import_batches.id", "import_batches.store_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["store_id", "digest"],
            ["import_blobs.store_id", "import_blobs.digest"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("import_id", "client_file_id", name="uq_import_file_client"),
        CheckConstraint(
            "upload_status <> 'uploaded' OR digest IS NOT NULL",
            name="ck_import_file_digest",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_id: Mapped[UUID] = mapped_column(index=True)
    store_id: Mapped[UUID] = mapped_column()
    client_file_id: Mapped[UUID] = mapped_column()
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(16))
    digest: Mapped[str | None] = mapped_column(String(71))
    raw_digest: Mapped[str] = mapped_column(String(71))
    size: Mapped[int] = mapped_column(Integer)
    upload_status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(128))
    parse_status: Mapped[str] = mapped_column(String(16))


class ImportBlob(Base):
    __tablename__ = "import_blobs"
    __table_args__ = (
        CheckConstraint(
            "octet_length(content) <= 20971520", name="ck_import_blob_bytes"
        ),
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True
    )
    digest: Mapped[str] = mapped_column(String(71), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class ImportProfile(Base):
    __tablename__ = "import_profiles"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), index=True
    )
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    sheet_id: Mapped[UUID] = mapped_column()
    lifecycle_revision: Mapped[str] = mapped_column(String(128))
    proposal_revision: Mapped[str] = mapped_column(String(128))
    proposal_json: Mapped[dict] = mapped_column(JSONB)
    active_version: Mapped[str | None] = mapped_column(String(128))
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportProfileVersion(Base):
    __tablename__ = "import_profile_versions"
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_profiles.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), index=True
    )
    source_system_key: Mapped[str] = mapped_column(String(128))
    report_type: Mapped[str] = mapped_column(String(128))
    schema_signature: Mapped[str] = mapped_column(String(71), index=True)
    content_digest: Mapped[str] = mapped_column(String(71))
    spec_json: Mapped[dict] = mapped_column(JSONB)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    retired: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportSourceContext(Base):
    __tablename__ = "import_source_contexts"
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True
    )
    source_system_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(128), primary_key=True)
    evidence_reference: Mapped[str] = mapped_column(String(1000))
    approved_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_id", "store_id"],
            ["import_batches.id", "import_batches.store_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_import_job_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_id: Mapped[UUID] = mapped_column(index=True)
    store_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    session_digest: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(16))
    claim: Mapped[UUID | None] = mapped_column()
    executor_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_json: Mapped[dict] = mapped_column(JSONB)
    result_json: Mapped[dict | None] = mapped_column(JSONB)
    error_json: Mapped[dict | None] = mapped_column(JSONB)


class ImportPreview(Base):
    __tablename__ = "import_previews"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"), index=True
    )
    store_id: Mapped[UUID] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    digest: Mapped[str] = mapped_column(String(71))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mapping_revision: Mapped[str] = mapped_column(String(128))
    content_json: Mapped[dict] = mapped_column(JSONB)
    read_set_digest: Mapped[str] = mapped_column(String(71))


class ImportReceipt(Base):
    __tablename__ = "import_receipts"
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(200), primary_key=True)
    key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    record_json: Mapped[dict] = mapped_column(JSONB)


class ImportAudit(Base):
    __tablename__ = "import_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(64))
    record_json: Mapped[dict] = mapped_column(JSONB)
