"""Internal operational /2. Explicit effective inputs; no API/default resolver."""
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator, model_serializer, ValidationInfo
from app.application.contracts.offer_admission import OfferAdmission
from typing import Annotated
from app.application.contracts.common import Contract, Nonblank, Name, Unit
from app.application.contracts.decision_capture import (
    ExplicitProcurementConfiguration, InventoryScopeDeclaration, OperationalFacts,
    CaptureProblem, CapturedForecastProvenance,
)
from app.application.contracts.decision_execution import DecisionPolicy, PreparedDecisionInput
from app.application.contracts.decision_temporal import OperationalBasis
from app.application.contracts.procurement import ProcurementBudget
from app.application.contracts.procurement_v2 import (
    ProcurementPolicyV2, EffectiveRequirements, ProcurementInputV2, ProcurementResultV2,
)
from app.application.contracts.procurement_selection import ComparisonV2, WinnerSelection
from app.application.contracts.bom import BOMExpansionResult
from app.domain.forecasting.validation import forecast_dates


class ExplicitProcurementConfigurationV2(ExplicitProcurementConfiguration):
    policy: ProcurementPolicyV2
    budget: ProcurementBudget
    budget_ceiling: ProcurementBudget
    budget_version: Nonblank
    payable_fee_coverage: Literal['COMPLETE', 'UNKNOWN']
    payable_fee_coverage_provenance: Nonblank
    offer_admission: OfferAdmission | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy(self,handler):
        result=handler(self)
        if result.get('offer_admission') is None:result.pop('offer_admission',None)
        return result


class OperationalDecisionInputV2(Contract):
    semantics_version: Literal['operational_decision/2']
    store_id: UUID
    forecast_run_id: UUID | None
    cutoff_date: date
    requirements: EffectiveRequirements
    inventory_scope: tuple[InventoryScopeDeclaration, ...]
    committed_inbound_state: Literal['CONFIRMED_NONE', 'PRESENT_UNSUPPORTED', 'UNKNOWN']
    committed_inbound_provenance: Nonblank
    no_additional_orders_provenance: Nonblank
    snapshot_policy: DecisionPolicy
    procurement: ExplicitProcurementConfigurationV2

    @model_validator(mode='after')
    def declarations(self):
        forecast_dates(self.cutoff_date)
        if len({r.ingredient_id for r in self.inventory_scope}) != len(self.inventory_scope):
            raise ValueError('Duplicate inventory completeness declaration')
        object.__setattr__(self, 'inventory_scope', tuple(sorted(self.inventory_scope,key=lambda r:r.ingredient_id)))
        return self


class MenuProduct(Contract):
    store_id: UUID
    product_id: UUID
    name: Name
    selling_unit: Unit
    active: Annotated[bool,Field(strict=True)]


class SupplierTermIdentity(Contract):
    """Scoped identity survives a malformed numeric term, without inventing values."""
    store_id: UUID
    term_id: UUID
    ingredient_id: UUID
    supplier_id: UUID
    version: int | None = Field(default=None,gt=0,strict=True)

    @model_serializer(mode='wrap')
    def preserve_legacy(self,handler):
        result=handler(self)
        if result.get('version') is None:result.pop('version',None)
        return result


class OperationalFactsV2(Contract):
    facts: OperationalFacts
    catalog: tuple[MenuProduct, ...]
    ingredient_scope_ids: tuple[UUID, ...]
    supplier_term_scope: tuple[SupplierTermIdentity, ...]
    problems: tuple[CaptureProblem, ...]


class ProductExclusion(Contract):
    product_id: UUID
    reasons: tuple[CaptureProblem, ...]
    affected_dates: tuple[date, ...]


class OverrideAssessment(Contract):
    product_id: UUID
    path: Literal['LOW','BASE','HIGH']
    status: Literal['COMPUTED_SCOPE', 'NOT_EVALUATED']


class DecisionCaptureOutcomeV2(Contract):
    semantics_version: Literal['operational_capture/2']
    status: Literal['CAPTURED','DATA_BLOCKED','NO_COMPUTABLE_PRODUCTS']
    request: OperationalDecisionInputV2
    captured_at: AwareDatetime
    source: OperationalFactsV2 | None
    operational_basis: OperationalBasis | None
    menu: tuple[MenuProduct, ...]
    computed_product_ids: tuple[UUID, ...]
    exclusions: tuple[ProductExclusion, ...]
    override_assessments: tuple[OverrideAssessment, ...]
    prepared: PreparedDecisionInput | None
    procurement_input: ProcurementInputV2 | None
    problems: tuple[CaptureProblem, ...]
    forecast_provenance: CapturedForecastProvenance | None
    decision_readiness: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'

    @model_validator(mode='after')
    def reconcile(self):
        from app.application.decision_capture_v2_validation import validate_capture_v2
        validate_capture_v2(self)
        return self


class PhaseTiming(Contract):
    # Wall time diagnostics only, never business quantities or proof.
    capture_preparation_seconds: float
    bom_seconds: float
    engine_seconds: float
    comparison_seconds: float
    selector_seconds: float
    output_revalidation_seconds: float
    total_seconds: float
    engine_reported_seconds: float
    engine_overrun_seconds: float

    @model_validator(mode='after')
    def finite_nonnegative(self):
        import math
        if any(not math.isfinite(v) or v < 0 for v in self.model_dump().values()):
            raise ValueError('Phase timings must be finite/nonnegative')
        physical=(self.capture_preparation_seconds,self.bom_seconds,self.engine_seconds,
            self.comparison_seconds,self.selector_seconds,self.output_revalidation_seconds)
        if self.total_seconds<sum(physical):
            raise ValueError('Total timing cannot hide phases')
        return self


class OperationalPipelineResultV2(Contract):
    semantics_version: Literal['operational_pipeline/2']
    capture: DecisionCaptureOutcomeV2
    outcome: Literal['CAPTURE_BLOCKED','NO_COMPUTABLE_PRODUCTS','COMPUTATION_BLOCKED',
        'NUMERIC_UNSUPPORTED','EXECUTION_ERROR','NO_ELIGIBLE_CANDIDATE','RECOMMENDATION_AVAILABLE']
    bom: BOMExpansionResult | None
    procurement: ProcurementResultV2 | None
    comparison: ComparisonV2 | None
    selection: WinnerSelection | None
    problems: tuple[CaptureProblem, ...]
    timing: PhaseTiming
    decision_readiness: Literal['NOT_ASSESSED'] = 'NOT_ASSESSED'

    @model_validator(mode='after')
    def reconcile(self, info: ValidationInfo):
        from app.application.decision_pipeline_v2_validation import validate_pipeline_v2
        validate_pipeline_v2(self, retained=bool(info.context and info.context.get('retained_consistency')))
        return self
