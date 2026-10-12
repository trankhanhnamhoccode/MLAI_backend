"""Opt-in internal procurement/1; no DecisionRun/API or policy-v1 reinterpretation."""
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator
from app.application.contracts.common import (
    Contract, Nonblank, NonnegativeDecimal, PositiveDecimal, Strategy, Unit,
)
from app.application.contracts.decision_execution import PreparedDecisionInput, SourceReference, VersionOne
from app.application.contracts.decision_package import PathId
from app.application.contracts.serving import HypotheticalArrival, Quantity, ServingSimulationResult

Count = Annotated[int, Field(strict=True, ge=0)]
PositiveCount = Annotated[int, Field(strict=True, gt=0)]
Ratio = Annotated[NonnegativeDecimal, Field(le=1)]


class ProductFloor(Contract):
    product_id: UUID
    target: Ratio


class ConstructionRule(Contract):
    strategy: Strategy
    path: PathId
    target: Ratio
    floors: tuple[ProductFloor, ...]

    @model_validator(mode='after')
    def mapping(self):
        if self.path != {'LEAN': 'LOW', 'BALANCED': 'BASE', 'PROTECTED': 'HIGH'}[self.strategy]:
            raise ValueError('Strategy construction must map LEAN/LOW, BALANCED/BASE, PROTECTED/HIGH')
        if len({f.product_id for f in self.floors}) != len(self.floors):
            raise ValueError('Duplicate Product floor')
        object.__setattr__(self, 'floors', tuple(sorted(self.floors, key=lambda f: f.product_id)))
        return self


class NumericGuards(Contract):
    integer_tolerance: Annotated[PositiveDecimal, Field(lt=Decimal('0.5'))]
    coefficient_min: PositiveDecimal
    coefficient_max: PositiveDecimal
    scale_min: PositiveDecimal
    scale_max: PositiveDecimal
    integer_max: Annotated[int, Field(strict=True, gt=0, le=2**53-1)]

    @model_validator(mode='after')
    def ranges(self):
        if self.coefficient_min > self.coefficient_max or self.scale_min > self.scale_max:
            raise ValueError('Numeric guard ranges must be ordered')
        return self


class ProcurementPolicy(Contract):
    policy_id: Literal['procurement']
    version: VersionOne
    configuration_id: Nonblank
    configuration_version: PositiveCount
    provenance: Nonblank
    rules: tuple[ConstructionRule, ...]
    service_units: Literal['COMMON_SELLING_UNIT_HORIZON_AGGREGATE']
    primary: Literal['MIN_OUTLAY_SUBJECT_TO_REQUIREMENTS']
    fallback: Literal['MAX_CONSTRUCTION_SERVICE_THEN_MIN_OUTLAY']
    tie_rule: Literal['SORTED_OFFER_UUID_PACK_VECTOR_LEXICOGRAPHIC']
    supplier_splitting: Literal[True]
    order_count: VersionOne
    fee_mode: Literal['NONE', 'PER_OFFER', 'PER_SUPPLIER_ORDER']
    computation_seconds: PositiveDecimal
    validation_reserve_seconds: PositiveDecimal
    max_solves_per_strategy: PositiveCount
    certification: Literal['DISABLED', 'EXACT_ENUMERATION']
    certification_vector_limit: Count
    numeric: NumericGuards

    @model_validator(mode='after')
    def complete(self):
        if len(self.rules) != 3 or {r.strategy for r in self.rules} != {'LEAN', 'BALANCED', 'PROTECTED'}:
            raise ValueError('Exactly three explicit construction rules required')
        if Fraction(self.validation_reserve_seconds) >= Fraction(self.computation_seconds) / 3:
            raise ValueError('Validation reserve must fit each equal strategy slice')
        if (self.certification == 'EXACT_ENUMERATION') != (self.certification_vector_limit > 0):
            raise ValueError('Certification requires explicit positive domain limit; disabled uses zero')
        # Reject bool/coerced version even though Literal normally compares by equality.
        if type(self.version) is not int or type(self.order_count) is not int:
            raise ValueError('Versions and order count must be integers')
        object.__setattr__(self, 'rules', tuple(sorted(self.rules, key=lambda r: ('LEAN','BALANCED','PROTECTED').index(r.strategy))))
        return self


