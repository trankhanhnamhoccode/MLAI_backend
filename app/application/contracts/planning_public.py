"""Exact PLAN5/9 public wire. Internal solver/aggregate types stay private."""
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Annotated,Literal,Generic,TypeVar
from uuid import UUID
from pydantic import AwareDatetime,Field,model_serializer,model_validator
from app.application.contracts.auth import DTO
from app.application.contracts.planning_setup import PlanningRequest,StoredRequirements,MoneyText,PercentText,Version
from app.application.contracts.decision_temporal import OperationalBasis

Strategy=Literal['lean','balanced','protected']
Path=Literal['LOW','BASE','HIGH']
CountText=Annotated[str,Field(strict=True,pattern=r'^(0|[1-9][0-9]*)$')]
DecimalText=Annotated[str,Field(strict=True,pattern=r'^(0|[1-9][0-9]*)(\.[0-9]+)?$')]
OptionId=Annotated[str,Field(strict=True,min_length=1,max_length=128)]


class PlanningNotificationDetails(DTO):
    field: str | None=None
    entity: str | None=None
    entity_id: UUID | None=None
    affected_dates: tuple[date,...] | None=None
    ingredient_ids: tuple[UUID,...] | None=None
    default_updated_at: AwareDatetime | None=None
    saved_updated_at: AwareDatetime | None=None
    classification: str | None=None
    proof_scope: str | None=None
    suggested_action: str | None=None

    @model_serializer(mode='wrap')
    def present(self,handler):
        return {k:v for k,v in handler(self).items() if v is not None}


class PlanningNotification(DTO):
    code: str
    message: str
    details: PlanningNotificationDetails=Field(default_factory=PlanningNotificationDetails)


class Accepted(DTO):
    run_id: UUID
    status: Literal['queued','running','completed','failed']
    accepted_at: AwareDatetime


class PollMeta(DTO):
    warnings: tuple[PlanningNotification,...]
    poll_after_ms: Literal[0,2000]


T=TypeVar('T')
class PlanningEnvelope(DTO,Generic[T]):
    data: T
    meta: PollMeta
    error: None


class ExactQuantity(DTO):
    numerator: Annotated[str,Field(strict=True,pattern=r'^(0|[1-9][0-9]*)$',max_length=1000)]
    denominator: Annotated[str,Field(strict=True,pattern=r'^[1-9][0-9]*$',max_length=1000)]
    decimal_view: DecimalText

    @model_validator(mode='after')
    def canonical(self):
        from app.domain.decision.quantities import display
        f=Fraction(int(self.numerator),int(self.denominator))
        if (str(f.numerator),str(f.denominator))!=(self.numerator,self.denominator) or Decimal(self.decimal_view)!=display(f):
            raise ValueError('Quantity must preserve reduced exact fraction and Decimal50 view')
        return self


class Service(DTO):
    numerator: CountText
    denominator: Annotated[str,Field(strict=True,pattern=r'^[1-9][0-9]*$')]
    percent_view: DecimalText

    @model_validator(mode='after')
    def canonical(self):
        from app.domain.decision.quantities import display
        f=Fraction(int(self.numerator),int(self.denominator))
        if f>1 or (str(f.numerator),str(f.denominator))!=(self.numerator,self.denominator) or Decimal(self.percent_view)!=display(f*100):
            raise ValueError('Service must preserve exact reduced ratio and percentage view')
        return self


class BudgetAtAcceptance(DTO):
    limit: MoneyText
    currency: str
    ceiling_at_acceptance: MoneyText
    ceiling_version: Version


class PlanningSavedReference(DTO):
    id: UUID
    version: Version
    updated_at: AwareDatetime


class RunConfiguration(DTO):
    requirements_mode: Literal['default','custom','saved']
    effective_requirements: StoredRequirements
    budget: BudgetAtAcceptance
    default_version: Version | None
    saved_reference: PlanningSavedReference | None
    policy_version: Literal['procurement_api_policy/1']='procurement_api_policy/1'


class ForecastView(DTO):
    forecast_run_id: UUID
    input_digest: str
    model_type: str
    model_version: str
    artifact_identity: str | None
    start_date: date
    end_date: date
    history_start_date: date | None
    history_end_date: date | None
    training_start_date: date | None
    training_end_date: date | None
    reused: bool
    quality_status: Literal['not_evaluated','evaluated']
    warnings: tuple[PlanningNotification,...]


class PlanningProductBrief(DTO):
    product_id: UUID
    name: str
    selling_unit: str


class ExcludedOverride(DTO):
    path: Path
    target_percent: PercentText
    status: Literal['NOT_EVALUATED']='NOT_EVALUATED'


class Exclusion(DTO):
    product_id: UUID
    code: str
    field: str
    affected_dates: tuple[date,...]
    ingredient_ids: tuple[UUID,...]
    message: str
    suggested_action: str
    requirement_overrides: tuple[ExcludedOverride,...]


