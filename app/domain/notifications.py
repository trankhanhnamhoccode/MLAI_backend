"""Versioned immutable facts, fixed safe templates; no infrastructure dependencies."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID


class EventType(StrEnum):
    PERMISSION_SUBMITTED = "permission_request.submitted"
    PERMISSION_APPROVED = "permission_request.approved"
    PERMISSION_REJECTED = "permission_request.rejected"
    MAPPING_SUBMITTED = "mapping_submission.submitted"
    MAPPING_APPROVED = "mapping_submission.approved"
    MAPPING_REJECTED = "mapping_submission.rejected"
    MAPPING_CHANGES_REQUESTED = "mapping_submission.changes_requested"
    GRANTS_CHANGED = "membership.grants_changed"


TEMPLATES = MappingProxyType({
    EventType.PERMISSION_SUBMITTED: ("Có yêu cầu quyền mới", "Một nhân viên gửi yêu cầu quyền tại quán."),
    EventType.PERMISSION_APPROVED: ("Yêu cầu quyền đã được duyệt", "Mở yêu cầu để kiểm tra kết quả và quyền hiện hành."),
    EventType.PERMISSION_REJECTED: ("Yêu cầu quyền đã bị từ chối", "Mở yêu cầu để kiểm tra kết quả."),
    EventType.MAPPING_SUBMITTED: ("Có profile cần duyệt", "Một nhân viên gửi profile để review tại quán."),
    EventType.MAPPING_APPROVED: ("Profile đã được duyệt", "Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập."),
    EventType.MAPPING_REJECTED: ("Profile đã bị từ chối", "Mở submission để kiểm tra kết quả review."),
    EventType.MAPPING_CHANGES_REQUESTED: ("Profile cần chỉnh sửa", "Mở submission để kiểm tra yêu cầu chỉnh sửa."),
    EventType.GRANTS_CHANGED: ("Quyền tại quán đã thay đổi", "Mở quán để kiểm tra quyền hiện hành."),
})


@dataclass(frozen=True)
class NotificationEvent:
    event_id: UUID
    event_type: EventType
    occurred_at: datetime
    object_id: UUID
    recipients: tuple[UUID, ...]
    store_id: UUID | None = None
    object_revision: str | None = None
    decision_id: UUID | None = None
    payload_version: int = 1

    def __post_init__(self):
        ids = (self.event_id, self.object_id, *self.recipients)
        if not isinstance(self.event_type, EventType) or type(self.payload_version) is not int or self.payload_version != 1:
            raise ValueError("INVALID_NOTIFICATION_PAYLOAD")
        if not isinstance(self.recipients, tuple) or not self.recipients or len(set(self.recipients)) != len(self.recipients):
            raise ValueError("INVALID_NOTIFICATION_RECIPIENTS")
        if any(not isinstance(i, UUID) for i in ids):
            raise ValueError("INVALID_NOTIFICATION_ID")
        if any(i is not None and not isinstance(i, UUID) for i in (self.store_id, self.decision_id)):
            raise ValueError("INVALID_NOTIFICATION_ID")
        if self.event_type.value.rsplit(".", 1)[1] in {"approved", "rejected", "changes_requested"} and self.decision_id is None:
            raise ValueError("NOTIFICATION_DECISION_REQUIRED")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.utcoffset() is None:
            raise ValueError("INVALID_NOTIFICATION_TIME")
        if self.object_revision is not None and (not isinstance(self.object_revision, str) or not 1 <= len(self.object_revision.encode()) <= 256):
            raise ValueError("INVALID_NOTIFICATION_REVISION")

    @property
    def object_type(self):
        return self.event_type.value.split(".")[0]


def retry_delay(attempt: int) -> int:
    if attempt < 1:
        raise ValueError("INVALID_ATTEMPT")
    return (1, 5, 30, 60)[attempt - 1] if attempt <= 4 else 300
