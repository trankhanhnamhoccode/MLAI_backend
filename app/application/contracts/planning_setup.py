"""Planning-contract/1 boundary and detached config values; no storage or HTTP."""
from datetime import date, timedelta
from decimal import Decimal
import re
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BeforeValidator, Field, field_validator, model_serializer, model_validator
from app.application.contracts.common import Contract, Name, Nonblank
from app.application.contracts.decision_capture_v2 import MenuProduct
from app.application.contracts.procurement import ProcurementBudget
from app.application.contracts.procurement_v2 import EffectiveRequirements, ProcurementPolicyV2

Version = Annotated[str, Field(strict=True, min_length=1, max_length=128)]
PathId = Literal['LOW', 'BASE', 'HIGH']


def decimal_text(value, *, percent):
    if not isinstance(value, str) or re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?', value) is None:
        raise ValueError('Supply unsigned plain decimal text')
    whole, _, fraction = value.partition('.')
    if len(whole) > (3 if percent else 18) or len(fraction) > (32 if percent else 18):
        raise ValueError('Decimal text exceeds digit limits')
    if percent and Decimal(value) > 100:
        raise ValueError('Percentage exceeds 100')
    return value


PercentText = Annotated[str, BeforeValidator(lambda v: decimal_text(v, percent=True)), Field(pattern=r'^(0|[1-9][0-9]*)(\.[0-9]+)?$',min_length=1,max_length=36)]
MoneyText = Annotated[str, BeforeValidator(lambda v: decimal_text(v, percent=False)), Field(pattern=r'^(0|[1-9][0-9]*)(\.[0-9]+)?$',min_length=1,max_length=37)]


def resource_id(value):
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('Supply canonical lower-case UUID')
    return UUID(value)


ResourceId = Annotated[UUID, BeforeValidator(resource_id)]


def business_date(value):
    if type(value) is date:
        return value
    if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is None:
        raise ValueError('Supply YYYY-MM-DD business date')
    return date.fromisoformat(value)


BusinessDate = Annotated[date, BeforeValidator(business_date)]


class PresenceContract(Contract):
    """Preserve omission through instance revalidation and retained serialization."""
    @model_validator(mode='wrap')
    @classmethod
    def retained_presence(cls, value, handler):
        if isinstance(value, cls):
            value = value.model_dump(round_trip=True)
        return handler(value)

    @model_serializer(mode='wrap')
    def preserve_omission(self, handler):
        result = handler(self)
        for field in type(self).model_fields:
            if field not in self.model_fields_set and getattr(self, field) is None:
                result.pop(field, None)
        return result


class ProductOverride(Contract):
    product_id: ResourceId
    min_fill_rate_percent: PercentText


