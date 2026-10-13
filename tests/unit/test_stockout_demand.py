from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.forecasting.stockout import Observation, aggregate_stockout, reconstruct

D = date(2026, 1, 1)


@pytest.mark.parametrize('values,expected', [
    ((), None), ((None, False), None), ((False, False), False),
    ((True, None), True), ((None,), None), ((False,), False), ((True,), True),
])
def test_aggregate_unknown_requires_evidence(values, expected):
    assert aggregate_stockout(values) is expected
    assert aggregate_stockout(tuple(reversed(values))) is expected


def test_causal_reconstruction_observed_zero_and_unsupported():
    rows = tuple(Observation(D+timedelta(days=i), Decimal(q), flag)
                 for i, (q, flag) in enumerate((('0', None), ('1', True), ('10', False),
                    ('20', False), ('30', False), ('2', True), ('999', False))))
    result = reconstruct(rows, D+timedelta(days=5))
    assert result[0].observed_quantity == result[0].demand_quantity == 0
    assert result[0].stockout is None
    assert not result[1].usable and result[1].method == 'CENSORED_UNSUPPORTED'
    assert result[-1].observed_quantity == 2 and result[-1].demand_quantity == 20
    assert result[-1].evidence_dates == tuple(D+timedelta(days=i) for i in (2, 3, 4))
    assert result == reconstruct(rows[:-1], D+timedelta(days=5))


def test_each_origin_ignores_future_support_and_reconstructed_values():
    rows = (Observation(D, Decimal(1), True),) + tuple(
        Observation(D+timedelta(days=i), Decimal(100), False) for i in range(1, 5))
    for i in range(5):
        result = reconstruct(rows, D+timedelta(days=i))
        assert not result[0].usable
        assert result == reconstruct(rows[:i+1], D+timedelta(days=i))


def test_known_zero_never_derived_stockout():
    row = reconstruct((Observation(D, Decimal(0), False),), D)[0]
    assert row.stockout is False and row.method == 'OBSERVED' and row.demand_quantity == 0
