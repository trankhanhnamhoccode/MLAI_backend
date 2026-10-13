"""Internal comparison facts only. No HTTP resource, winner or selected strategy."""
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.application.contracts.common import Contract, FiniteDecimal, Strategy, Unit, Nonblank
from app.application.contracts.procurement import (
    ProcurementResult, BasketLine, ConstructionRule, RequirementGap, SolverEvidence,
    CandidateClassification, Count, PositiveCount,
)
from app.application.contracts.serving import Quantity, HypotheticalArrival, ProductServingDay, IngredientServingDay
from app.application.contracts.bom import BOMIssue
from app.application.contracts.decision_execution import SourceReference
from app.domain.decision.quantities import checked, display

Token = Annotated[str, Field(strict=True, pattern=r'^cmp1_[a-f0-9]{64}$')]


class SignedQuantity(Contract):
    numerator: Annotated[str, Field(strict=True, pattern=r'^(0|-?[1-9][0-9]*)$', max_length=1001)]
    denominator: Annotated[str, Field(strict=True, pattern=r'^[1-9][0-9]*$', max_length=1000)]
    decimal_view: FiniteDecimal

    @model_validator(mode='after')
    def canonical(self):
        value=checked(Fraction(int(self.numerator),int(self.denominator)))
        if (str(value.numerator),str(value.denominator))!=(self.numerator,self.denominator) or self.decimal_view!=display(value):
            raise ValueError('Signed quantity requires reduced exact fraction and canonical Decimal50 view')
        return self


class ProcurementComparisonInput(Contract):
    procurement: ProcurementResult


class FeeComponent(Contract):
    basis: Literal['OFFER', 'SUPPLIER_ORDER']
    entity_id: UUID
    amount: Quantity


class OutlayBreakdown(Contract):
    purchase: Quantity
    payable_fees: Quantity
    delivery_fees: Quantity | None
    fee_classification: Literal['NO_PAYABLE_FEES','PAYABLE_FEE_TYPE_NOT_CAPTURED']
    total: Quantity
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    fee_mode: Literal['NONE', 'PER_OFFER', 'PER_SUPPLIER_ORDER']
    components: tuple[FeeComponent, ...]


class ComparedProduct(Contract):
    path: Literal['LOW','BASE','HIGH']
    product_id: UUID
    unit: Unit
    requested: Quantity
    fulfilled: Quantity
    lost: Quantity
    service: Quantity | None


class ComparedIngredient(Contract):
    path: Literal['LOW','BASE','HIGH']
    ingredient_id: UUID
    unit: Unit
    daily_shortage_sum: Quantity
    horizon_ending: Quantity
    expired: Quantity
    other_waste: Quantity


class ComparisonOption(Contract):
    token: Token
    identity_kind: Literal['INTERNAL_COMPARISON_TOKEN_NOT_PERSISTED']
    source_strategies: tuple[Strategy, ...]
    basket: tuple[BasketLine, ...]
    arrivals: tuple[HypotheticalArrival, ...]
    outlay: OutlayBreakdown
    products: tuple[ComparedProduct, ...]
    ingredients: tuple[ComparedIngredient, ...]
    daily_products: tuple[ProductServingDay, ...]
    daily_ingredients: tuple[IngredientServingDay, ...]
    issues: tuple[BOMIssue, ...]
    provenance: tuple[SourceReference, ...]
    hard_validity: Literal['EXACT_VALIDATED']


class StrategyComparisonOutcome(Contract):
    rule: ConstructionRule
    option_token: Token | None
    execution: Literal['FINISHED','INCOMPLETE','ERROR','BLOCKED','NUMERIC_UNSUPPORTED']
    termination: Nonblank
    target_met: bool
    target_feasibility: Literal['PASS_EXISTS','NO_PASS_CERTIFIED','UNKNOWN']
    requirement_gaps: tuple[RequirementGap, ...]
    proof: Literal['COMPLETE_EXACT_ENUMERATION','UNPROVEN']
    proof_scope: Literal['CAPTURED_FINITE_DOMAIN_ONLY']
    search_complete: bool
    domain_size: PositiveCount
    enumerated_vectors: Count
    solver: tuple[SolverEvidence, ...]
    journal: tuple[CandidateClassification, ...]
    excluded: tuple[tuple[Count, ...], ...]
    diagnostic: str | None


class ProductDelta(Contract):
    path: Literal['LOW','BASE','HIGH']
    product_id: UUID
    unit: Unit
    fulfilled: SignedQuantity
    lost: SignedQuantity


class IngredientDelta(Contract):
    path: Literal['LOW','BASE','HIGH']
    ingredient_id: UUID
    unit: Unit
    daily_shortage_sum: SignedQuantity
    horizon_ending: SignedQuantity
    expired: SignedQuantity
    other_waste: SignedQuantity


class OptionDelta(Contract):
    from_token: Token
    to_token: Token
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    total_outlay: SignedQuantity
    products: tuple[ProductDelta, ...]
    ingredients: tuple[IngredientDelta, ...]


class ComparisonDiagnostic(Contract):
    code: Literal['SAME_PLAN_DIFFERENT_EVALUATION']
    strategies: tuple[Strategy, ...]
    option_tokens: tuple[Token, ...]
    detail: Nonblank


class ProcurementComparisonResult(Contract):
    semantics_version: Literal['procurement_comparison/1']
    input: ProcurementComparisonInput
    status: Literal['COMPLETE','COMPLETE_WITH_DIAGNOSTICS']
    options: tuple[ComparisonOption, ...]
    outcomes: tuple[StrategyComparisonOutcome, ...]
    deltas: tuple[OptionDelta, ...]
    diagnostics: tuple[ComparisonDiagnostic, ...]
    delta_convention: Literal['TO_MINUS_FROM']
    decision_readiness: Literal['NOT_ASSESSED']

    @model_validator(mode='after')
    def reconcile(self):
        from app.application.procurement_comparison_validation import validate_comparison
        validate_comparison(self)
        return self
