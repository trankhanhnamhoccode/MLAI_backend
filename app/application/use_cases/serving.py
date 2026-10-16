"""Pure captured inventory simulation, opt-in and separate from DecisionRun writers."""
from dataclasses import asdict
from fractions import Fraction
from zoneinfo import ZoneInfo
from pydantic import TypeAdapter, ValidationError

from app.application.contracts.bom import BOMIssue
from app.application.contracts.common import NonnegativeDecimal
from app.application.contracts.serving import (
    ServingSimulationInput, ServingSimulationResult, Quantity, ProductServingDay,
    FulfilledContribution, LotServingDay, IngredientServingDay,
)
from app.application.use_cases.bom import expand_bom
from app.domain.demand.bom import DatedRecipe, RecipeLine, DemandPoint
from app.domain.decision.quantities import checked, display, ServingNumericError
from app.domain.decision.serving import Stock, simulate


_NONNEGATIVE_DECIMAL_ADAPTER = TypeAdapter(NonnegativeDecimal)


def _quantity(value: Fraction) -> Quantity:
    checked(value)
    view = display(value)
    try:
        _NONNEGATIVE_DECIMAL_ADAPTER.validate_python(view)
    except ValidationError as error:
        if any(e['type'] != 'finite_number' for e in error.errors()):
            raise
        raise ServingNumericError('Decimal display exceeds existing contract finite-number range') from error
    return Quantity(numerator=str(value.numerator), denominator=str(value.denominator), decimal_view=view)


def _row(row: object) -> dict:
    return {key: _quantity(value) if isinstance(value, Fraction) else value for key, value in asdict(row).items()}


def simulate_serving(request: ServingSimulationInput) -> ServingSimulationResult:
    request = ServingSimulationInput.model_validate(request)
    bom = expand_bom(request.prepared)
    request = ServingSimulationInput(prepared=bom.prepared, arrivals=request.arrivals)
    issues = list(bom.issues)
    prepared = request.prepared
    capture_day = prepared.inventory_as_of.astimezone(ZoneInfo(prepared.timezone)).date()
    ingredients = {i.ingredient_id: i for i in prepared.ingredients}
    stocks = []
    for lot in prepared.lots:
        if lot.received_date is not None and lot.received_date > capture_day:
            issues.append(BOMIssue(code='FUTURE_RECEIPT_NOT_INBOUND', kind='WARNING', field='received_date',
                day=capture_day, affected=[{'entity':'inventory_lot','entity_id':lot.id}],
                impact='Future-dated operational lot excluded throughout simulation',
                suggested_action='Supply explicit hypothetical arrival separately if intended'))
            continue
        # A /2 past scenario activates the *captured current balance* only on its
        # original receipt date. This is an explicit hypothetical assumption, not
        # reconstruction of the actual historical received quantity.
        activation = (lot.received_date if prepared.operational_basis is not None and
                      lot.received_date is not None and
                      lot.received_date > prepared.operational_basis.planning_start_date else None)
        stocks.append(Stock(lot.id, lot.ingredient_id, lot.unit, lot.on_hand_quantity,
                            lot.received_date, lot.expiry_date, activation))
    for arrival in request.arrivals:
        if ingredients[arrival.ingredient_id].expiry_tracking and arrival.expiry_date is None:
            issues.append(BOMIssue(code='MISSING_ARRIVAL_EXPIRY', kind='DATA_BLOCKER', field='expiry_date',
                day=arrival.arrival_day, affected=[{'entity':'inventory_lot','entity_id':arrival.lot_id}],
                impact='Tracked hypothetical stock requires explicit expiry',
                suggested_action='Supply known hypothetical expiry; do not invent one'))
        stocks.append(Stock(arrival.lot_id, arrival.ingredient_id, arrival.unit, arrival.quantity,
                            arrival.arrival_day, arrival.expiry_date, arrival.arrival_day))
    def result(status: str, **rows) -> ServingSimulationResult:
        return ServingSimulationResult(status=status, decision_readiness=(
            'DATA_BLOCKED' if any(i.kind == 'DATA_BLOCKER' for i in issues) else 'NOT_ASSESSED'),
            input=request, bom=bom, issues=tuple(sorted(issues, key=lambda i: (
                i.day or capture_day, i.path_id or '', i.code, str(i.affected)))), **rows)
    if bom.status != 'COMPLETE' or any(i.kind == 'DATA_BLOCKER' for i in issues):
        return result('ARITHMETIC_BLOCKED' if bom.status == 'ARITHMETIC_BLOCKED' else 'DATA_BLOCKED')
    demands = tuple(DemandPoint(path.path_id, d.product_id, d.day, d.quantity) for path in bom.paths for d in path.demands)
    recipes = tuple(DatedRecipe(r.id, r.product_id, r.effective_from, r.effective_to, r.yield_quantity, r.process_loss_rate,
                    tuple(RecipeLine(line.ingredient_id, line.unit, line.quantity) for line in r.lines)) for r in prepared.recipes)
    try:
        computed = simulate(demands, recipes, tuple(stocks), {i.ingredient_id:i.unit for i in prepared.ingredients},
                            {p.product_id:p.selling_unit for p in prepared.products})
        rows = dict(products=tuple(ProductServingDay(**_row(r)) for r in computed.products),
            contributions=tuple(FulfilledContribution(**_row(r)) for r in computed.contributions),
            lots=tuple(LotServingDay(**_row(r)) for r in computed.lots),
            ingredients=tuple(IngredientServingDay(**_row(r)) for r in computed.ingredients))
    except ServingNumericError as error:
        issues.append(BOMIssue(code='SERVING_NUMERIC_BOUNDARY', kind='DATA_BLOCKER', field='quantity',
            affected=[{'entity':'product','entity_id':p} for p in prepared.request.product_ids],
            impact=str(error), suggested_action='Review exact numeric capacity; no partial results or fabricated zero'))
        return result('ARITHMETIC_BLOCKED')
    return result('COMPLETE', **rows)
