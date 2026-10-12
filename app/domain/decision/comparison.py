"""Exact comparison arithmetic only; no solver, simulator or presentation policy."""
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from uuid import UUID
from app.domain.decision.quantities import checked


class ComparisonNumericError(ValueError):
    """The entire comparison exceeds the canonical exact numeric envelope."""


def total(values) -> Fraction:
    return checked(sum(values, Fraction(0)))


def delta(before: Fraction, after: Fraction) -> Fraction:
    return checked(after-before)


@dataclass(frozen=True)
class ProductObservation:
    path: str
    product_id: UUID
    unit: str
    requested: Fraction
    fulfilled: Fraction
    lost: Fraction


@dataclass(frozen=True)
class ProductTotals:
    path: str
    product_id: UUID
    unit: str
    requested: Fraction
    fulfilled: Fraction
    lost: Fraction
    service: Fraction | None


def product_totals(rows: tuple[ProductObservation, ...]) -> tuple[ProductTotals, ...]:
    grouped={}
    for row in rows:
        grouped.setdefault((row.path,row.product_id,row.unit),[]).append(row)
    result=[]
    for (path,product,unit),values in sorted(grouped.items()):
        requested=total(v.requested for v in values)
        fulfilled=total(v.fulfilled for v in values)
        lost=total(v.lost for v in values)
        if requested!=fulfilled+lost:raise ValueError('Product conservation mismatch')
        result.append(ProductTotals(path,product,unit,requested,fulfilled,lost,
                                    None if not requested else checked(fulfilled/requested)))
    return tuple(result)


@dataclass(frozen=True)
class IngredientObservation:
    path: str
    day: date
    ingredient_id: UUID
    unit: str
    shortage: Fraction
    ending: Fraction
    expired: Fraction
    other_waste: Fraction


@dataclass(frozen=True)
class IngredientTotals:
    path: str
    ingredient_id: UUID
    unit: str
    daily_shortage_sum: Fraction
    horizon_ending: Fraction
    expired: Fraction
    other_waste: Fraction


def ingredient_totals(rows: tuple[IngredientObservation, ...], end_day: date) -> tuple[IngredientTotals, ...]:
    grouped={}
    for row in rows:
        grouped.setdefault((row.path,row.ingredient_id,row.unit),[]).append(row)
    result=[]
    for (path,ingredient,unit),values in sorted(grouped.items()):
        end=[v for v in values if v.day==end_day]
        if len(end)!=1:raise ValueError('Ingredient requires exactly one horizon-ending row')
        result.append(IngredientTotals(path,ingredient,unit,total(v.shortage for v in values),
            checked(end[0].ending),total(v.expired for v in values),total(v.other_waste for v in values)))
    return tuple(result)
