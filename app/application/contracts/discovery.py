"""D01/SU01 read projections; availability never implies fabricated facts."""
from typing import Literal, Generic, TypeVar
from datetime import date
from uuid import UUID
from pydantic import AwareDatetime
from app.application.contracts.auth import DTO, Pagination
from app.application.contracts.planning_setup import Version


class DiscoveryMeta(DTO):
    request_id: str
    snapshot_id: Version
    observed_at: AwareDatetime
    pagination: Pagination


class SupplierPickerItem(DTO):
    supplier_id: UUID
    name: str
    active: bool
    version: Version


class SupplierPicker(DTO):
    items: tuple[SupplierPickerItem, ...]


class SupplierPickerEnvelope(DTO):
    data: SupplierPicker
    meta: DiscoveryMeta
    error: None


class SectionSource(DTO):
    resource: str
    version: Version


T=TypeVar('T')
class TodaySection(DTO,Generic[T]):
    availability: Literal['available','empty','unknown','forbidden','unavailable']
    value: T | None
    updated_at: AwareDatetime | None
    completeness: Literal['confirmed','partial','unknown']
    reason_codes: tuple[str,...]
    source: SectionSource | None


class InventoryAttentionItem(DTO):
    ingredient_id: UUID
    status: str
    reason_codes: tuple[str,...]
    usable_quantity: str | None
    unit: str


class InventoryAttention(DTO):
    as_of_date: date
    expired_lot_count: int
    near_expiry_lot_count: int
    low_stock_ingredient_count: int | None
    unknown_assessment_ingredient_count: int
    items: tuple[InventoryAttentionItem,...]
    has_more: bool


class TodayTask(DTO):
    type: Literal['import','mapping_submission','permission_request']
    id: UUID
    state: str
    updated_at: AwareDatetime
    allowed_actions: tuple[str,...]


class TodayTaskList(DTO):
    total_count: int
    items: tuple[TodayTask,...]
    has_more: bool


class LatestRun(DTO):
    run_id: UUID
    status: Literal['queued','running','completed','failed']
    accepted_at: AwareDatetime
    result_digest: Version | None
    outcome: str | None
    error_code: str | None


from app.application.contracts.readiness import Readiness


class TodaySections(DTO):
    inventory: TodaySection[InventoryAttention] | None = None
    imports: TodaySection[TodayTaskList] | None = None
    mapping: TodaySection[TodayTaskList] | None = None
    permissions: TodaySection[TodayTaskList] | None = None
    readiness: TodaySection[Readiness] | None = None
    planning: TodaySection[LatestRun] | None = None


class Today(DTO):
    store_id: UUID
    sections: TodaySections


class TodayMeta(DTO):
    request_id: str
    snapshot_id: Version
    observed_at: AwareDatetime
    as_of_date: date
    timezone: str


class TodayEnvelope(DTO):
    data: Today
    meta: TodayMeta
    error: None
