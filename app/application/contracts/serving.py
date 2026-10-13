"""Internal pure serving foundation; exact quantities, Decimal views, no orders."""
from datetime import date
from fractions import Fraction
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator

from app.application.contracts.bom import BOMExpansionResult, BOMIssue
from app.application.contracts.common import Contract, NonnegativeDecimal, PositiveDecimal, Unit
from app.application.contracts.decision_execution import PreparedDecisionInput
from app.application.contracts.decision_package import PathId
from app.domain.decision.quantities import checked, display
from app.domain.forecasting.validation import forecast_dates
from app.application.serving_validation import validate_product, validate_lot, validate_ingredient, validate_result


class Quantity(Contract):
    numerator: Annotated[str, Field(strict=True, pattern=r'^(0|[1-9][0-9]*)$', max_length=1000)]
    denominator: Annotated[str, Field(strict=True, pattern=r'^[1-9][0-9]*$', max_length=1000)]
    decimal_view: NonnegativeDecimal

    @model_validator(mode='after')
    def canonical(self) -> 'Quantity':
        value = checked(Fraction(int(self.numerator), int(self.denominator)))
        if (str(value.numerator), str(value.denominator)) != (self.numerator, self.denominator):
            raise ValueError('Exact quantity must use reduced canonical numerator/denominator')
        if self.decimal_view != display(value):
            raise ValueError('Decimal view must match precision50/HALF_EVEN exact quantity')
        return self


class HypotheticalArrival(Contract):
    lot_id: UUID
    store_id: UUID
    ingredient_id: UUID
    unit: Unit
    arrival_day: date
    expiry_date: date | None = None
    quantity: PositiveDecimal

    @model_validator(mode='after')
    def expiry(self) -> 'HypotheticalArrival':
        if self.expiry_date is not None and self.expiry_date < self.arrival_day:
            raise ValueError('Hypothetical expiry cannot precede arrival')
        return self


class ServingSimulationInput(Contract):
    prepared: PreparedDecisionInput
    arrivals: tuple[HypotheticalArrival, ...] = ()

    @model_validator(mode='after')
    def scope(self) -> 'ServingSimulationInput':
        ingredients = {i.ingredient_id: i.unit for i in self.prepared.ingredients}
        days = forecast_dates(self.prepared.request.cutoff_date)
        seen = {lot.id for lot in self.prepared.lots}
        for arrival in self.arrivals:
            if arrival.lot_id in seen:
                raise ValueError('Duplicate/colliding hypothetical lot identity')
            seen.add(arrival.lot_id)
            if (arrival.store_id != self.prepared.request.store_id or
                    ingredients.get(arrival.ingredient_id) != arrival.unit or arrival.arrival_day not in days):
                raise ValueError('Arrival must match captured Store/Ingredient/unit and planning window')
        object.__setattr__(self, 'arrivals', tuple(sorted(self.arrivals, key=lambda a: a.lot_id)))
        return self


class ProductServingDay(Contract):
    path_id: PathId
    day: date
    product_id: UUID
    recipe_id: UUID
    unit: Unit
    requested: Quantity
    fulfilled: Quantity
    lost: Quantity

    @model_validator(mode='after')
    def conservation(self) -> 'ProductServingDay':
        validate_product(self)
        return self


class FulfilledContribution(Contract):
    path_id: PathId
    day: date
    product_id: UUID
    recipe_id: UUID
    ingredient_id: UUID
    unit: Unit
    quantity: Quantity


class LotServingDay(Contract):
    path_id: PathId
    day: date
    lot_id: UUID
    ingredient_id: UUID
    unit: Unit
    opening: Quantity
    arrivals: Quantity
    pre_service_expired: Quantity
    consumed: Quantity
    close_expired: Quantity
    other_waste: Quantity
    ending: Quantity

    @model_validator(mode='after')
    def conservation(self) -> 'LotServingDay':
        validate_lot(self)
        return self


class IngredientServingDay(Contract):
    path_id: PathId
    day: date
    ingredient_id: UUID
    unit: Unit
    requested: Quantity
    available: Quantity
    shortage: Quantity
    consumed: Quantity
    expired: Quantity
    other_waste: Quantity
    ending: Quantity

    @model_validator(mode='after')
    def arithmetic(self) -> 'IngredientServingDay':
        validate_ingredient(self)
        return self


class ServingSimulationResult(Contract):
    semantics_version: Literal['serving_fefo/1'] = 'serving_fefo/1'
    status: Literal['COMPLETE', 'DATA_BLOCKED', 'ARITHMETIC_BLOCKED']
    decision_readiness: Literal['NOT_ASSESSED', 'DATA_BLOCKED']
    input: ServingSimulationInput
    bom: BOMExpansionResult
    issues: tuple[BOMIssue, ...]
    products: tuple[ProductServingDay, ...] = ()
    contributions: tuple[FulfilledContribution, ...] = ()
    lots: tuple[LotServingDay, ...] = ()
    ingredients: tuple[IngredientServingDay, ...] = ()

    @model_validator(mode='after')
    def status_and_coverage(self) -> 'ServingSimulationResult':
        blocked = any(i.kind == 'DATA_BLOCKER' for i in self.issues)
        if blocked != (self.decision_readiness == 'DATA_BLOCKED'):
            raise ValueError('Captured or numeric blockers cannot disappear')
        if self.status != 'COMPLETE':
            if not blocked or self.products or self.contributions or self.lots or self.ingredients:
                raise ValueError('Blocked simulation cannot expose partial rows')
        else:
            if blocked or self.bom.status != 'COMPLETE':
                raise ValueError('Complete serving cannot have known blockers')
            expected = {(path, day, product) for path in ('LOW','BASE','HIGH')
                        for day in forecast_dates(self.input.prepared.request.cutoff_date)
                        for product in self.input.prepared.request.product_ids}
            actual = [(p.path_id, p.day, p.product_id) for p in self.products]
            if len(actual) != len(expected) or set(actual) != expected:
                raise ValueError('Complete serving requires full Product/path/day coverage')
        validate_result(self)
        return self
