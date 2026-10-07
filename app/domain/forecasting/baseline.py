"""Baseline-specific readiness and exact historical quantiles, without I/O."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, MAX_EMAX, MIN_EMIN, localcontext
from typing import Literal
from uuid import UUID

from app.domain.forecasting.validation import ForecastSemanticError, validate_quantiles

ObservedQuantity = tuple[date, Decimal]
BASELINE_MODEL_TYPE = 'historical_quantile_baseline'
BASELINE_MODEL_VERSION = '1'


@dataclass(frozen=True, slots=True)
class BaselineProductReadiness:
    product_id: UUID
    status: Literal['READY', 'NOT_READY_NO_HISTORY']
    observed_count: int
    first_observed_date: date | None
    last_observed_date: date | None


class BaselineNotReadyError(ForecastSemanticError):
    """All missing-history Products and the complete baseline readiness report."""

    def __init__(self, readiness: tuple[BaselineProductReadiness, ...]) -> None:
        self.readiness = readiness
        self.product_ids = tuple(r.product_id for r in readiness if r.status == 'NOT_READY_NO_HISTORY')
        super().__init__('BASELINE_NOT_READY',
            'Historical quantile baseline has no observed history for Products: '
            + ', '.join(str(p) for p in self.product_ids))


def assess_product_readiness(product_id: UUID,
                             observations: tuple[ObservedQuantity, ...]) -> BaselineProductReadiness:
    """Canonical samples supplied by the validated application capture; no imputation."""
    for _, quantity in observations:
        validate_quantiles(quantity, quantity, quantity)
    if not observations:
        return BaselineProductReadiness(product_id, 'NOT_READY_NO_HISTORY', 0, None, None)
    dates = tuple(day for day, _ in observations)
    return BaselineProductReadiness(product_id, 'READY', len(observations), min(dates), max(dates))


def _linear_quantile(values: tuple[Decimal, ...], q: Decimal) -> Decimal:
    position = Decimal(len(values) - 1) * q
    lower = int(position)  # Nonnegative position: truncation is floor, without float.
    fraction = position - Decimal(lower)
    if fraction == 0:
        return values[lower]
    return values[lower] + (values[lower + 1] - values[lower]) * fraction


def historical_quantiles(quantities: tuple[Decimal, ...]) -> tuple[Decimal, Decimal, Decimal]:
    """Exact linear P25/P50/P75 of actual observed values; empty sample undefined."""
    if not quantities:
        raise ForecastSemanticError('NO_HISTORY', 'Historical quantiles require an observed quantity')
    for quantity in quantities:
        validate_quantiles(quantity, quantity, quantity)
    values = tuple(sorted(quantities))
    # Exact difference/product/sum can span the full integer/fractional digit range.
    # Quarter interpolation adds at most two fractional places; guard digits also
    # cover carries and the (n-1)*q index calculation. Never inherit caller rounding.
    scale = min(v.as_tuple().exponent for v in values)
    precision = max(max(v.adjusted() for v in values) - scale + 4,
                    len(str(len(values))) + 3)
    with localcontext() as context:
        context.prec = precision
        context.Emax = MAX_EMAX
        context.Emin = MIN_EMIN
        context.clamp = 0
        return (_linear_quantile(values, Decimal('0.25')),
                _linear_quantile(values, Decimal('0.50')),
                _linear_quantile(values, Decimal('0.75')))
