"""Exact one-order basket arithmetic. Plain Python, no solver/boundary imports."""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from uuid import UUID
from app.domain.decision.quantities import checked, exact


@dataclass(frozen=True)
class Offer:
    id: UUID
    ingredient: UUID
    supplier: UUID
    unit: str
    pack: Decimal
    cost: Decimal
    minimum: int
    upper: int
    lead: int
    shelf: int | None
    lot_id: UUID
    fee: Decimal | None


def pack_quantity(pack: Decimal, count: int) -> Decimal:
    """Integer multiplication is exact even under hostile ambient Decimal context."""
    checked(exact(pack) * count)
    sign, digits, exponent = pack.as_tuple()
    coefficient = int(''.join(map(str, digits))) * count
    return Decimal((sign, tuple(map(int, str(coefficient))), exponent))


def outlay(offers: tuple[Offer, ...], counts: tuple[int, ...], fee_mode: str,
           supplier_fees: tuple[tuple[UUID, Decimal], ...]) -> Fraction:
    value = sum((exact(o.cost)*n for o,n in zip(offers,counts)), Fraction(0))
    if fee_mode == 'PER_OFFER':
        value += sum((exact(o.fee) for o,n in zip(offers,counts) if n), Fraction(0))
    elif fee_mode == 'PER_SUPPLIER_ORDER':
        active = {o.supplier for o,n in zip(offers,counts) if n}
        value += sum((exact(f) for s,f in supplier_fees if s in active), Fraction(0))
    elif fee_mode != 'NONE':
        raise ValueError('Unknown fee mode')
    return checked(value)


def basket_violations(offers: tuple[Offer, ...], counts: tuple[int, ...], spend: Fraction,
                      budget: Decimal | None,
                      limits: tuple[tuple[UUID, UUID, Decimal], ...]) -> tuple[str, ...]:
    errors = []
    if len(counts) != len(offers):
        return ('PACK_VECTOR_LENGTH',)
    if any(type(n) is not int or n < 0 or n > o.upper or (n and n < o.minimum)
           for o,n in zip(offers,counts)):
        return ('PACK_MOQ_BOUNDS',)
    if budget is not None and spend > exact(budget):
        errors.append('BUDGET')
    for supplier, ingredient, maximum in limits:
        qty = sum((exact(o.pack)*n for o,n in zip(offers,counts)
                   if o.supplier == supplier and o.ingredient == ingredient), Fraction(0))
        if qty > exact(maximum):
            errors.append('SUPPLIER_LIMIT')
    return tuple(errors)


def requirements(served: Fraction, requested: Fraction, target: Decimal) -> Fraction:
    """Positive exact shortfall; zero demand vacuously meets a configured target."""
    return checked(max(Fraction(0), exact(target)*requested-served))


def vectors(bounds: tuple[int, ...]):
    """Finite odometer, independent of tests' itertools.product oracle."""
    current = [0]*len(bounds)
    while True:
        yield tuple(current)
        for j in range(len(bounds)-1,-1,-1):
            current[j] += 1
            if current[j] <= bounds[j]:
                break
            current[j] = 0
        else:
            return
