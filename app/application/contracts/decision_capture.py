"""Internal operational capture values; no ORM references or public HTTP contract."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from app.application.contracts.common import Contract, Nonblank, RunStatus
from app.application.contracts.decision_execution import (
    CapturedDecisionProduct, CapturedDecisionIngredient, CapturedRecipe,
    CapturedDecisionConstraint, DecisionPolicy, PreparedDecisionInput,
)
from app.application.contracts.forecast_execution import ForecastExecutionInput, ForecastExecutionPrediction, PreparedForecastInput
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.inventory import InventoryLotResult
from app.application.contracts.supplier import SupplierTermResult
from app.application.contracts.procurement import (
    ProcurementPolicy, ProcurementBudget, ProcurementOffer, SupplierFee,
    IngredientCapacity, SupplierLimit, ProcurementResult,
)
from app.application.contracts.bom import BOMExpansionResult
from app.application.contracts.serving import ServingSimulationResult
from app.application.contracts.procurement_comparison import ProcurementComparisonResult


class InventoryScopeDeclaration(Contract):
    ingredient_id: UUID
    state: Literal['COMPLETE_CURRENT_LOTS', 'CONFIRMED_EMPTY', 'UNKNOWN']
    provenance: Nonblank


class ExplicitProcurementConfiguration(Contract):
    policy: ProcurementPolicy
    offers: tuple[ProcurementOffer, ...]
    budget: ProcurementBudget | None
    supplier_fees: tuple[SupplierFee, ...]
    capacities: tuple[IngredientCapacity, ...]
    supplier_limits: tuple[SupplierLimit, ...]
    capacity_state: Literal['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN']
    supplier_limit_state: Literal['DECLARED', 'EXPLICIT_NOT_CONFIGURED', 'UNKNOWN']
    provenance: Nonblank

    @model_validator(mode='after')
    def declarations(self):
        for state, rows in ((self.capacity_state, self.capacities), (self.supplier_limit_state, self.supplier_limits)):
            if (state == 'DECLARED') != bool(rows):
                raise ValueError('Declared limits need values; unknown/unconfigured must not contain values')
        return self


class OperationalDecisionInput(Contract):
    store_id: UUID
    forecast_run_id: UUID
    product_ids: tuple[UUID, ...]
    cutoff_date: date
    day_start_provenance: Nonblank
    inventory_scope: tuple[InventoryScopeDeclaration, ...]
    committed_inbound_state: Literal['CONFIRMED_NONE', 'PRESENT_UNSUPPORTED', 'UNKNOWN']
    committed_inbound_provenance: Nonblank
    no_additional_orders_provenance: Nonblank
    snapshot_policy: DecisionPolicy
    procurement: ExplicitProcurementConfiguration

    @model_validator(mode='after')
    def explicit_scope(self):
        # Reuse exact Product/horizon/date-overflow boundary; no invented history.
        ForecastExecutionInput(store_id=self.store_id, product_ids=self.product_ids,
                               cutoff_date=self.cutoff_date, history_start_date=self.cutoff_date)
        if len({r.ingredient_id for r in self.inventory_scope}) != len(self.inventory_scope):
            raise ValueError('Duplicate inventory scope declaration')
        object.__setattr__(self, 'product_ids', tuple(sorted(self.product_ids)))
        object.__setattr__(self, 'inventory_scope', tuple(sorted(self.inventory_scope, key=lambda r: r.ingredient_id)))
        return self


class CaptureProblem(Contract):
    code: Nonblank
    kind: Literal['WARNING', 'DATA_BLOCKER']
    entity: Nonblank
    entity_id: UUID | None
    field: Nonblank
    detail: Nonblank
    day: date | None = None


class SourceTime(Contract):
    entity: Nonblank
    entity_id: UUID
    kind: Literal['ROW_CREATED_AT', 'ROW_UPDATED_AT', 'RUN_COMPLETED_AT']
    at: AwareDatetime


class StoreFact(Contract):
    id: UUID
    timezone: Nonblank
    currency: Nonblank


class ScopedPrediction(ForecastExecutionPrediction):
    id: UUID
    store_id: UUID
    forecast_run_id: UUID


class ForecastFact(Contract):
    id: UUID
    store_id: UUID
    status: RunStatus
    training_start_date: date
    training_end_date: date
    forecast_start_date: date
    forecast_end_date: date
    input_fingerprint: Nonblank | None
    model_type: Nonblank
    model_version: Nonblank
    artifact_key: Nonblank | None
    completed_at: AwareDatetime | None
    predictions: tuple[ScopedPrediction, ...]
    retained: PreparedForecastInput | None
    retained_digest: Nonblank | None
    execution: ExecutionDetails | None


class OperationalFacts(Contract):
    """Port result is detached; read() must release all owned DB resources first."""
    captured_at: AwareDatetime
    store: StoreFact | None
    forecast: ForecastFact | None
    products: tuple[CapturedDecisionProduct, ...]
    ingredients: tuple[CapturedDecisionIngredient, ...]
    recipes: tuple[CapturedRecipe, ...]
    lots: tuple[InventoryLotResult, ...]
    supplier_terms: tuple[SupplierTermResult, ...]
    constraints: tuple[CapturedDecisionConstraint, ...]
    source_times: tuple[SourceTime, ...]


class CapturedForecastProvenance(Contract):
    run_id: UUID
    status: RunStatus
    training_start_date: date
    training_end_date: date
    forecast_start_date: date
    forecast_end_date: date
    completed_at: AwareDatetime | None
    retained_input_digest: Nonblank | None
    prediction_units_source: Literal['RETAINED_FORECAST_INPUT_REQUIRED']
    execution: ExecutionDetails | None


class DecisionCaptureOutcome(Contract):
    status: Literal['CAPTURED', 'DATA_BLOCKED']
    request: OperationalDecisionInput
    captured_at: AwareDatetime
    prepared: PreparedDecisionInput | None
    problems: tuple[CaptureProblem, ...]
    source_times: tuple[SourceTime, ...]
    forecast_provenance: CapturedForecastProvenance | None = None
    inventory_time_semantics: Literal['CURRENT_BALANCES_OBSERVED_NOT_HISTORICAL_AS_OF']
    decision_readiness: Literal['NOT_ASSESSED']

    @model_validator(mode='after')
    def outcome(self):
        blocked = any(p.kind == 'DATA_BLOCKER' for p in self.problems)
        if blocked != (self.status == 'DATA_BLOCKED') or (not blocked and self.prepared is None):
            raise ValueError('Capture status must preserve blockers and captured values')
        return self


class OperationalPipelineResult(Contract):
    capture: DecisionCaptureOutcome
    status: Literal['DATA_BLOCKED', 'COMPUTATION_BLOCKED', 'COMPUTED', 'EXECUTION_ERROR']
    bom: BOMExpansionResult | None = None
    serving: ServingSimulationResult | None = None
    procurement: ProcurementResult | None = None
    comparison: ProcurementComparisonResult | None = None
    problems: tuple[CaptureProblem, ...] = ()
    decision_readiness: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'
