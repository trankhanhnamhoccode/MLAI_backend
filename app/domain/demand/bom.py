"""Pure dated recipe expansion, without inventory, strategies, providers or I/O."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.domain.demand.arithmetic import BOMArithmeticError, contribution_quantity, exact_quantity_sum


@dataclass(frozen=True)
class DemandPoint:
    path_id: str
    product_id: UUID
    day: date
    quantity: Decimal


@dataclass(frozen=True)
class RecipeLine:
    ingredient_id: UUID
    unit: str
    quantity: Decimal


@dataclass(frozen=True)
class DatedRecipe:
    recipe_id: UUID
    product_id: UUID
    effective_from: date
    effective_to: date | None
    yield_quantity: Decimal
    loss: Decimal
    lines: tuple[RecipeLine, ...]


@dataclass(frozen=True)
class Component:
    path_id: str
    product_id: UUID
    day: date
    recipe_id: UUID
    ingredient_id: UUID
    unit: str
    quantity: Decimal


@dataclass(frozen=True)
class IngredientTotal:
    path_id: str
    day: date
    ingredient_id: UUID
    unit: str
    quantity: Decimal


@dataclass(frozen=True)
class RecipeGap:
    product_id: UUID
    day: date
    code: str


@dataclass(frozen=True)
class Expansion:
    contributions: tuple[Component, ...]
    totals: tuple[IngredientTotal, ...]
    gaps: tuple[RecipeGap, ...]


_PATH_ORDER = {'LOW': 0, 'BASE': 1, 'HIGH': 2}


def expand_dated_bom(demands: tuple[DemandPoint, ...], recipes: tuple[DatedRecipe, ...]) -> Expansion:
    """Input graph is checked at the application boundary. No partial success."""
    selected = {}
    gaps = []
    for product, day in sorted({(d.product_id, d.day) for d in demands}, key=lambda k: (k[1], k[0])):
        choices = [r for r in recipes if r.product_id == product and r.effective_from <= day
                   and (r.effective_to is None or day <= r.effective_to)]
        if len(choices) > 1:
            raise ValueError('Overlapping recipe versions must be rejected, not resolved')
        if not choices or not choices[0].lines:
            gaps.append(RecipeGap(product, day, 'MISSING_RECIPE' if not choices else 'EMPTY_RECIPE'))
        else:
            selected[product, day] = choices[0]
    if gaps:
        return Expansion((), (), tuple(gaps))
    components = []
    groups: dict[tuple[str, date, UUID, str], list[Decimal]] = {}
    for demand in sorted(demands, key=lambda d: (_PATH_ORDER[d.path_id], d.day, d.product_id)):
        recipe = selected[demand.product_id, demand.day]
        for line in sorted(recipe.lines, key=lambda l: l.ingredient_id):
            try:
                quantity = contribution_quantity(demand.quantity, line.quantity, recipe.yield_quantity, recipe.loss)
            except BOMArithmeticError as error:
                raise BOMArithmeticError(error.code, str(error), path_id=demand.path_id,
                    product_id=demand.product_id, day=demand.day, ingredient_id=line.ingredient_id) from error
            components.append(Component(demand.path_id, demand.product_id, demand.day, recipe.recipe_id,
                                        line.ingredient_id, line.unit, quantity))
            groups.setdefault((demand.path_id, demand.day, line.ingredient_id, line.unit), []).append(quantity)
    totals = []
    for (path, day, ingredient, unit), quantities in sorted(
            groups.items(), key=lambda kv: (_PATH_ORDER[kv[0][0]], *kv[0][1:])):
        try:
            total = exact_quantity_sum(tuple(quantities))
        except BOMArithmeticError as error:
            raise BOMArithmeticError(error.code, str(error), path_id=path, day=day, ingredient_id=ingredient) from error
        totals.append(IngredientTotal(path, day, ingredient, unit, total))
    return Expansion(tuple(components), tuple(totals), ())
