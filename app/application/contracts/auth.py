"""Strict public DTOs for the six S4.1 routes."""
import re
from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator, model_serializer


def canonical_email(value: str) -> str:
    value = value.strip().lower()
    if not 1 <= len(value) <= 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("INVALID_EMAIL")
    return value


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    def __repr_args__(self):
        return [(key, value) for key, value in super().__repr_args__() if key not in {"password", "token"}]


class LoginRequest(DTO):
    email: StrictStr = Field(min_length=1, max_length=320)
    password: StrictStr = Field(min_length=1, max_length=128, json_schema_extra={"format": "password", "writeOnly": True})
    remember_me: StrictBool = False

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        return canonical_email(value)


class CredentialCompletion(DTO):
    token: StrictStr = Field(min_length=1, max_length=512, json_schema_extra={"writeOnly": True})
    password: StrictStr = Field(min_length=12, max_length=128, json_schema_extra={"format": "password", "writeOnly": True})

    @field_validator("password", "token")
    @classmethod
    def byte_limit(cls, value: str, info) -> str:
        if len(value.encode("utf-8")) > (1024 if info.field_name == "password" else 512):
            raise ValueError("PASSWORD_POLICY_VIOLATION" if info.field_name == "password" else "VALIDATION_ERROR")
        return value


class UserSummary(DTO):
    user_id: UUID
    email: str
    display_name: str


class SessionSummary(DTO):
    expires_at: datetime
    absolute_expires_at: datetime
    csrf_token: str


class AuthContext(DTO):
    user: UserSummary
    session: SessionSummary
    default_store_id: UUID | None
    accessible_store_count: int
    authorization_version: str


class StoreSummary(DTO):
    store_id: UUID
    name: str
    timezone: str
    currency: str
    role: Literal["OWNER", "STAFF"]
    membership_id: UUID
    authorization_version: str


class MembershipContext(DTO):
    membership_id: UUID
    role: Literal["OWNER", "STAFF"]
    authorization_version: str
    effective_permissions: tuple[str, ...]


class StoreContext(StoreSummary):
    active: Literal[True] = True
    server_now: datetime
    as_of_date: date
    membership: MembershipContext
    permission_catalog_version: Literal["permissions-v3"] = "permissions-v3"


class StoreList(DTO):
    items: tuple[StoreSummary, ...]


class CompletedCredential(DTO):
    next_action: Literal["login"] = "login"
    completed_at: datetime


class Pagination(DTO):
    limit: int
    next_cursor: str | None
    total_count: int | None


class Meta(DTO):
    request_id: str
    pagination: Pagination | None = None

    @model_serializer(mode="wrap")
    def without_absent_pagination(self, serializer):
        result = serializer(self)
        if self.pagination is None:
            result.pop("pagination", None)
        return result


T = TypeVar("T")


class Envelope(DTO, Generic[T]):
    data: T
    meta: Meta
    error: None


class ErrorDetails(DTO):
    approval_request_allowed: Literal[False] = False


class ErrorInfo(DTO):
    code: str
    message: str
    details: ErrorDetails


class ErrorEnvelope(DTO):
    data: None
    meta: Meta
    error: ErrorInfo


class AuthError(Exception):
    def __init__(self, code: str, status: int = 403, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after
