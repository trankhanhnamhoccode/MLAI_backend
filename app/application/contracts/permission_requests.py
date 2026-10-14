from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictStr, field_validator
from app.application.contracts.auth import DTO
from app.application.contracts.staff import PermissionDescriptor
from app.application.contracts.collaboration import Reasoned, Version, NotificationDelivery

Permissions = Annotated[tuple[StrictStr, ...], Field(min_length=1, max_length=43)]
State = Literal["pending", "approved", "rejected", "cancelled", "satisfied", "invalidated"]


class SubmitRequest(Reasoned):
    requested_permissions: Permissions
    permission_catalog_version: Version
    expected_grants_version: Version

    @field_validator("requested_permissions")
    @classmethod
    def canonical(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("DUPLICATE_PERMISSION")
        return tuple(sorted(value))


class ApproveRequest(Reasoned):
    action: Literal["approve"]
    approved_permissions: Permissions
    expected_grants_version: Version
    permission_catalog_version: Version

    @field_validator("approved_permissions")
    @classmethod
    def canonical(cls, value):
        return SubmitRequest.canonical(value)


class CancelRequest(Reasoned):
    action: Literal["cancel"]


class RejectRequest(Reasoned):
    action: Literal["reject"]


class RequestDecision(DTO):
    decision_id: UUID
    actor_user_id: UUID
    reason: str
    decided_at: datetime
    permission_event_id: UUID | None


class PermissionRequest(DTO):
    request_id: UUID
    store_id: UUID
    requester_membership_id: UUID
    requester_user_id: UUID
    requested_permissions: tuple[str, ...]
    grants_at_submission: tuple[str, ...]
    current_grants: tuple[str, ...]
    approved_permissions: tuple[str, ...]
    actually_added_permissions: tuple[str, ...]
    permission_catalog_version: Version
    grants_version_at_submission: Version
    current_grants_version: Version
    version: Version
    state: State
    reason: str
    created_at: datetime
    updated_at: datetime
    decision: RequestDecision | None
    allowed_actions: tuple[str, ...]


class RequestList(DTO):
    items: tuple[PermissionRequest, ...]
    permission_catalog_version: Version
    permission_catalog: tuple[PermissionDescriptor, ...]


class ActionResult(DTO):
    request: PermissionRequest
    notification_delivery: NotificationDelivery
