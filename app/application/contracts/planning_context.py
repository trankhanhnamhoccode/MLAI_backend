"""Exact PLAN4 C01 projection; no public Run execution contract."""
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime
from app.application.contracts.auth import DTO
from app.application.contracts.planning_setup import StoredRequirements,Version
from app.application.contracts.planning_configuration import BudgetCeiling,Validation,Notification
from app.application.contracts.readiness import ScopeEstimate,Readiness


class Defaults(DTO):
    requirements_mode: Literal['default']='default'
    horizon_days: Literal[7]=7
    cutoff_date: date | None
    forecast_start_date: date | None


class ProductBrief(DTO):
    product_id: UUID
    name: str
    selling_unit: str


class Constraints(DTO):
    enum: tuple[str,...] | None=None
    unique: bool | None=None
    max_items: int | None=None
    minimum: str | None=None
    maximum: str | None=None
    max_integer_digits: int | None=None
    max_fraction_digits: int | None=None
    unique_product_id: bool | None=None


class FieldDescriptor(DTO):
    field: str
    type: Literal['decimal_text','path','product_override_array']
    required: bool
    nullable: bool
    constraints: Constraints
    inheritance: str


class Mode(DTO):
    mode: Literal['default','custom','saved']
    availability: Literal['available','unavailable','unknown']
    reason_codes: tuple[str,...]


class Saved(DTO):
    saved_requirement_id: UUID
    name: str
    updated_at: AwareDatetime
    requirements: StoredRequirements
    validation: Validation
    warnings: tuple[Notification,...]


class Capabilities(DTO):
    winner_selection: bool
    saved_requirements: bool
    include_open_purchase_orders: Literal[False]=False
    scenario_based_planning: Literal[False]=False


class PlanningReadiness(DTO):
    status: Literal['ready','not_ready','unknown']
    can_generate: bool
    reason_codes: tuple[str,...]
    evaluated_forecast_start_date: date | None
    scope_estimate: ScopeEstimate | None
    history_watermark: date | None


class Context(DTO):
    store_id: UUID
    currency: str
    timezone: str
    observed_at: AwareDatetime
    context_version: Version
    latest_business_date: date | None
    defaults: Defaults
    supported_horizon_days: tuple[Literal[7],...]=(7,)
    supported_strategies: tuple[Literal['lean','balanced','protected'],...]=('lean','balanced','protected')
    supported_paths: tuple[Literal['LOW','BASE','HIGH'],...]=('LOW','BASE','HIGH')
    default_requirements: StoredRequirements | None
    default_requirements_version: Version | None
    default_requirements_updated_at: AwareDatetime | None
    budget_ceiling: BudgetCeiling | None
    products: tuple[ProductBrief,...]
    custom_requirement_fields: tuple[FieldDescriptor,...] | None
    requirements_modes: tuple[Mode,...]
    saved_requirements: tuple[Saved,...] | None
    capabilities: Capabilities
    readiness: PlanningReadiness


class ContextSourceReadiness(Readiness):
    """Internal null suggestion assessment; R01 keeps its required dates."""
    evaluated_forecast_start_date: date | None
    cutoff_date: date | None