class RunScope(DTO):
    menu_products: tuple[PlanningProductBrief,...]
    computed_product_ids: tuple[UUID,...]
    excluded_products: tuple[Exclusion,...]
    menu_count: int
    computed_count: int
    coverage_status: Literal['full','partial','none']


class ExecutionView(DTO):
    engine_semantics_version: str
    comparison_version: str
    selector_version: str
    elapsed_ms: int
    engine_elapsed_ms: int
    engine_deadline_ms: int
    engine_overrun_ms: int
    comparison_selector_elapsed_ms: int
    search_complete: bool


class Gap(DTO):
    product_id: UUID
    path: Path
    target_percent: PercentText
    shortfall: ExactQuantity
    unit: str


class StrategyResult(DTO):
    strategy: Strategy
    construction_path: Path
    option_id: OptionId | None
    execution: Literal['FINISHED','INCOMPLETE','ERROR','BLOCKED','NUMERIC_UNSUPPORTED']
    termination: str
    customer_pass: bool
    construction_pass: bool
    selection_kind: Literal['TARGET','CUSTOMER_PASS_FALLBACK','REFERENCE_NOT_RANKED','NONE']
    customer_feasibility: Literal['PASS_EXISTS','NO_PASS_CERTIFIED','UNKNOWN']
    construction_feasibility: Literal['PASS_EXISTS','NO_PASS_CERTIFIED','UNKNOWN']
    proof: Literal['UNPROVEN','COMPLETE_EXACT_ENUMERATION']
    proof_scope: Literal['CAPTURED_FINITE_DOMAIN_ONLY']
    domain_size: CountText
    search_complete: bool
    customer_gaps: tuple[Gap,...]
    construction_gaps: tuple[Gap,...]
    diagnostic: PlanningNotification | None


class PlanningFeeComponent(DTO):
    basis: Literal['OFFER','SUPPLIER_ORDER']
    entity_id: UUID
    amount: ExactQuantity


class Costs(DTO):
    currency: str
    purchase: ExactQuantity
    payable_fees: ExactQuantity
    delivery_fees: ExactQuantity | None
    fee_classification: Literal['DECLARED_DELIVERY','PAYABLE_FEE_TYPE_NOT_CAPTURED','NONE']
    total: ExactQuantity
    fee_components: tuple[PlanningFeeComponent,...]


class Purchase(DTO):
    supplier_term_id: UUID
    supplier_id: UUID
    ingredient_id: UUID
    unit: str
    packs: int=Field(ge=1)
    quantity: ExactQuantity
    arrival_date: date
    expiry_date: date | None
    purchase_outlay: ExactQuantity
    payable_fee_components: tuple[PlanningFeeComponent,...]


class ProductService(DTO):
    product_id: UUID
    unit: str
    path: Path
    requested: ExactQuantity
    fulfilled: ExactQuantity
    lost_sales: ExactQuantity
    service: Service | None


class IngredientBalance(DTO):
    ingredient_id: UUID
    unit: str
    path: Path
    consumed: ExactQuantity
    expired: ExactQuantity
    ending_usable: ExactQuantity


class Assessment(DTO):
    product_id: UUID
    path: Path
    target_percent: PercentText
    applied_source: Literal['common','product_override']
    status: Literal['PASS','FAIL','NOT_EVALUATED']
    shortfall: ExactQuantity | None


class Option(DTO):
    option_id: OptionId
    source_strategies: tuple[Strategy,...]
    eligible: bool
    rejection_reasons: tuple[str,...]
    not_selected_reason: Literal['HIGHER_COST','LOWER_SERVICE_TIE','STABLE_ORDER_TIE','CUSTOMER_REQUIREMENTS_NOT_MET','RELATED_BLOCKER'] | None
    costs: Costs
    purchases: tuple[Purchase,...]
    product_services: tuple[ProductService,...]
    ingredient_balances: tuple[IngredientBalance,...]
    requirements_assessment: tuple[Assessment,...]
    issues: tuple[PlanningNotification,...]


class PlanningResult(DTO):
    completeness: Literal['full','partial']
    strategies: tuple[StrategyResult,...]
    options: tuple[Option,...]
    winner_option_id: OptionId | None
    winner_reason: Literal['WINNER_FOUND','NO_ELIGIBLE_CANDIDATE','NOT_EVALUATED']
    warnings: tuple[PlanningNotification,...]

    @model_validator(mode='after')
    def winner_reference(self):
        if self.winner_option_id is not None and not any(o.option_id==self.winner_option_id and o.eligible for o in self.options):
            raise ValueError('Winner must reference retained eligible option')
        return self


class RunView(DTO):
    run_id: UUID
    store_id: UUID
    status: Literal['queued','running','completed','failed']
    outcome: Literal['recommendation_available','no_eligible_candidate','no_computable_products','computation_blocked','execution_error'] | None
    accepted_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    response_version: Version
    request: PlanningRequest
    configuration: RunConfiguration
    operational_basis: OperationalBasis | None
    forecast: ForecastView | None
    scope: RunScope | None
    execution: ExecutionView | None
    result: PlanningResult | None
    errors: tuple[PlanningNotification,...]
