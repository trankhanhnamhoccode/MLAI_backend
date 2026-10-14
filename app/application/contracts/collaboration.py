"""Shared C2 transport conventions, not business authority."""
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from pydantic import Field, StrictStr, field_validator, AfterValidator
from app.application.contracts.auth import DTO, Meta, Pagination, AuthError

def version_bytes(value):
    if len(value.encode()) > 256:
        raise ValueError('INVALID_VERSION')
    return value


Version = Annotated[StrictStr, Field(min_length=1, max_length=256), AfterValidator(version_bytes)]


class Reasoned(DTO):
    reason: Annotated[StrictStr, Field(min_length=1, max_length=1000)]

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or len(value.encode()) > 1000:
            raise ValueError("INVALID_REASON")
        return value


class NotificationDelivery(DTO):
    status: Literal["pending", "not_required"]
    event_id: UUID | None


class PageMeta(DTO):
    request_id: str
    pagination: Pagination
    snapshot_id: Version
    observed_at: datetime


T = TypeVar("T")


class PageEnvelope(DTO, Generic[T]):
    data: T
    meta: PageMeta
    error: None


class WorkflowErrorDetails(DTO):
    existing_request_id: UUID | None = None
    existing_submission_id: UUID | None = None
    missing_fields: tuple[str, ...] | None = None
    reason_codes: tuple[str, ...] | None = None


class WorkflowErrorInfo(DTO):
    code: str
    message: str
    details: WorkflowErrorDetails


class WorkflowErrorEnvelope(DTO):
    data: None
    meta: Meta
    error: WorkflowErrorInfo


class WorkflowError(AuthError):
    def __init__(self, code, status=409, **details):
        super().__init__(code, status)
        self.details = WorkflowErrorDetails(**details)
