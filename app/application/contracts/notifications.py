"""Strict NF01--NF03 public DTOs; internal delivery evidence is never exposed."""
from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID
from pydantic import Field, StrictBool
from app.application.contracts.auth import DTO, Pagination, Meta


class NotificationStore(DTO):
    store_id: UUID
    name: str


class NotificationObject(DTO):
    type: Literal["permission_request", "mapping_submission", "membership"]
    id: UUID
    revision: str | None = Field(max_length=256)


class NotificationLink(DTO):
    path: str
    availability: Literal["available", "forbidden", "unavailable"]


class Notification(DTO):
    notification_id: UUID
    recipient_user_id: UUID
    store: NotificationStore | None
    event_id: UUID
    decision_id: UUID | None
    event_type: str
    occurred_at: datetime
    created_at: datetime
    read_at: datetime | None
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    object: NotificationObject
    link: NotificationLink | None
    version: str = Field(min_length=1, max_length=256)


class Inbox(DTO):
    items: tuple[Notification, ...]


class UnreadCount(DTO):
    unread_count: int = Field(ge=0)
    scope: Literal["accessible", "store"]
    store_id: UUID | None


class ReadRequest(DTO):
    read: StrictBool


class ReadState(DTO):
    notification_id: UUID
    read_at: datetime | None
    version: str


class NotificationMeta(DTO):
    request_id: str
    snapshot_id: str = Field(min_length=1, max_length=256)
    observed_at: datetime


class InboxMeta(NotificationMeta):
    pagination: Pagination


T = TypeVar("T")
M = TypeVar("M")


class NotificationEnvelope(DTO, Generic[T, M]):
    data: T
    meta: M
    error: None


class NotificationErrorDetails(DTO):
    """No provider payload or approval/grant hints on this surface."""


class NotificationErrorInfo(DTO):
    code: str
    message: str
    details: NotificationErrorDetails


class NotificationErrorEnvelope(DTO):
    data: None
    meta: Meta
    error: NotificationErrorInfo
