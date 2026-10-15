"""Detached DEMO normalization, with unresolved facts kept outside runtime contracts."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import StrictBool, model_validator
from app.application.contracts.common import Contract, Nonblank, NonnegativeDecimal
from app.application.contracts.forecast_challenger import Digest


class CellEvidence(Contract):
    file_sha256: Digest
    sheet: Nonblank
    cell: Nonblank
    raw: str | None
    formula: StrictBool = False


class DemoProduct(Contract):
    product_id: UUID
    source_key: Nonblank
    name: Nonblank
    selling_unit: Nonblank
    menu_status: Nonblank
    sources: tuple[CellEvidence, ...]


class DemoSale(Contract):
    product_id: UUID
    sales_date: date
    quantity: NonnegativeDecimal | None
    is_stockout: StrictBool | None
    available_at: None = None
    sources: tuple[CellEvidence, ...]


class DemoCalendar(Contract):
    day: date
    closed: StrictBool | None
    holiday: StrictBool | None
    available_at: None = None
    sources: tuple[CellEvidence, ...]


class DemoDataset(Contract):
    schema_version: Literal[1] = 1
    evidence_class: Literal['DEMO_EXPOSED_POS_GENERATION_UNVERIFIED'] = 'DEMO_EXPOSED_POS_GENERATION_UNVERIFIED'
    identity_kind: Literal['BENCHMARK_SURROGATE_NOT_CANONICAL_DB'] = 'BENCHMARK_SURROGATE_NOT_CANONICAL_DB'
    scope_status: Literal['PROPOSED_FIVE_SINGLE_ITEMS_MENU_UNCHANGED'] = 'PROPOSED_FIVE_SINGLE_ITEMS_MENU_UNCHANGED'
    source_revision: Digest
    store_id: UUID
    timezone: str | None
    products: tuple[DemoProduct, ...]
    sales: tuple[DemoSale, ...]
    calendar: tuple[DemoCalendar, ...]
    # Source workbooks contain no recovered per-fact publication/revision times.
    availability_status: Literal['HISTORICAL_VINTAGES_NOT_ESTABLISHED'] = 'HISTORICAL_VINTAGES_NOT_ESTABLISHED'


class AdmissionDeclarations(Contract):
    schema_version: Literal[1] = 1
    timezone: str | None = None
    accept_five_single_item_scope: StrictBool = False
    observation_availability: Literal['UNDECLARED', 'RETROSPECTIVE_NEXT_RUN_ASSUMPTION'] = 'UNDECLARED'
    source_revision: Digest | None = None

    @model_validator(mode='after')
    def known_zone(self):
        if self.timezone is not None:
            from zoneinfo import ZoneInfo
            ZoneInfo(self.timezone)
        return self


class AdmissionFinding(Contract):
    code: Nonblank
    classification: Literal['CURRENT_FACT', 'PROPOSAL', 'BLOCKER']
    area: Literal['FORECAST_AB', 'FORECAST_C', 'E4', 'DATA', 'IDENTITY']
    detail: Nonblank
    sources: tuple[CellEvidence, ...] = ()