class ProcurementBudget(Contract):
    state: Literal['KNOWN', 'EXPLICIT_UNCONSTRAINED', 'UNKNOWN']
    amount: NonnegativeDecimal | None
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    provenance: Nonblank

    @model_validator(mode='after')
    def known(self):
        if (self.state == 'KNOWN') != (self.amount is not None):
            raise ValueError('Only KNOWN budget has an amount; unknown is not unlimited')
        return self


class OfferBound(Contract):
    maximum_packs: Count
    source: Literal['TECHNICAL_SEARCH_LIMIT', 'CAPTURED_SUPPLIER_LIMIT']
    derivation: Nonblank
    proof_scope: Literal['CAPTURED_FINITE_DOMAIN_ONLY']


class ProcurementOffer(Contract):
    term_id: UUID
    arrival_lot_id: UUID
    bound: OfferBound
    payable_fee: NonnegativeDecimal | None
    provenance: Nonblank


class SupplierFee(Contract):
    supplier_id: UUID
    amount: NonnegativeDecimal | None
    provenance: Nonblank


class IngredientCapacity(Contract):
    store_id: UUID
    ingredient_id: UUID
    unit: Unit
    maximum_quantity: NonnegativeDecimal
    checkpoint: Literal['POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION']
    provenance: Nonblank


class SupplierLimit(Contract):
    store_id: UUID
    supplier_id: UUID
    ingredient_id: UUID
    unit: Unit
    maximum_quantity: NonnegativeDecimal
    scope: Literal['ONE_ORDER_SUPPLIER_INGREDIENT']
    provenance: Nonblank


