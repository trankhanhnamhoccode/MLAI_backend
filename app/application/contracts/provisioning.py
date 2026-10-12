"""Operator-only typed application commands; not browser DTOs."""
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import Field, StrictStr, field_validator
from app.application.contracts.auth import DTO, canonical_email


class VerifiedAccountCommand(DTO):
    request_reference: StrictStr = Field(min_length=1, max_length=200)
    evidence_reference: StrictStr = Field(min_length=1, max_length=1000)
    email: StrictStr = Field(min_length=1, max_length=320)
    display_name: StrictStr = Field(min_length=1, max_length=200)
    existing_user_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        return canonical_email(value)

    @field_validator("request_reference", "evidence_reference", "display_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank operator evidence")
        return value


class ProvisionStoreCommand(VerifiedAccountCommand):
    store_name: StrictStr = Field(min_length=1, max_length=200)
    timezone: StrictStr = Field(default="Asia/Ho_Chi_Minh", max_length=64)
    currency: StrictStr = Field(default="VND", pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def timezone_known(cls, value):
        ZoneInfo(value)
        return value

    @field_validator("store_name")
    @classmethod
    def store_nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank Store name")
        return value


class IssueCredentialCommand(DTO):
    user_id: UUID
    purpose: Literal["SETUP", "RESET"]
    request_reference: StrictStr = Field(min_length=1, max_length=200)
    evidence_reference: StrictStr = Field(min_length=1, max_length=1000)
    verified_email: StrictStr

    @field_validator("verified_email")
    @classmethod
    def email_shape(cls, value):
        return canonical_email(value)

    @field_validator("request_reference", "evidence_reference")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank operator evidence")
        return value


class ProvisionReceipt(DTO):
    user_id: UUID
    store_id: UUID | None
    audit_id: UUID


class DeliveryReceipt(DTO):
    audit_id: UUID
    status: Literal["delivered", "failed"]
