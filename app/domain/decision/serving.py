"""Pure progressive proportional filling and independent dated FEFO paths."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from app.domain.demand.bom import DatedRecipe, DemandPoint
from app.domain.decision.quantities import checked, exact


@dataclass(frozen=True)
class Stock:
    id: UUID
    ingredient_id: UUID
    unit: str
    quantity: Decimal
    received_date: date | None
    expiry_date: date | None
    arrival_day: date | None = None


@dataclass(frozen=True)
class ProductDay:
    path_id: str
    day: date
    product_id: UUID
    recipe_id: UUID
    unit: str
    requested: Fraction
    fulfilled: Fraction
    lost: Fraction


@dataclass(frozen=True)
class Usage:
    path_id: str
    day: date
    product_id: UUID
    recipe_id: UUID
    ingredient_id: UUID
    unit: str
    quantity: Fraction


@dataclass(frozen=True)
class LotDay:
    path_id: str
    day: date
    lot_id: UUID
    ingredient_id: UUID
    unit: str
    opening: Fraction
    arrivals: Fraction
    pre_service_expired: Fraction
    consumed: Fraction
    close_expired: Fraction
    other_waste: Fraction
    ending: Fraction


@dataclass(frozen=True)
class IngredientDay:
    path_id: str
    day: date
    ingredient_id: UUID
    unit: str
    requested: Fraction
    available: Fraction
    shortage: Fraction
    consumed: Fraction
    expired: Fraction
    other_waste: Fraction
    ending: Fraction


@dataclass(frozen=True)
class Simulation:
    products: tuple[ProductDay, ...]
    contributions: tuple[Usage, ...]
    lots: tuple[LotDay, ...]
    ingredients: tuple[IngredientDay, ...]


def allocate(requested: dict[UUID, Fraction], intensities: dict[UUID, dict[UUID, Fraction]],
             capacity: dict[UUID, Fraction]) -> dict[UUID, Fraction]:
    """Exact progressive filling. Rates equal fractions of original requests."""
    fulfilled = {product: Fraction(0) for product in requested}
    active = {product for product, quantity in requested.items() if quantity > 0}
    remaining = dict(capacity)
    fraction = Fraction(0)
    while active:
        rates: dict[UUID, Fraction] = {}
        for product in sorted(active):
            for ingredient, intensity in intensities[product].items():
                rates[ingredient] = checked(rates.get(ingredient, Fraction(0)) + requested[product]*intensity)
        limits = {ingredient: checked(remaining.get(ingredient, Fraction(0))/rate)
                  for ingredient, rate in rates.items() if rate > 0}
        step = min([1-fraction, *limits.values()])
        if step < 0:
            raise ValueError('Negative capacity violates serving conservation')
        for product in sorted(active):
            fulfilled[product] = checked(fulfilled[product] + requested[product]*step)
        for ingredient, rate in rates.items():
            remaining[ingredient] = checked(remaining.get(ingredient, Fraction(0)) - rate*step)
        fraction = checked(fraction + step)
        if fraction == 1:
            break
        saturated = {ingredient for ingredient, limit in limits.items() if limit == step}
        frozen = {p for p in active if set(intensities[p]) & saturated}
        if not frozen:
            raise ValueError('Progressive filling made no progress')
        active -= frozen
    return fulfilled


def simulate(demands: tuple[DemandPoint, ...], recipes: tuple[DatedRecipe, ...],
             stocks: tuple[Stock, ...], units: dict[UUID, str], product_units: dict[UUID, str]) -> Simulation:
    """Graph/time/blockers are checked at the application boundary, not inferred."""
    products, usages, lot_rows, ingredient_rows = [], [], [], []
    stock_order = sorted(stocks, key=lambda s: (s.expiry_date is None, s.expiry_date or date.max,
                        s.received_date is None, s.received_date or date.max, s.id))
    for path in ('LOW', 'BASE', 'HIGH'):
        balance = {s.id: exact(s.quantity) if s.arrival_day is None else Fraction(0) for s in stocks}
        days = sorted({d.day for d in demands if d.path_id == path})
        for day in days:
            daily = sorted((d for d in demands if d.path_id == path and d.day == day), key=lambda d: d.product_id)
            selected = {}
            for d in daily:
                matches = [r for r in recipes if r.product_id == d.product_id and r.effective_from <= day
                           and (r.effective_to is None or day <= r.effective_to)]
                if len(matches) != 1 or not matches[0].lines:
                    raise ValueError('Serving requires a complete unambiguous dated BOM')
                selected[d.product_id] = matches[0]
            requested = {d.product_id: exact(d.quantity) for d in daily}
            intensity = {p: {line.ingredient_id: checked(exact(line.quantity)/(exact(r.yield_quantity)*(1-exact(r.loss))))
                             for line in r.lines} for p, r in selected.items()}
            opening, arrived, before_expiry = {}, {}, {}
            capacity = {i: Fraction(0) for i in units}
            for stock in stocks:
                opening[stock.id] = balance[stock.id]
                arrived[stock.id] = exact(stock.quantity) if stock.arrival_day == day else Fraction(0)
                balance[stock.id] = checked(balance[stock.id] + arrived[stock.id])
                expired = stock.expiry_date is not None and stock.expiry_date < day
                before_expiry[stock.id] = balance[stock.id] if expired else Fraction(0)
                balance[stock.id] -= before_expiry[stock.id]
                capacity[stock.ingredient_id] = checked(capacity[stock.ingredient_id] + balance[stock.id])
            served = allocate(requested, intensity, capacity)
            consumed = {i: Fraction(0) for i in units}
            full_need = {i: Fraction(0) for i in units}
            for product in sorted(requested):
                recipe = selected[product]
                products.append(ProductDay(path, day, product, recipe.recipe_id, product_units[product],
                                requested[product], served[product], checked(requested[product]-served[product])))
                for ingredient, coefficient in sorted(intensity[product].items()):
                    quantity = checked(served[product]*coefficient)
                    usages.append(Usage(path, day, product, recipe.recipe_id, ingredient, units[ingredient], quantity))
                    consumed[ingredient] = checked(consumed[ingredient]+quantity)
                    full_need[ingredient] = checked(full_need[ingredient]+requested[product]*coefficient)
            need = dict(consumed)
            takes = {}
            for stock in stock_order:
                take = min(balance[stock.id], need[stock.ingredient_id])
                takes[stock.id] = take
                balance[stock.id] = checked(balance[stock.id]-take)
                need[stock.ingredient_id] -= take
            if any(need.values()):
                raise ValueError('Allocated consumption exceeds FEFO capacity')
            expired_total = {i: Fraction(0) for i in units}
            ending = {i: Fraction(0) for i in units}
            for stock in sorted(stocks, key=lambda s: s.id):
                close_expired = balance[stock.id] if stock.expiry_date == day else Fraction(0)
                balance[stock.id] -= close_expired
                expired_total[stock.ingredient_id] = checked(expired_total[stock.ingredient_id] + before_expiry[stock.id]+close_expired)
                ending[stock.ingredient_id] = checked(ending[stock.ingredient_id]+balance[stock.id])
                if opening[stock.id]+arrived[stock.id] != before_expiry[stock.id]+takes[stock.id]+close_expired+balance[stock.id]:
                    raise ValueError('Lot balance does not conserve exact quantity')
                lot_rows.append(LotDay(path, day, stock.id, stock.ingredient_id, stock.unit,
                    opening[stock.id], arrived[stock.id], before_expiry[stock.id], takes[stock.id],
                    close_expired, Fraction(0), balance[stock.id]))
            for ingredient in sorted(units):
                ingredient_rows.append(IngredientDay(path, day, ingredient, units[ingredient], full_need[ingredient],
                    capacity[ingredient], checked(max(full_need[ingredient]-capacity[ingredient], Fraction(0))),
                    consumed[ingredient], expired_total[ingredient], Fraction(0), ending[ingredient]))
    return Simulation(tuple(products), tuple(usages), tuple(lot_rows), tuple(ingredient_rows))