class ProcurementInput(Contract):
    prepared: PreparedDecisionInput
    policy: ProcurementPolicy
    offers: tuple[ProcurementOffer, ...]
    budget: ProcurementBudget
    supplier_fees: tuple[SupplierFee, ...]
    capacities: tuple[IngredientCapacity, ...]
    supplier_limits: tuple[SupplierLimit, ...]
    arrivals: tuple[HypotheticalArrival, ...]
    unsupported_configured_constraints: tuple[Nonblank, ...]
    source_references: tuple[SourceReference, ...]

    @model_validator(mode='after')
    def scope(self):
        from app.application.use_cases.bom import _canonical_snapshot
        p = _canonical_snapshot(self.prepared)
        object.__setattr__(self, 'prepared', p)
        ingredients = {i.ingredient_id: i.unit for i in p.ingredients}
        terms = {t.id: t for t in p.supplier_terms}
        if len({o.term_id for o in self.offers}) != len(self.offers):
            raise ValueError('Duplicate procurement offer')
        if (self.policy.service_units == 'COMMON_SELLING_UNIT_HORIZON_AGGREGATE'
                and len({product.selling_unit for product in p.products}) != 1):
            raise ValueError('Horizon aggregate service requires exact common selling unit')
        if self.budget.currency != p.currency:
            raise ValueError('Budget currency differs from captured currency')
        for c in p.constraints:
            if c.kind == 'BUDGET_LIMIT':
                # Operational /2 carries a physical Store ceiling and a possibly
                # lower explicit effective limit. Preserve the physical constraint;
                # the new engine limit may tighten it, never relax it. Old /1 and
                # historical /2 envelopes retain their original equality guard.
                operational_v2=(p.capture_version==2 and p.operational_basis is not None
                                and self.policy.policy_id=='procurement_api_policy')
                if (self.budget.state!='KNOWN' or
                    (self.budget.amount>c.value if operational_v2 else self.budget.amount!=c.value)):
                    raise ValueError('Procurement envelope cannot bypass captured budget')
        if not self.source_references:
            raise ValueError('Procurement capture/config provenance is required')
        allowed = {'store': {p.request.store_id}, 'forecast_run': {p.request.forecast_run_id},
                   'product': set(p.request.product_ids), 'ingredient': set(ingredients),
                   'supplier_term': set(terms), 'inventory_lot': {l.id for l in p.lots},
                   'constraint': {c.id for c in p.constraints}}
        for reference in self.source_references:
            if reference.entity not in allowed or reference.entity_id not in allowed[reference.entity]:
                raise ValueError('Procurement source reference outside captured scope')
        object.__setattr__(self, 'source_references', tuple(sorted(self.source_references,
            key=lambda r: (r.entity, r.entity_id, r.version or 0, r.origin))))
        seen = {l.id for l in p.lots}
        from app.application.contracts.serving import ServingSimulationInput
        ServingSimulationInput(prepared=p, arrivals=self.arrivals)
        seen.update(a.lot_id for a in self.arrivals)
        suppliers = set()
        for o in self.offers:
            if o.term_id not in terms or o.arrival_lot_id in seen:
                raise ValueError('Offer must reference captured term and unique hypothetical lot identity')
            seen.add(o.arrival_lot_id)
            t = terms[o.term_id]
            suppliers.add(t.supplier_id)
            # Date overflow is a boundary rejection, not silent truncation.
            try:
                day = p.request.cutoff_date + timedelta(days=1+t.lead_time_days)
                if t.shelf_life_days is not None:
                    day + timedelta(days=t.shelf_life_days)
            except OverflowError as error:
                raise ValueError('Offer arrival/expiry date overflow') from error
        for rule in self.policy.rules:
            if any(f.product_id not in p.request.product_ids for f in rule.floors):
                raise ValueError('Floor Product outside snapshot')
        if len({f.supplier_id for f in self.supplier_fees}) != len(self.supplier_fees) or any(f.supplier_id not in suppliers for f in self.supplier_fees):
            raise ValueError('Supplier fee duplicates or scope mismatch')
        if self.policy.fee_mode=='NONE' and (any(o.payable_fee not in (None,0) for o in self.offers) or
                                             any(f.amount not in (None,0) for f in self.supplier_fees)):
            raise ValueError('NONE fee declaration contradicts supplied positive payable fee')
        for rows, key in ((self.capacities, lambda c: c.ingredient_id),
                          (self.supplier_limits, lambda c: (c.supplier_id, c.ingredient_id))):
            if len({key(c) for c in rows}) != len(rows):
                raise ValueError('Duplicate capacity/supplier limit')
            for c in rows:
                if c.store_id != p.request.store_id or ingredients.get(c.ingredient_id) != c.unit:
                    raise ValueError('Constraint Store/Ingredient/exact unit mismatch')
                if isinstance(c, SupplierLimit) and not any(t.supplier_id == c.supplier_id and t.ingredient_id == c.ingredient_id for t in terms.values()):
                    raise ValueError('Supplier limit outside captured terms')
        for offer in self.offers:
            if offer.bound.source == 'CAPTURED_SUPPLIER_LIMIT':
                term = terms[offer.term_id]
                limits = [c for c in self.supplier_limits if c.supplier_id == term.supplier_id and c.ingredient_id == term.ingredient_id]
                if not limits or Fraction(term.pack_size_base_quantity)*offer.bound.maximum_packs > Fraction(limits[0].maximum_quantity):
                    raise ValueError('Supplier-derived bound requires consistent captured supplier limit')
        for name, key in (('offers', lambda o:o.term_id), ('supplier_fees',lambda f:f.supplier_id),
                          ('capacities',lambda c:c.ingredient_id), ('supplier_limits',lambda c:(c.supplier_id,c.ingredient_id)),
                          ('arrivals',lambda a:a.lot_id)):
            object.__setattr__(self,name,tuple(sorted(getattr(self,name),key=key)))
        return self


class ConstraintCoverage(Contract):
    constraint: Nonblank
    status: Literal['ENFORCED', 'EXPLICIT_UNCONSTRAINED', 'NOT_CONFIGURED', 'BLOCKED']
    detail: Nonblank


class BasketLine(Contract):
    term_id: UUID
    supplier_id: UUID
    ingredient_id: UUID
    unit: Unit
    packs: PositiveCount
    quantity: Quantity


