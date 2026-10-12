"""Opt-in S3.1 boundary. S1 opaque DecisionRun persistence remains unchanged.

No DB capture, business engine, persistence adapter or recommendation computation.
All nested collections are tuples of frozen typed values, never caller dictionaries.
"""
from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BeforeValidator, Field, field_validator, model_validator

from app.application.contracts.common import (
    Contract, Metadata, Nonblank, NonnegativeDecimal, Strategy, Unit,
)
from app.application.contracts.forecast_execution import ForecastExecutionPrediction, ForecastWarning
from app.application.contracts.inventory import InventoryLotResult
from app.application.contracts.recipe import CreateRecipeVersionInput
from app.application.contracts.supplier import SupplierTermResult
from app.domain.decision.validation import (
    DECIMAL_PRECISION, POLICY_V1, STRATEGIES, arrival_date, unique_coverage,
)
from app.domain.forecasting.validation import forecast_dates, validate_output_coverage
from app.application.contracts.decision_temporal import OperationalBasis

def _version_one(value: object) -> object:
    if type(value) is not int:
        raise ValueError('Version must be integer 1')
    return value


def _utc_instant(value: datetime) -> datetime:
    try:
        return value.astimezone(datetime_timezone.utc)
    except (OverflowError, ValueError) as error:
        raise ValueError('Business instant outside supported UTC date range') from error


