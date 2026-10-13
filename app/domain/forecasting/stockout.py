"""Observed stockout and causal demand estimates; no persistence or boundary imports."""
from dataclasses import dataclass
from collections import deque
from datetime import date
from decimal import Decimal
from typing import Literal

POLICY_VERSION = 'causal_stockout_v1'
LOOKBACK_DAYS = 42
MIN_SUPPORT = 3


def aggregate_stockout(values: tuple[bool | None, ...]) -> bool | None:
    """Any positive evidence wins; false requires every contribution known false."""
    if any(value is not None and type(value) is not bool for value in values):
        raise ValueError('Stockout must be bool or None')
    if True in values:
        return True
    return False if values and all(value is False for value in values) else None


@dataclass(frozen=True, slots=True)
class Observation:
    day: date
    quantity: Decimal
    stockout: bool | None


@dataclass(frozen=True, slots=True)
class DemandEstimate:
    day: date
    observed_quantity: Decimal
    stockout: bool | None
    demand_quantity: Decimal | None
    method: Literal['OBSERVED', 'UNKNOWN_OBSERVED_COMPATIBILITY', 'PAST_MEDIAN', 'CENSORED_UNSUPPORTED']
    evidence_dates: tuple[date, ...] = ()
    policy_version: str = POLICY_VERSION

    @property
    def usable(self) -> bool:
        return self.demand_quantity is not None


def reconstruct(observations: tuple[Observation, ...], cutoff: date) -> tuple[DemandEstimate, ...]:
    """Only earlier uncensored observations support an estimate, never other estimates.

    Prefer same weekday when >=3 samples exist; otherwise use all earlier known
    uncensored days within 42 days. Median >= observed is a provisional estimator,
    not observed lost demand. Unknown remains usable under explicit compatibility.
    """
    rows = sorted((row for row in observations if row.day <= cutoff), key=lambda row: row.day)
    if len({row.day for row in rows}) != len(rows):
        raise ValueError('Duplicate observation day')
    result = []
    references: deque[Observation] = deque()
    for row in rows:
        if not row.quantity.is_finite() or row.quantity < 0 or (row.stockout is not None and type(row.stockout) is not bool):
            raise ValueError('Invalid observation')
        while references and (row.day - references[0].day).days > LOOKBACK_DAYS:
            references.popleft()
        if row.stockout is not True:
            result.append(DemandEstimate(row.day, row.quantity, row.stockout, row.quantity,
                'OBSERVED' if row.stockout is False else 'UNKNOWN_OBSERVED_COMPATIBILITY'))
            if row.stockout is False:
                references.append(row)
            continue
        support = list(references)
        weekday = [r for r in support if r.day.weekday() == row.day.weekday()]
        if len(weekday) >= MIN_SUPPORT:
            support = weekday
        if len(support) < MIN_SUPPORT:
            result.append(DemandEstimate(row.day, row.quantity, True, None, 'CENSORED_UNSUPPORTED'))
            continue
        values = sorted(r.quantity for r in support)
        # Lower median avoids rounding/context dependence and remains conservative.
        estimate = max(row.quantity, values[(len(values)-1)//2])
        result.append(DemandEstimate(row.day, row.quantity, True, estimate, 'PAST_MEDIAN',
            tuple(r.day for r in support)))
    return tuple(result)
