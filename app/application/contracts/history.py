"""PLAN15.2 and IMP11 accepted history wire, no business recomputation."""
from datetime import date
from typing import Generic,Literal,TypeVar
from uuid import UUID
from pydantic import AwareDatetime
from app.application.contracts.auth import DTO,Pagination
from app.application.contracts.planning_setup import Version
from app.application.contracts.planning_public import OptionId
from app.application.contracts.import_mapping import Notice


class RunCreator(DTO):
    user_id: UUID
    display_name: str | None


class RunSummary(DTO):
    run_id: UUID
    store_id: UUID
    status: Literal['queued','running','completed','failed']
    accepted_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    forecast_start_date: date
    forecast_end_date: date
    requirements_mode: Literal['default','saved','custom']
    created_by: RunCreator
    winner_option_id: OptionId | None
    outcome: str | None
    error_code: str | None
    result_schema_version: str | None
    result_digest: Version | None
    record_version: Version


class RunHistory(DTO):
    items: tuple[RunSummary,...]


class RunHistoryMeta(DTO):
    request_id: str
    snapshot_id: Version
    pagination: Pagination


class RunHistoryEnvelope(DTO):
    data: RunHistory
    meta: RunHistoryMeta
    error: None


ImportStatus=Literal['in_progress','completed','completed_with_warnings','failed']
Category=Literal['sales','inventory','recipes','supplier']


class CalendarDay(DTO):
    date: date
    import_count: int


class ImportCalendar(DTO):
    month: str
    timezone: str
    grouped_by: Literal['imported_at']='imported_at'
    matched_import_count: int
    unfiltered_import_count: int
    days: tuple[CalendarDay,...]


class HistoryMeta(DTO):
    request_id: str
    warnings: tuple[Notice,...] = ()


class ImportHistoryItem(DTO):
    import_id: UUID
    display_number: str
    data_date: date
    imported_at: AwareDatetime
    file_count: int
    status: ImportStatus


class ImportHistory(DTO):
    items: tuple[ImportHistoryItem,...]


class ImportHistoryMeta(HistoryMeta):
    pagination: Pagination
    unfiltered_date_count: int


T=TypeVar('T');M=TypeVar('M')
class HistoryEnvelope(DTO,Generic[T,M]):
    data: T
    meta: M
    error: None