VersionOne = Annotated[Literal[1], BeforeValidator(_version_one)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
Currency = Annotated[str, Field(pattern=r'^[A-Z]{3}$')]


class DecisionPolicy(Contract):
    policy_id: Literal['competition_demo'] = 'competition_demo'
    version: VersionOne = 1
    classification: Literal['PROVISIONAL_POLICY'] = 'PROVISIONAL_POLICY'
    base_service_target: Annotated[NonnegativeDecimal, Field(le=1)] = Decimal('.95')
    high_service_target: Annotated[NonnegativeDecimal, Field(le=1)] = Decimal('.90')
    lean_protection: Annotated[NonnegativeDecimal, Field(le=1)] = Decimal(0)
    balanced_protection: Annotated[NonnegativeDecimal, Field(le=1)] = Decimal('.5')
    protected_protection: Annotated[NonnegativeDecimal, Field(le=1)] = Decimal(1)
    decimal_precision: Annotated[int, Field(strict=True)] = DECIMAL_PRECISION
    decimal_rounding: Literal['ROUND_HALF_EVEN'] = 'ROUND_HALF_EVEN'
    strategy_tie_order: tuple[Strategy, ...] = STRATEGIES
    order_count: VersionOne = 1
    expiry_day_usable: Annotated[bool, Field(strict=True)] = True
    service_units: Literal['SINGLE_SELLING_UNIT'] = 'SINGLE_SELLING_UNIT'
    safety_stock_mode: Literal['TERMINAL_FLOOR_ONCE'] = 'TERMINAL_FLOOR_ONCE'

    @model_validator(mode='after')
    def actual_v1(self):
        if ((self.base_service_target, self.high_service_target, self.lean_protection,
             self.balanced_protection, self.protected_protection) != POLICY_V1
                or self.decimal_precision != DECIMAL_PRECISION
                or self.strategy_tie_order != STRATEGIES or not self.expiry_day_usable):
            raise ValueError('Values do not match policy v1; changing policy requires a new reviewed version')
        return self


class DecisionExecutionInput(Contract):
    store_id: UUID
    forecast_run_id: UUID
    product_ids: tuple[UUID, ...]
    cutoff_date: date
    order_at: AwareDatetime

    @field_validator('order_at')
    @classmethod
    def normalized_instant(cls, value: datetime) -> datetime:
        return _utc_instant(value)

    @model_validator(mode='after')
    def explicit_scope(self):
        if not self.product_ids or len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError('Product scope must be nonempty and unique')
        forecast_dates(self.cutoff_date)
        object.__setattr__(self, 'product_ids', tuple(sorted(self.product_ids)))
        return self


class AffectedEntity(Contract):
    entity: Literal['store', 'product', 'ingredient', 'inventory_lot', 'supplier_term', 'constraint', 'candidate']
    entity_id: UUID | None = None
    strategy: Strategy | None = None

    @model_validator(mode='after')
    def identified(self):
        if self.entity == 'candidate':
            if self.strategy is None:
                raise ValueError('Candidate issue requires a strategy')
        elif self.entity_id is None:
            raise ValueError('Affected business entity requires identity')
        return self


class DecisionIssue(Contract):
    code: Metadata
    kind: Literal['INFO', 'WARNING', 'DATA_BLOCKER', 'HARD_VIOLATION']
    field: Nonblank
    affected: tuple[AffectedEntity, ...]
    impact: Nonblank
    suggested_action: Nonblank

    @model_validator(mode='after')
    def has_object(self):
        if not self.affected:
            raise ValueError('Business issue requires affected objects')
        return self


class DecisionReadiness(Contract):
    status: Literal['READY_FOR_COMPUTATION', 'DATA_BLOCKED']
    issues: tuple[DecisionIssue, ...]

    @model_validator(mode='after')
    def meaningful_status(self):
        blocked = any(i.kind == 'DATA_BLOCKER' for i in self.issues)
        if blocked != (self.status == 'DATA_BLOCKED'):
            raise ValueError('Readiness must reflect blockers; readiness is not quality')
        return self


class SourceReference(Contract):
    entity: Nonblank
    entity_id: UUID
    version: PositiveInt | None = None
    origin: Literal['SOURCE_EXPLICIT', 'DETERMINISTIC_DERIVED', 'SYSTEM_ASSIGNED', 'UNKNOWN', 'AMBIGUOUS']


class CapturedDecisionProduct(Contract):
    store_id: UUID
    product_id: UUID
    selling_unit: Unit
    sku: Metadata | None = None


class CapturedDecisionIngredient(Contract):
    store_id: UUID
    ingredient_id: UUID
    unit: Unit
    expiry_tracking: Annotated[bool, Field(strict=True)]


class CapturedRecipe(CreateRecipeVersionInput):
    id: UUID


class DecisionForecastPoint(ForecastExecutionPrediction):
    unit: Unit


class CapturedDecisionForecast(Contract):
    store_id: UUID
    run_id: UUID
    cutoff_date: date
    input_fingerprint: Metadata
    model_type: Metadata
    model_version: Metadata
    artifact_identity: Nonblank | None
    predictions: tuple[DecisionForecastPoint, ...]
    warnings: tuple[ForecastWarning, ...] = ()


class CapturedDecisionConstraint(Contract):
    id: UUID
    store_id: UUID
    version: PositiveInt
    kind: Literal['BUDGET_LIMIT', 'MIN_SAFETY_STOCK']
    ingredient_id: UUID | None
    value: NonnegativeDecimal
    unit: Unit
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode='after')
    def scope_and_dates(self):
        if (self.kind == 'MIN_SAFETY_STOCK') != (self.ingredient_id is not None):
            raise ValueError('Constraint scope does not match registry')
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError('Constraint dates must be ordered')
        return self


