"""Canonical N12--N19 request/response values. No caller-declared authority."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field, StrictStr, field_validator
from app.application.contracts.auth import DTO, UserSummary, AuthError, canonical_email
from app.domain.permissions import PERMISSIONS


class PermissionDescriptor(DTO):
    key: str
    group: str
    label_vi: str
    description_vi: str
    grantable_to_staff: bool
    required_with: tuple[str, ...]
    exposure: Literal["ordinary", "cost", "budget"]


class GrantsRequest(DTO):
    grants: tuple[StrictStr, ...] = Field(max_length=len(PERMISSIONS))
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @field_validator("grants")
    @classmethod
    def validate_grants(cls, value):
        if not set(value) <= PERMISSIONS:
            raise AuthError("UNKNOWN_PERMISSION", 422)
        if len(set(value)) != len(value) or tuple(sorted(value)) != value:
            raise ValueError("Grants must be unique and sorted")
        return value

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank reason")
        return value


class CreateInvitation(GrantsRequest):
    email: StrictStr = Field(min_length=1, max_length=320)
    permission_catalog_version: StrictStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        return canonical_email(value)


class ReissueInvitation(GrantsRequest):
    action: Literal["reissue"]
    permission_catalog_version: StrictStr = Field(min_length=1, max_length=128)


class RevokeInvitation(DTO):
    action: Literal["revoke"]
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank reason")
        return value


class AcceptInvitation(DTO):
    token: StrictStr = Field(min_length=1, max_length=512, json_schema_extra={"writeOnly": True})
    accept: Literal[True]

    @field_validator("accept", mode="before")
    @classmethod
    def consent(cls, value):
        if value is not True:
            raise ValueError("Explicit acceptance required")
        return value

    @field_validator("token")
    @classmethod
    def token_bytes(cls, value):
        if len(value.encode()) > 512:
            raise AuthError("INVALID_TOKEN", 422)
        return value


class DeclineInvitation(DTO):
    token: StrictStr = Field(min_length=1, max_length=512, json_schema_extra={"writeOnly": True})
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @field_validator("token")
    @classmethod
    def token_bytes(cls, value):
        if len(value.encode("utf-8")) > 512:
            raise AuthError("INVALID_TOKEN", 422)
        return value

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank reason")
        return value


class StaffMembership(DTO):
    membership_id: UUID
    user: UserSummary
    role: Literal["STAFF"] = "STAFF"
    active: bool
    grants: tuple[str, ...]
    version: str
    updated_at: datetime


class MembershipList(DTO):
    items: tuple[StaffMembership, ...]
    permission_catalog_version: Literal["permissions-v3"] = "permissions-v3"
    permission_catalog: tuple[PermissionDescriptor, ...]


class PermissionUpdate(DTO):
    membership: StaffMembership
    event_id: UUID | None
    changed: bool


class PermissionEvent(DTO):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    event_id: UUID
    store_id: UUID
    target_membership_id: UUID
    actor_user_id: UUID | None
    occurred_at: datetime
    reason: str
    before_grants: tuple[str, ...]
    after_grants: tuple[str, ...]
    before_version: str | None
    after_version: str
    request_id: str
    source: Literal["ASSISTED_PROVISIONING", "OWNER_CHANGE", "INVITATION_ACCEPTANCE", "PERMISSION_REQUEST_APPROVAL"]
    operator_reference: str | None
    issuer_user_id: UUID | None
    permission_request_id: UUID | None = None
    decision_id: UUID | None = None


class PermissionEvents(DTO):
    items: tuple[PermissionEvent, ...]


class DeliveryReceipt(DTO):
    status: Literal["queued", "delivered", "failed"]
    attempt_id: UUID


class Invitation(DTO):
    invitation_id: UUID
    store_id: UUID
    target_email: str
    role: Literal["STAFF"] = "STAFF"
    offered_grants: tuple[str, ...]
    permission_catalog_version: str
    version: str
    status: Literal["pending", "accepted", "revoked", "expired", "declined"]
    issuer_user_id: UUID
    created_at: datetime
    issued_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    declined_at: datetime | None
    reason: str
    delivery_status: Literal["queued", "delivered", "failed"]


class InvitationCreation(DTO):
    invitation: Invitation
    delivery: DeliveryReceipt


class InvitationAction(DTO):
    invitation: Invitation
    delivery: DeliveryReceipt | None
    event_id: UUID | None


class InvitationEvent(DTO):
    event_id: UUID
    invitation_id: UUID
    store_id: UUID
    actor_user_id: UUID | None
    occurred_at: datetime
    kind: Literal["CREATED", "REISSUED", "REVOKED", "ACCEPTED", "DECLINED", "DELIVERY_FAILED", "DELIVERY_SUCCEEDED"]
    reason: str | None
    before_version: str | None
    after_version: str
    before_offered_grants: tuple[str, ...] | None
    after_offered_grants: tuple[str, ...]
    recipient_user_id: UUID | None
    delivery_attempt_id: UUID | None = None


class InvitationList(DTO):
    items: tuple[Invitation, ...]


class InvitationEvents(DTO):
    items: tuple[InvitationEvent, ...]


class InvitationStore(DTO):
    store_id: UUID
    name: str


class InvitationOffer(DTO):
    invitation_id: UUID
    store: InvitationStore
    target_email: str
    role: Literal["STAFF"] = "STAFF"
    offered_grants: tuple[str, ...]
    permission_catalog_version: str
    permission_descriptors: tuple[PermissionDescriptor, ...]
    version: str
    status: Literal["pending", "accepted", "revoked", "expired", "declined"]
    issued_at: datetime
    expires_at: datetime
    declined_at: datetime | None


class OfferRead(DTO):
    invitation: InvitationOffer
    can_accept: bool
    can_decline: bool
    reason_codes: tuple[str, ...]


class AcceptanceReceipt(DTO):
    invitation_id: UUID
    invitation_version_at_acceptance: str
    store_id: UUID
    membership_id: UUID
    role: Literal["STAFF"] = "STAFF"
    accepted_grants: tuple[str, ...]
    authorization_version_at_acceptance: str
    accepted_at: datetime
    event_id: UUID
    next_action: Literal["refresh_store_context"] = "refresh_store_context"


class DeclineReceipt(DTO):
    invitation_id: UUID
    store_id: UUID
    status: Literal["declined"] = "declined"
    declined_at: datetime
    version: str
    event_id: UUID
    next_action: Literal["return_to_stores"] = "return_to_stores"
