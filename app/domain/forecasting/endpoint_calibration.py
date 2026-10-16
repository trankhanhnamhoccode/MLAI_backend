"""One offline endpoint method and shared factual closure policy; no IO or models."""
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from math import ceil

F = Fraction
POLICY_VERSION = 'shared_explicit_closure/1'
METHOD_VERSION = 'pooled_horizon_endpoint_residual_nearest_rank/1'


@dataclass(frozen=True)
class ClosureFact:
    store: str
    day: date
    closed: bool | None
    holiday: bool | None
    available_at: datetime | None
    source: str | None


def closure_state(facts: tuple[ClosureFact, ...], store: str, day: date,
                  at: datetime) -> str:
    rows = tuple(r for r in facts if r.day == day)
    if any(r.store != store for r in rows):
        raise ValueError('CLOSURE_STORE_CONFLICT')
    if len(rows) > 1:
        raise ValueError('CLOSURE_DUPLICATE_OR_CONFLICT')
    if not rows:
        return 'UNKNOWN'
    r = rows[0]
    if r.available_at is None or not r.source or r.available_at > at or r.closed is None:
        return 'UNKNOWN'
    return 'CLOSED' if r.closed else 'OPEN'


def common_closure(quantiles: tuple[F, F, F], interval: tuple[F, F] | None,
                   state: str, *, applied_policy: str | None = None):
    if applied_policy is not None:
        raise ValueError('CLOSURE_POLICY_ALREADY_APPLIED')
    if state not in ('OPEN', 'CLOSED', 'UNKNOWN'):
        raise ValueError('INVALID_CLOSURE_STATE')
    if not F(0) <= quantiles[0] <= quantiles[1] <= quantiles[2]:
        raise ValueError('INVALID_RAW_QUANTILES')
    if state == 'CLOSED':
        return (F(0), F(0), F(0)), None if interval is None else (F(0), F(0))
    return quantiles, interval


@dataclass(frozen=True)
class EndpointSample:
    product: str
    unit: str
    target: date
    feature_origin: date
    known_at: datetime
    actual: F
    lower: F
    upper: F


@dataclass(frozen=True)
class EndpointFit:
    status: str
    reason: str | None
    lower_delta: F
    upper_delta: F
    tasks: int
    dates: int
    products: tuple[str, ...]
    lower_rank: int
    upper_rank: int


def empirical_quantile(values: tuple[F, ...], probability: F) -> tuple[F, int]:
    if not values or not F(0) < probability < F(1):
        raise ValueError('INVALID_EMPIRICAL_QUANTILE')
    rank = ceil(len(values) * probability)
    return sorted(values)[rank - 1], rank


def fit_endpoints(samples: tuple[EndpointSample, ...], *, products: tuple[str, ...],
                  unit: str, start: date, end: date, point_end: date,
                  forecast_origin: date, available_at: datetime,
                  quarantined: frozenset[date], minimum_tasks: int = 30,
                  minimum_dates: int = 7) -> EndpointFit:
    if not point_end < start <= end <= forecast_origin:
        raise ValueError('ENDPOINT_WINDOW_ORDER')
    keys = [(s.product, s.feature_origin, s.target) for s in samples]
    if len(set(keys)) != len(keys):
        raise ValueError('ENDPOINT_DUPLICATE_TASK')
    for s in samples:
        if not point_end <= s.feature_origin < s.target or not start <= s.target <= end:
            raise ValueError('ENDPOINT_CAUSAL_WINDOW')
        if s.target in quarantined or s.known_at > available_at:
            raise ValueError('ENDPOINT_LABEL_NOT_ELIGIBLE')
        if s.unit != unit or s.product not in products or s.actual < 0 or s.lower < 0 or s.upper < s.lower:
            raise ValueError('ENDPOINT_SCOPE_UNIT_OR_VALUE')
    dates = len({s.target for s in samples})
    observed_products = tuple(sorted({s.product for s in samples}))
    if len(samples) < minimum_tasks or dates < minimum_dates or set(observed_products) != set(products):
        return EndpointFit('NOT_FITTED', 'MINIMUM_30_TASKS_7_DATES_ALL_PRODUCTS', F(0), F(0),
                           len(samples), dates, observed_products, 0, 0)
    lower, lr = empirical_quantile(tuple(s.actual - s.lower for s in samples), F(1, 4))
    upper, ur = empirical_quantile(tuple(s.actual - s.upper for s in samples), F(3, 4))
    return EndpointFit('FITTED', None, lower, upper, len(samples), dates, observed_products, lr, ur)


def correct_endpoints(quantiles: tuple[F, F, F], fit: EndpointFit):
    if fit.status != 'FITTED':
        return quantiles, dict(adjusted=False, lower_nonnegative_clamp=False,
                               lower_median_clamp=False, upper_median_clamp=False, raw_crossing=False)
    low, median, high = quantiles
    raw_low, raw_high = low + fit.lower_delta, high + fit.upper_delta
    final = max(F(0), min(median, raw_low)), median, max(median, raw_high)
    return final, dict(adjusted=True, lower_nonnegative_clamp=raw_low < 0,
                      lower_median_clamp=raw_low > median, upper_median_clamp=raw_high < median,
                      raw_crossing=not raw_low <= median <= raw_high)