class CustomPath(PresenceContract):
    path: PathId
    min_fill_rate_percent: PercentText | None = None
    product_overrides: Annotated[tuple[ProductOverride, ...], Field(max_length=50)] | None = None

    @field_validator('min_fill_rate_percent', 'product_overrides', mode='before')
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError('Field cannot be null; omit it to inherit')
        return value

    @model_validator(mode='after')
    def presence(self):
        for field in ('min_fill_rate_percent', 'product_overrides'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(field + ' cannot be null')
        if self.product_overrides is not None and len({o.product_id for o in self.product_overrides}) != len(self.product_overrides):
            raise ValueError('Duplicate Product override')
        return self


class CustomRequirements(PresenceContract):
    paths: Annotated[tuple[CustomPath, ...], Field(min_length=1, max_length=3)]
    budget_limit: MoneyText | None = None

    @model_validator(mode='after')
    def unique(self):
        if len({p.path for p in self.paths}) != len(self.paths):
            raise ValueError('Duplicate path')
        return self


class PlanningRequest(PresenceContract):
    requirements_mode: Literal['default', 'custom', 'saved']
    forecast_start_date: BusinessDate
    default_requirements_version: Version | None = None
    requirements: CustomRequirements | None = None
    saved_requirement_id: ResourceId | None = None

    @field_validator('default_requirements_version', 'saved_requirement_id', 'requirements', mode='before')
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError('Field cannot be null')
        return value

    @field_validator('forecast_start_date')
    @classmethod
    def horizon(cls, value):
        try:
            value - timedelta(days=1)
            value + timedelta(days=6)
        except OverflowError as error:
            raise ValueError('Seven-day forecast date range overflows') from error
        return value

    @model_validator(mode='after')
    def mode_fields(self):
        fields = self.model_fields_set
        for field in ('default_requirements_version', 'saved_requirement_id', 'requirements'):
            if field in fields and getattr(self, field) is None:
                raise ValueError(field + ' cannot be null')
        if self.requirements_mode == 'custom':
            if self.requirements is None or 'saved_requirement_id' in fields:
                raise ValueError('Custom requires requirements and forbids saved ID')
        elif self.requirements_mode == 'saved':
            if self.saved_requirement_id is None or 'requirements' in fields:
                raise ValueError('Saved requires saved ID and forbids requirements')
        elif 'requirements' in fields or 'saved_requirement_id' in fields:
            raise ValueError('Default forbids requirements and saved ID')
        # D = start - 1 and end = start + 6, never datetime coercion or wraparound.
        try:
            self.forecast_start_date - timedelta(days=1)
            self.forecast_start_date + timedelta(days=6)
        except OverflowError as error:
            raise ValueError('Seven-day forecast date range overflows') from error
        return self


class StoredPath(Contract):
    path: PathId
    min_fill_rate_percent: PercentText
    product_overrides: Annotated[tuple[ProductOverride, ...], Field(max_length=50)]

    @model_validator(mode='after')
    def unique(self):
        if len({o.product_id for o in self.product_overrides}) != len(self.product_overrides):
            raise ValueError('Duplicate stored Product override')
        return self


class StoredRequirements(Contract):
    """Fully resolved thresholds/overrides; budget null alone remains late-bound."""
    paths: Annotated[tuple[StoredPath, ...], Field(min_length=1, max_length=3)]
    budget_limit: MoneyText | None

    @model_validator(mode='after')
    def unique(self):
        if len({p.path for p in self.paths}) != len(self.paths):
            raise ValueError('Duplicate stored path')
        return self


class DefaultRequirementsRecord(Contract):
    version: Version
    updated_at: AwareDatetime | None
    requirements: StoredRequirements


class SavedRequirementsRecord(Contract):
    store_id: UUID
    saved_requirement_id: UUID
    version: Version
    name: Name
    updated_at: AwareDatetime | None
    requirements: StoredRequirements


class BudgetCeilingRecord(Contract):
    amount: MoneyText
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    version: Version
    updated_at: AwareDatetime | None
    provenance: Nonblank


class PlanningConfiguration(Contract):
    """Already-read bundle, not a DB loader or guarantee of transactional reads."""
    store_id: UUID
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    timezone: Nonblank
    read_at: AwareDatetime
    configuration_version: Version
    provenance: Nonblank
    consistency: Literal['SINGLE_SNAPSHOT_DECLARED', 'UNSPECIFIED']
    defaults: DefaultRequirementsRecord | None
    budget_ceiling: BudgetCeilingRecord | None
    saved: SavedRequirementsRecord | None
    products: tuple[MenuProduct, ...]
    policy: ProcurementPolicyV2

    @model_validator(mode='after')
    def coherent(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('Unknown IANA Store timezone') from error
        if len({p.product_id for p in self.products}) != len(self.products):
            raise ValueError('Duplicate Product configuration reference')
        if any(p.store_id != self.store_id for p in self.products):
            raise ValueError('Configuration Product belongs to another Store')
        if self.budget_ceiling and self.budget_ceiling.currency != self.currency:
            raise ValueError('Budget ceiling currency conflicts with Store')
        for record in (self.defaults, self.saved, self.budget_ceiling):
            if record and record.updated_at and record.updated_at > self.read_at:
                raise ValueError('Configuration update occurs after read time')
        return self


class PlanningFieldError(Contract):
    code: Nonblank
    field: Nonblank
    message: Nonblank


class PlanningWarning(Contract):
    code: Literal['DEFAULT_CHANGED_SINCE_SAVED_UPDATE', 'DEFAULT_CHANGE_HISTORY_UNKNOWN']
    field: Literal['saved_requirement_id']
    default_updated_at: AwareDatetime | None
    saved_updated_at: AwareDatetime | None


class DefaultReference(Contract):
    version: Version
    updated_at: AwareDatetime | None


class SavedReference(Contract):
    saved_requirement_id: UUID
    version: Version
    updated_at: AwareDatetime | None


class ResolvedPlanningSetup(Contract):
    semantics_version: Literal['planning_resolution/1']
    request: PlanningRequest
    configuration: PlanningConfiguration
    requirements: EffectiveRequirements
    budget: ProcurementBudget
    budget_ceiling: ProcurementBudget
    budget_version: Version
    default_reference: DefaultReference | None
    saved_reference: SavedReference | None
    warnings: tuple[PlanningWarning, ...]
    cutoff_date: date
    forecast_end_date: date
    # Configuration read time is not durable acceptance, auth or public readiness.
    decision_readiness: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'

    @model_validator(mode='after')
    def reconcile(self):
        from app.application.use_cases.planning_setup import _project, ResolutionRejected
        try:
            expected = _project(self.request, self.configuration)
        except ResolutionRejected as error:
            raise ValueError('Resolved setup has invalid source/request') from error
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise ValueError('Resolved setup differs from retained inputs: ' + field)
        return self


class PlanningResolutionOutcome(Contract):
    status: Literal['RESOLVED', 'INVALID']
    resolution: ResolvedPlanningSetup | None
    errors: tuple[PlanningFieldError, ...]

    @model_validator(mode='after')
    def coherent(self):
        if (self.status == 'RESOLVED') != (self.resolution is not None) or bool(self.errors) != (self.status == 'INVALID'):
            raise ValueError('Resolution outcome inconsistent')
        return self
