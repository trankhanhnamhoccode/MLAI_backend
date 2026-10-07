"""Frozen S2.3 identity/integrity acceptance; no DB."""
import json
from decimal import localcontext

import pytest

from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared, restore_prepared, RetainedInputError
from tests.unit.test_forecast_execution import prepared_values, A


def test_numeric_equivalence_order_and_context():
    values = prepared_values()
    captures = []
    for quantity in ('10', '10.0', '10.00'):
        values['observations'][0]['quantity'] = quantity
        captures.append(serialize_prepared(PreparedForecastInput(**values)))
    assert captures[0] == captures[1] == captures[2]
    values['products'].reverse()
    values['forecast_dates'].reverse()
    assert serialize_prepared(PreparedForecastInput(**values)) == captures[0]
    with localcontext() as context:
        context.prec = 2
        values['observations'][0]['quantity'] = '12345678901234567890.12500'
        captured = serialize_prepared(PreparedForecastInput(**values))
        assert json.loads(captured.canonical_json)['observations'][0]['quantity'] == '12345678901234567890.125'
        assert context.prec == 2
    for quantity in ('0', '-0', '0.000'):
        values['observations'][0]['quantity'] = quantity
        assert json.loads(serialize_prepared(PreparedForecastInput(**values)).canonical_json)['observations'][0]['quantity'] == '0'


@pytest.mark.parametrize('change', ['quantity', 'unit', 'timezone', 'window', 'scope'])
def test_consumed_values_change_identity(change):
    values = prepared_values()
    before = serialize_prepared(PreparedForecastInput(**values))
    if change == 'quantity': values['observations'][0]['quantity'] = '1'
    elif change == 'unit':
        values['products'][1]['selling_unit'] = values['observations'][0]['selling_unit'] = 'glass'
    elif change == 'timezone': values['timezone'] = 'UTC'
    elif change == 'window': values['request']['history_start_date'] = '2026-08-01'
    else:
        values['request']['product_ids'] = [A]
        values['products'] = [values['products'][1]]
    assert serialize_prepared(PreparedForecastInput(**values)).digest != before.digest


def test_roundtrip_and_version_independent_of_prepared_schema():
    original = PreparedForecastInput(**prepared_values())
    encoded = serialize_prepared(original)
    assert encoded.serialization_version == 1 and len(encoded.digest) == 64
    assert restore_prepared(json.loads(encoded.canonical_json), 1, encoded.digest) == original


@pytest.mark.parametrize('kind', ['version', 'hash', 'payload'])
def test_integrity_failure(kind):
    encoded = serialize_prepared(PreparedForecastInput(**prepared_values()))
    payload = json.loads(encoded.canonical_json)
    if kind == 'payload': payload['observations'][0]['quantity'] = '999'
    with pytest.raises(RetainedInputError):
        restore_prepared(payload, 2 if kind == 'version' else 1,
                         '0'*64 if kind == 'hash' else encoded.digest)
