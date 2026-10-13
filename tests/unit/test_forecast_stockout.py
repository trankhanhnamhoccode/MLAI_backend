from datetime import timedelta
from decimal import Decimal
import json

import pytest
from pydantic import ValidationError

from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_demand import demand_estimates, usable_histories
from app.application.forecast_serialization import serialize_prepared, restore_prepared
from app.application.use_cases.forecast_baseline import run_historical_quantile_baseline
from app.application.use_cases.forecast_evaluation import at_origin
from app.infrastructure.forecast_model import training_rows
from scripts.forecast_demo import synthetic_input


def prepared():
    original = synthetic_input(50, 1)
    values = original.model_dump()
    values.update(schema_version=2, demand_policy='causal_stockout_v1')
    for row in values['observations']:
        row['is_stockout'] = False
    values['observations'][0].update(is_stockout=True, quantity='0')
    values['observations'][35].update(is_stockout=True, quantity='1')
    return PreparedForecastInput.model_validate(values)


def test_captured_derived_records_and_consumer_preserve_observed_sales():
    p = prepared()
    rows = demand_estimates(p)[p.request.product_ids[0]]
    assert rows[0].method == 'CENSORED_UNSUPPORTED' and not rows[0].usable
    assert rows[35].method == 'PAST_MEDIAN' and rows[35].demand_quantity >= 1
    assert p.observations[35].quantity == 1 and p.observations[0].quantity == 0
    assert p.demand_records[35].evidence_dates == rows[35].evidence_dates
    history = dict(usable_histories(p)[p.request.product_ids[0]])
    assert p.observations[0].sales_date not in history
    assert history[p.observations[35].sales_date] == rows[35].demand_quantity
    codes = {w.code for w in run_historical_quantile_baseline(p).warnings}
    assert codes == {'CENSORED_HISTORY_EXCLUDED', 'DEMAND_RECONSTRUCTED'}


def test_rolling_origins_recompute_from_captured_prefix_only():
    p = prepared()
    origin = p.observations[30].sales_date
    capture = at_origin(p, origin)
    assert all(r.sales_date <= origin and all(d < r.sales_date for d in r.evidence_dates) for r in capture.demand_records)
    before = training_rows(p)
    values = p.model_dump()
    values['demand_records'] = ()
    for r in values['observations']:
        if r['sales_date'] > origin:
            r.update(quantity='99999', is_stockout=True)
    changed = PreparedForecastInput.model_validate(values)
    after = training_rows(changed)
    left = [(k, f) for k, f in zip(before.keys, before.features) if k[1]+timedelta(days=k[2]) <= origin]
    right = [(k, f) for k, f in zip(after.keys, after.features) if k[1]+timedelta(days=k[2]) <= origin]
    assert left == right
    assert serialize_prepared(at_origin(changed, origin)) == serialize_prepared(capture)


def test_digest_observation_correction_retained_and_validation():
    p = prepared()
    encoded = serialize_prepared(p)
    retained = restore_prepared(json.loads(encoded.canonical_json), 1, encoded.digest)
    before = run_historical_quantile_baseline(retained)
    values = p.model_dump()
    values['observations'][35]['is_stockout'] = False
    with pytest.raises(ValidationError):
        PreparedForecastInput.model_validate(values)  # Cannot launder stale derived evidence.
    values['demand_records'] = ()
    corrected = PreparedForecastInput.model_validate(values)
    assert serialize_prepared(corrected).digest != encoded.digest
    assert run_historical_quantile_baseline(retained) == before


def test_legacy_capture_exact_digest_and_unknown_compatibility():
    legacy = synthetic_input(50, 1)
    encoded = serialize_prepared(legacy)
    payload = json.loads(encoded.canonical_json)
    assert 'demand_policy' not in payload and 'demand_records' not in payload
    assert all('is_stockout' not in r for r in payload['observations'])
    newer = PreparedForecastInput.model_validate(legacy.model_dump() | dict(schema_version=2, demand_policy='causal_stockout_v1'))
    assert usable_histories(legacy) == usable_histories(newer)
    old, new = run_historical_quantile_baseline(legacy), run_historical_quantile_baseline(newer)
    assert old.predictions == new.predictions
    assert {w.code for w in new.warnings} == {'STOCKOUT_UNKNOWN'}