class PreparedDecisionInput(Contract):
    # v2 adds per-Product service admission; v1 retains its single-unit contract.
    capture_version: Annotated[int, Field(strict=True, ge=1, le=2)] = 1
    operational_basis: OperationalBasis | None = None
    snapshot_schema_version: VersionOne = 1
    request: DecisionExecutionInput
    timezone: Nonblank
    currency: Currency
    inventory_as_of: AwareDatetime
    forecast: CapturedDecisionForecast
    products: tuple[CapturedDecisionProduct, ...]
    ingredients: tuple[CapturedDecisionIngredient, ...]
    recipes: tuple[CapturedRecipe, ...]
    lots: tuple[InventoryLotResult, ...]
    supplier_terms: tuple[SupplierTermResult, ...]
    constraints: tuple[CapturedDecisionConstraint, ...]
    policy: DecisionPolicy
    issues: tuple[DecisionIssue, ...]
    assumptions: tuple[Nonblank, ...]
    source_references: tuple[SourceReference, ...]

    @field_validator('inventory_as_of')
    @classmethod
    def normalized_instant(cls, value: datetime) -> datetime:
        return _utc_instant(value)

    @model_validator(mode='after')
    def validate_capture(self):
        try:
            zone = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('Timezone must be a resolvable IANA timezone') from error
        days = forecast_dates(self.request.cutoff_date)
        try:
            order_day = self.request.order_at.astimezone(zone).date()
        except (OverflowError, ValueError) as error:
            raise ValueError('Business instant outside supported Store-local date range') from error
        basis = self.operational_basis
        if basis is None:
            if order_day != days[0] or self.inventory_as_of != self.request.order_at:
                raise ValueError('v1 requires an as-of snapshot at the D+1 decision instant, before trading')
            required = {'DAY_START_CAPTURE', 'COMPLETE_INVENTORY_SCOPE', 'NO_ADDITIONAL_ORDERS'}
        else:
            if (self.capture_version != 2 or basis.timezone != self.timezone or
                    basis.planning_start_date != days[0] or order_day != days[0] or
                    basis.captured_at != self.inventory_as_of):
                raise ValueError('Temporal adapter requires explicit capture2 and genuine capture basis')
            if basis.kind == 'CURRENT_CAPTURE' and self.request.order_at != basis.captured_at:
                raise ValueError('Current order instant must be the observed capture instant')
            if not set(basis.assumptions) <= set(self.assumptions):
                raise ValueError('Snapshot must retain temporal basis assumptions')
            required = {'CURRENT_BALANCES_NOT_HISTORICAL_AS_OF', 'COMPLETE_INVENTORY_SCOPE', 'NO_ADDITIONAL_ORDERS'}
        if not required <= set(self.assumptions):
            raise ValueError('Explicit day-start, complete stock scope and one-order assumptions required')
        if not self.source_references or len(set(self.assumptions)) != len(self.assumptions):
            raise ValueError('Capture requires source references and unique assumptions')
        request, forecast = self.request, self.forecast
        if (forecast.store_id, forecast.run_id, forecast.cutoff_date) != (
                request.store_id, request.forecast_run_id, request.cutoff_date):
            raise ValueError('Forecast Store/run/cutoff must match decision request')
        unique_coverage(tuple(p.product_id for p in self.products), set(request.product_ids), 'Products')
        product_units = {p.product_id: p.selling_unit for p in self.products}
        if self.capture_version == 1 and len(set(product_units.values())) != 1:
            raise ValueError('Policy v1 service aggregation requires one selling unit; no inferred normalization')
        ingredients = {i.ingredient_id: i for i in self.ingredients}
        if len(ingredients) != len(self.ingredients):
            raise ValueError('Duplicate Ingredients')
        for rows, key in ((self.recipes, 'id'), (self.lots, 'id'), (self.supplier_terms, 'id'), (self.constraints, 'id')):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError('Duplicate captured identity')
        for row in (*self.products, *self.ingredients, *self.recipes, *self.lots, *self.supplier_terms, *self.constraints):
            if row.store_id != request.store_id:
                raise ValueError('Captured entity outside Store scope')
        self.validate_issue_scope(self.issues)
        validate_output_coverage(request.product_ids, request.cutoff_date,
                                 tuple((p.product_id, p.forecast_date) for p in forecast.predictions))
        if any(p.unit != product_units[p.product_id] for p in forecast.predictions):
            raise ValueError('Forecast units must match captured Product units')
        for row in (*self.lots, *self.supplier_terms):
            if row.ingredient_id not in ingredients or row.unit != ingredients[row.ingredient_id].unit:
                raise ValueError('Lot/term Ingredient scope or unit mismatch')
        for recipe in self.recipes:
            if recipe.product_id not in product_units:
                raise ValueError('Recipe outside requested Product scope')
            for line in recipe.lines:
                if line.ingredient_id not in ingredients or line.unit != ingredients[line.ingredient_id].unit:
                    raise ValueError('Recipe Ingredient scope or unit mismatch')
        for product in request.product_ids:
            for day in days:
                matches = [r for r in self.recipes if r.product_id == product and
                           r.effective_from <= day and (r.effective_to is None or day <= r.effective_to)]
                if len(matches) > 1:
                    raise ValueError('Ambiguous overlapping recipe versions')
                if not matches or not matches[0].lines:
                    self._require_issue('MISSING_RECIPE', 'DATA_BLOCKER', 'product', product)
        for lot in self.lots:
            if lot.received_date is not None and lot.expiry_date is not None and lot.expiry_date < lot.received_date:
                raise ValueError('Lot expiry precedes receipt')
            # Temporal /2 admits captured balances later in a past horizon; expiry
            # remains required before such a balance can become eligible.
            usable_date = lot.received_date is None or lot.received_date <= (basis.local_capture_date if basis else order_day)
            if usable_date and lot.on_hand_quantity > 0:
                if ingredients[lot.ingredient_id].expiry_tracking and lot.expiry_date is None:
                    self._require_issue('MISSING_EXPIRY', 'DATA_BLOCKER', 'inventory_lot', lot.id)
                if lot.received_date is None:
                    self._require_issue('MISSING_RECEIVED_DATE', 'WARNING', 'inventory_lot', lot.id)
                if lot.unit_cost is None:
                    self._require_issue('MISSING_COST', 'WARNING', 'inventory_lot', lot.id)
        for term in self.supplier_terms:
            if (not term.active or term.effective_from > order_day or
                    (term.effective_to is not None and term.effective_to < order_day)):
                raise ValueError('Captured supplier terms must be effective at the order date')
            arrival_date(order_day, term.lead_time_days)
        budgets = []
        for constraint in self.constraints:
            if constraint.kind == 'BUDGET_LIMIT':
                budgets.append(constraint)
                if constraint.unit != self.currency:
                    raise ValueError('Budget currency must match Store.currency')
                if not constraint.effective_from <= order_day or (
                        constraint.effective_to is not None and order_day > constraint.effective_to):
                    raise ValueError('Budget must be effective at order date')
            elif (constraint.ingredient_id not in ingredients or
                  constraint.unit != ingredients[constraint.ingredient_id].unit):
                raise ValueError('Safety-stock Ingredient scope/unit mismatch')
        if len(budgets) > 1:
            raise ValueError('Ambiguous order budget')
        for ingredient in ingredients:
            for day in days:
                matches = [c for c in self.constraints if c.kind == 'MIN_SAFETY_STOCK' and
                           c.ingredient_id == ingredient and c.effective_from <= day and
                           (c.effective_to is None or day <= c.effective_to)]
                if len(matches) > 1:
                    raise ValueError('Overlapping safety stock versions')
        # Canonical order is independent of loader iteration, not an allocation priority.
        for name, key in (('products', 'product_id'), ('ingredients', 'ingredient_id'),
                          ('recipes', 'id'), ('lots', 'id'), ('supplier_terms', 'id'), ('constraints', 'id')):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name), key=lambda r: getattr(r, key))))
        object.__setattr__(self, 'forecast', forecast.model_copy(update={
            'predictions': tuple(sorted(forecast.predictions, key=lambda p: (p.forecast_date, p.product_id)))}))
        return self

    def _require_issue(self, code, kind, entity, entity_id):
        if not any(i.code == code and i.kind == kind and
                   any(a.entity == entity and a.entity_id == entity_id for a in i.affected) for i in self.issues):
            raise ValueError(f'{code} requires an object-specific {kind}')

    def validate_issue_scope(self, issues: tuple[DecisionIssue, ...]) -> None:
        allowed = {
            'store': {self.request.store_id},
            'product': set(self.request.product_ids),
            'ingredient': {i.ingredient_id for i in self.ingredients},
            'inventory_lot': {l.id for l in self.lots},
            'supplier_term': {t.id for t in self.supplier_terms},
            'constraint': {c.id for c in self.constraints},
        }
        for issue in issues:
            for affected in issue.affected:
                if affected.entity != 'candidate' and affected.entity_id not in allowed[affected.entity]:
                    raise ValueError('Business issue references an entity outside captured scope')
