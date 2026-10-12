"""S3.1 supplied output shapes; no business engine or persistence wiring."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.application.contracts.common import Contract, Metadata, Nonblank, NonnegativeDecimal, Strategy, Unit
from app.application.contracts.decision_execution import Currency, DecisionIssue, DecisionPolicy, VersionOne
from app.domain.decision.validation import exact_equal, service_ratio

Packs = Annotated[int, Field(ge=0, strict=True)]
PathId = Literal['LOW', 'BASE', 'HIGH']


class ProductDemand(Contract):
    product_id: UUID
    day: date
    unit: Unit
    quantity: NonnegativeDecimal


class ProductDemandPath(Contract):
    path_id: PathId
    demands: tuple[ProductDemand, ...]


class BOMContribution(Contract):
    path_id: PathId
    product_id: UUID
    day: date
    recipe_id: UUID
    ingredient_id: UUID
    unit: Unit
    quantity: NonnegativeDecimal


class ProcurementLine(Contract):
    supplier_term_id: UUID
    ingredient_id: UUID
    unit: Unit
    packs: Packs
    quantity: NonnegativeDecimal
    purchase_outlay: NonnegativeDecimal
    arrival_date: date
    expiry_date: date | None


class ProcurementCandidate(Contract):
    strategy: Strategy
    lines: tuple[ProcurementLine, ...]
    purchase_outlay: NonnegativeDecimal
    currency: Currency
    equivalent_to: tuple[Strategy, ...] = ()


class DailyProductFulfillment(Contract):
    product_id: UUID
    day: date
    unit: Unit
    requested: NonnegativeDecimal
    fulfilled: NonnegativeDecimal
    lost_sales: NonnegativeDecimal

    @model_validator(mode='after')
    def conserved(self):
        if self.fulfilled > self.requested or not exact_equal(self.requested, self.fulfilled, self.lost_sales):
            raise ValueError('Fulfillment/lost sales must conserve requested Product demand')
        return self


class DailyIngredientBalance(Contract):
    ingredient_id: UUID
    day: date
    unit: Unit
    opening: NonnegativeDecimal
    arrivals: NonnegativeDecimal
    consumed: NonnegativeDecimal
    shortage: NonnegativeDecimal
    expired: NonnegativeDecimal
    waste: NonnegativeDecimal
    ending_usable: NonnegativeDecimal

    @model_validator(mode='after')
    def conserved(self):
        if not exact_equal(self.opening, self.consumed, self.expired, self.waste,
                           self.ending_usable, self.arrivals.copy_negate()):
            raise ValueError('Ingredient flow must conserve inventory, without double expiry/waste')
        return self


class DecisionMetric(Contract):
    status: Literal['KNOWN', 'UNKNOWN', 'UNDEFINED']
    value: NonnegativeDecimal | None
    unit: Unit
    reason: Nonblank | None = None

    @model_validator(mode='after')
    def missing_is_not_zero(self):
        if self.status == 'KNOWN':
            if self.value is None or self.reason is not None:
                raise ValueError('Known metric needs a value and no missing reason')
        elif self.value is not None or self.reason is None:
            raise ValueError('Missing/undefined metric needs null and a reason')
        return self


class EvaluationMetrics(Contract):
    requested: NonnegativeDecimal
    fulfilled: NonnegativeDecimal
    lost_sales: NonnegativeDecimal
    selling_unit: Unit
    service: DecisionMetric
    purchase_outlay: DecisionMetric
    waste_value: DecisionMetric
    ending_usable_value: DecisionMetric

    @model_validator(mode='after')
    def service_denominator(self):
        if not exact_equal(self.requested, self.fulfilled, self.lost_sales):
            raise ValueError('Metrics must conserve requested quantity')
        ratio = service_ratio(self.fulfilled, self.requested)
        if self.service.unit != 'ratio':
            raise ValueError('Service metric unit must be ratio')
        if ratio is None:
            if self.service.status != 'UNDEFINED':
                raise ValueError('Zero demand service is undefined')
        elif self.service.status != 'KNOWN' or self.service.value != ratio:
            raise ValueError('Service must equal fulfilled/requested at policy precision')
        return self


class CandidatePathEvaluation(Contract):
    strategy: Strategy
    path_id: PathId
    status: Literal['COMPLETE', 'INCOMPLETE', 'HARD_INFEASIBLE']
    products: tuple[DailyProductFulfillment, ...]
    ingredients: tuple[DailyIngredientBalance, ...]
    metrics: EvaluationMetrics | None
    issues: tuple[DecisionIssue, ...]

    @model_validator(mode='after')
    def status_matches_evidence(self):
        hard = any(i.kind == 'HARD_VIOLATION' for i in self.issues)
        if hard != (self.status == 'HARD_INFEASIBLE'):
            raise ValueError('Hard infeasibility must have explicit violation evidence')
        if self.status == 'COMPLETE' and (self.metrics is None or any(i.kind == 'DATA_BLOCKER' for i in self.issues)):
            raise ValueError('Complete evaluation requires metrics and no data blockers')
        return self


class RecommendationEvidence(Contract):
    strategy: Strategy
    path_id: PathId
    metric: Literal['service', 'purchase_outlay', 'waste_value', 'hard_constraints']
    explanation: Nonblank


class DecisionRecommendation(Contract):
    status: Literal['TARGETS_MET', 'BASE_ONLY', 'TARGETS_NOT_MET', 'HARD_INFEASIBLE', 'DATA_BLOCKED', 'EVALUATION_INCOMPLETE']
    strategy: Strategy | None
    evidence: tuple[RecommendationEvidence, ...]
    explanation: Nonblank

    @model_validator(mode='after')
    def blocked_has_no_winner(self):
        if self.status in ('DATA_BLOCKED', 'HARD_INFEASIBLE', 'EVALUATION_INCOMPLETE') and self.strategy is not None:
            raise ValueError('Blocked/hard-infeasible package cannot claim a winner')
        if self.status in ('TARGETS_MET', 'BASE_ONLY') and self.strategy is None:
            raise ValueError('Successful recommendation requires a strategy')
        if self.strategy is not None and not self.evidence:
            raise ValueError('Selected strategy requires business evidence')
        return self


class DecisionPackageV1(Contract):
    package_schema_version: VersionOne = 1
    input_fingerprint: Metadata
    policy: DecisionPolicy
    # Actual producing algorithms, not claims that S3.1 implements these engines.
    bom_version: Metadata
    candidate_version: Metadata
    simulator_version: Metadata
    recommendation_version: Metadata
    paths: tuple[ProductDemandPath, ...]
    bom: tuple[BOMContribution, ...]
    candidates: tuple[ProcurementCandidate, ...]
    evaluations: tuple[CandidatePathEvaluation, ...]
    recommendation: DecisionRecommendation
    issues: tuple[DecisionIssue, ...]
