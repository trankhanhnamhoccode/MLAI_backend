"""Independent exact output invariants. Never replay allocation or simulation."""
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING, Iterable
from zoneinfo import ZoneInfo

from app.domain.decision.quantities import checked, exact
from app.domain.forecasting.validation import forecast_dates

if TYPE_CHECKING:
    from app.application.contracts.serving import (
        Quantity, ProductServingDay, LotServingDay, IngredientServingDay, ServingSimulationResult,
    )


def q(value: 'Quantity') -> Fraction:
    return checked(Fraction(int(value.numerator), int(value.denominator)))


def total(values: Iterable[Fraction]) -> Fraction:
    result = Fraction(0)
    for value in values:
        result = checked(result + value)
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_product(row: 'ProductServingDay') -> None:
    require(q(row.requested) == total((q(row.fulfilled), q(row.lost)))
            and q(row.fulfilled) <= q(row.requested), 'Product requested/fulfilled/lost must conserve exact quantity')


def validate_lot(row: 'LotServingDay') -> None:
    require(total((q(row.opening), q(row.arrivals))) == total(q(getattr(row, name)) for name in (
        'pre_service_expired', 'consumed', 'close_expired', 'other_waste', 'ending')),
        'Lot opening/arrivals/disposal/consumption/ending must conserve exact quantity')
    require(q(row.other_waste) == 0, 'Lot other_waste must be zero in serving_fefo/1')


def validate_ingredient(row: 'IngredientServingDay') -> None:
    require(q(row.shortage) == checked(max(q(row.requested)-q(row.available), Fraction(0))),
            'Ingredient shortage must equal max(requested-available,0)')
    require(q(row.other_waste) == 0, 'Ingredient other_waste must be zero in serving_fefo/1')
    require(q(row.consumed) <= min(q(row.requested), q(row.available)),
            'Ingredient consumption cannot exceed requested or available quantities')


def index(rows: tuple, expected: set, key, label: str) -> dict:
    mapped = {key(row): row for row in rows}
    require(len(mapped) == len(rows) and set(mapped) == expected, f'{label} coverage/identity must be full and unique')
    return mapped