class ServiceMetric(Contract):
    path: PathId
    product_id: UUID | None
    requested: Quantity
    served: Quantity
    service: Quantity | None


class RequirementGap(Contract):
    product_id: UUID | None
    target: Ratio
    shortfall_quantity: Quantity


class ProcurementCandidate(Contract):
    counts: tuple[Count, ...]
    basket: tuple[BasketLine, ...]
    arrivals: tuple[HypotheticalArrival, ...]
    outlay: Quantity
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    hard_validity: Literal['EXACT_VALIDATED']
    evaluation: ServingSimulationResult
    services: tuple[ServiceMetric, ...]


class CandidateClassification(Contract):
    counts: tuple[Count, ...]
    stage: Literal['ZERO_BASELINE', 'MILP_TARGET', 'MILP_FALLBACK', 'ENUMERATION']
    classification: Literal['HARD_REJECTED', 'TARGET_MET', 'HARD_VALID_TARGET_MISS']
    reasons: tuple[Nonblank, ...]


class SolverEvidence(Contract):
    phase: Literal['TARGET', 'FALLBACK_SERVICE', 'FALLBACK_COST']
    status: Annotated[int, Field(strict=True, ge=0, le=4)]
    message: str
    incumbent: bool
    objective: float | None
    bound: float | None
    gap: float | None
    nodes: int | None
    seconds: float
    variables: Count
    constraints: Count
    solver_version: Nonblank
    time_limit: float
    extracted_counts: tuple[Count, ...] | None = None


class StrategyProcurementResult(Contract):
    rule: ConstructionRule
    execution: Literal['FINISHED', 'INCOMPLETE', 'ERROR', 'BLOCKED', 'NUMERIC_UNSUPPORTED']
    termination: Nonblank
    target_met: bool
    target_feasibility: Literal['PASS_EXISTS', 'NO_PASS_CERTIFIED', 'UNKNOWN']
    best_target_met: ProcurementCandidate | None
    best_available: ProcurementCandidate | None
    requirement_gaps: tuple[RequirementGap, ...]
    proof: Literal['COMPLETE_EXACT_ENUMERATION', 'UNPROVEN']
    proof_scope: Literal['CAPTURED_FINITE_DOMAIN_ONLY']
    search_complete: bool
    domain_size: PositiveCount
    enumerated_vectors: Count
    solver: tuple[SolverEvidence, ...]
    journal: tuple[CandidateClassification, ...]
    excluded: tuple[tuple[Count, ...], ...]
    diagnostic: str | None

    @model_validator(mode='after')
    def quality(self):
        if self.target_met != (self.best_target_met is not None):
            raise ValueError('Target status must reference validated passing candidate')
        if self.target_met != (self.target_feasibility == 'PASS_EXISTS'):
            raise ValueError('Target existence evidence mismatch')
        if self.search_complete != (self.proof == 'COMPLETE_EXACT_ENUMERATION'):
            raise ValueError('Only complete exact traversal proves finite domain')
        if self.search_complete and self.enumerated_vectors != self.domain_size:
            raise ValueError('Enumeration proof requires complete finite domain')
        if self.target_feasibility == 'NO_PASS_CERTIFIED' and not self.search_complete:
            raise ValueError('No-pass requires exact finite domain proof')
        return self


class ProcurementResult(Contract):
    semantics_version: Literal['procurement/1']
    input: ProcurementInput
    execution: Literal['FINISHED', 'INCOMPLETE', 'ERROR', 'BLOCKED', 'NUMERIC_UNSUPPORTED']
    readiness: Literal['READY_FOR_INTERNAL_PROCUREMENT', 'BLOCKED']
    coverage: tuple[ConstraintCoverage, ...]
    strategies: tuple[StrategyProcurementResult, ...]
    elapsed_seconds: float
    deadline_overrun_seconds: float
    unique_exact_evaluations: Count
    decision_readiness: Literal['NOT_ASSESSED']

    @model_validator(mode='after')
    def validate_output(self):
        from app.application.procurement_validation import validate_result
        validate_result(self)
        return self