def validate_result(result: 'ServingSimulationResult') -> None:
    prepared = result.input.prepared
    require(prepared == result.bom.prepared, 'Input and BOM retained snapshot/provenance must agree')
    for issue in result.bom.issues:
        require(issue in result.issues, 'BOM issues/blockers cannot disappear')
    for issue in prepared.issues:
        original = issue.model_dump()
        require(any(i.model_dump(include=set(original)) == original for i in result.bom.issues)
                and any(i.model_dump(include=set(original)) == original for i in result.issues),
                'Captured issues/blockers cannot disappear from BOM or serving output')
    capture_day = prepared.inventory_as_of.astimezone(ZoneInfo(prepared.timezone)).date()
    ingredients = {i.ingredient_id: i for i in prepared.ingredients}
    lots = {lot.id: lot for lot in prepared.lots if lot.received_date is None or lot.received_date <= capture_day}
    arrivals = {a.lot_id: a for a in result.input.arrivals}
    def has_issue(code, kind, identity):
        return any(i.code == code and i.kind == kind and any(
            a.entity == 'inventory_lot' and a.entity_id == identity for a in i.affected) for i in result.issues)
    for lot in prepared.lots:
        if lot.id not in lots:
            require(has_issue('FUTURE_RECEIPT_NOT_INBOUND', 'WARNING', lot.id), 'Excluded future lot warning cannot disappear')
    for a in arrivals.values():
        if ingredients[a.ingredient_id].expiry_tracking and a.expiry_date is None:
            require(has_issue('MISSING_ARRIVAL_EXPIRY', 'DATA_BLOCKER', a.lot_id), 'Tracked arrival expiry blocker cannot disappear')
    if result.status == 'ARITHMETIC_BLOCKED':
        require(result.bom.status == 'ARITHMETIC_BLOCKED' or any(
            i.code == 'SERVING_NUMERIC_BOUNDARY' and i.kind == 'DATA_BLOCKER' for i in result.issues),
            'Arithmetic status requires a numeric-boundary issue')
    if result.status != 'COMPLETE':
        return
    days = forecast_dates(prepared.request.cutoff_date)
    paths = ('LOW', 'BASE', 'HIGH')
    product_ids = prepared.request.product_ids
    products = index(result.products, {(p,d,id) for p in paths for d in days for id in product_ids},
                     lambda r: (r.path_id,r.day,r.product_id), 'Product')
    product_units = {p.product_id: p.selling_unit for p in prepared.products}
    forecast = {(p.forecast_date,p.product_id):p for p in prepared.forecast.predictions}
    selected = {}
    intensity = {}
    for day in days:
        for product in product_ids:
            matches = [r for r in prepared.recipes if r.product_id == product and r.effective_from <= day
                       and (r.effective_to is None or day <= r.effective_to)]
            require(len(matches) == 1 and bool(matches[0].lines), 'Complete serving requires dated nonempty recipe')
            recipe = selected[day,product] = matches[0]
            intensity[day,product] = {line.ingredient_id: checked(exact(line.quantity)/(
                exact(recipe.yield_quantity)*(1-exact(recipe.process_loss_rate)))) for line in recipe.lines}
    expected_contributions = {(path,day,product,selected[day,product].id,line.ingredient_id)
        for path in paths for day in days for product in product_ids for line in selected[day,product].lines}
    contributions = index(result.contributions, expected_contributions,
        lambda r: (r.path_id,r.day,r.product_id,r.recipe_id,r.ingredient_id), 'Contribution')
    for (path,day,product), row in products.items():
        require(row.unit == product_units[product], 'Product selling unit must match capture')
        require(row.recipe_id == selected[day,product].id, 'Product recipe identity must match dated capture')
        quantile = {'LOW':'p25','BASE':'p50','HIGH':'p75'}[path]
        require(q(row.requested) == exact(getattr(forecast[day,product], quantile)), 'Product requested must match captured forecast path')
    for (path,day,product,recipe,ingredient), row in contributions.items():
        require(row.unit == ingredients[ingredient].unit, 'Contribution Ingredient unit must match capture')
        require(q(row.quantity) == checked(q(products[path,day,product].fulfilled)*intensity[day,product][ingredient]),
                'Contribution quantity must equal exact fulfilled dated BOM')
    identities = {*lots, *arrivals}
    lot_rows = index(result.lots, {(p,d,id) for p in paths for d in days for id in identities},
                     lambda r: (r.path_id,r.day,r.lot_id), 'Lot')
    ingredient_rows = index(result.ingredients, {(p,d,id) for p in paths for d in days for id in ingredients},
                     lambda r: (r.path_id,r.day,r.ingredient_id), 'Ingredient')
    def metadata(identity):
        if identity in lots:
            lot = lots[identity]
            return lot.ingredient_id, lot.unit, lot.received_date, lot.expiry_date
        a = arrivals[identity]
        return a.ingredient_id, a.unit, a.arrival_day, a.expiry_date
    fefo = sorted(identities, key=lambda id: (
        metadata(id)[3] is None, metadata(id)[3] or date.max,
        metadata(id)[2] is None, metadata(id)[2] or date.max, id))
    # Available aggregation mirrors canonical captured-lot then arrival order;
    # output row order itself is irrelevant to validation or numeric capacity.
    availability_order = [*sorted(lots), *sorted(arrivals)]
    for path in paths:
        for day_index, day in enumerate(days):
            usable = {}
            for identity in sorted(identities):
                row = lot_rows[path,day,identity]
                ingredient, unit, received, expiry = metadata(identity)
                require((row.ingredient_id,row.unit) == (ingredient,unit), 'Lot Ingredient/unit must match captured or explicit arrival')
                activation = (lots[identity].received_date if identity in lots and
                              prepared.operational_basis is not None and
                              lots[identity].received_date is not None and
                              lots[identity].received_date > prepared.operational_basis.planning_start_date else None)
                first = exact(lots[identity].on_hand_quantity) if identity in lots and activation is None else Fraction(0)
                opening = first if day_index == 0 else q(lot_rows[path,days[day_index-1],identity].ending)
                arrival = exact(arrivals[identity].quantity) if identity in arrivals and arrivals[identity].arrival_day == day else Fraction(0)
                if activation == day:
                    arrival = exact(lots[identity].on_hand_quantity)
                require(q(row.opening) == opening, 'Lot opening must match input or previous ending')
                require(q(row.arrivals) == arrival, 'Lot arrivals must match explicit arrival input')
                gross = total((opening,arrival))
                pre_expired = gross if expiry is not None and expiry < day else Fraction(0)
                require(q(row.pre_service_expired) == pre_expired, 'Lot pre-service expiry timing/quantity incorrect')
                usable[identity] = checked(gross-pre_expired)
                require(q(row.consumed) <= usable[identity], 'Lot consumed exceeds usable stock or uses expired stock')
                remainder = checked(usable[identity]-q(row.consumed))
                closing = remainder if expiry == day else Fraction(0)
                require(q(row.close_expired) == closing, 'Lot close expiry timing/disposal incorrect')
                require(q(row.ending) == checked(remainder-closing), 'Lot ending must equal usable remainder after close')
            for ingredient in sorted(ingredients):
                row = ingredient_rows[path,day,ingredient]
                require(row.unit == ingredients[ingredient].unit, 'Ingredient unit must match capture')
                attributed = [id for id in sorted(identities) if metadata(id)[0] == ingredient]
                full_need = total(checked(q(products[path,day,p].requested)*intensity[day,p][ingredient])
                    for p in product_ids if ingredient in intensity[day,p])
                product_consumption = total(q(contributions[path,day,p,selected[day,p].id,ingredient].quantity)
                    for p in product_ids if ingredient in intensity[day,p])
                require(q(row.requested) == full_need, 'Ingredient requested must match full exact dated BOM')
                require(q(row.available) == total(usable[id] for id in availability_order if metadata(id)[0] == ingredient),
                        'Ingredient available must match usable lots')
                require(q(row.consumed) == product_consumption == total(q(lot_rows[path,day,id].consumed) for id in attributed),
                        'Ingredient consumption must match Product contributions and lot consumption')
                require(q(row.expired) == total(total((q(lot_rows[path,day,id].pre_service_expired),
                    q(lot_rows[path,day,id].close_expired))) for id in attributed), 'Ingredient expired must match lot disposals')
                require(q(row.ending) == total(q(lot_rows[path,day,id].ending) for id in attributed), 'Ingredient ending must match lots')
                require(q(row.other_waste) == total(q(lot_rows[path,day,id].other_waste) for id in attributed), 'Ingredient other waste must match lots')
                earlier_remaining = False
                for identity in fefo:
                    if metadata(identity)[0] != ingredient:
                        continue
                    consumed = q(lot_rows[path,day,identity].consumed)
                    require(not earlier_remaining or consumed == 0, 'FEFO consumes later lot while earlier usable stock remains')
                    earlier_remaining |= usable[identity]-consumed > 0
