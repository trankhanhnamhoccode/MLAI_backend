"""Frozen S2.1 execution acceptance. Synthetic values, no DB/model/provider."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.forecast import CompleteForecastRunInput
from app.application.contracts.forecast_execution import (
    ForecastExecutionInput, PreparedForecastInput, ForecastEngineResult,
    ForecastExecutionPrediction, validate_engine_result,
)
from app.domain.forecasting.validation import (
    ForecastSemanticError, forecast_dates, validate_output_coverage,
    validate_quantiles,
)

STORE, A, B, OTHER = (UUID(int=i) for i in range(100, 104))
D = date(2026, 9, 11)
DATES = tuple(D + timedelta(days=i) for i in range(1, 8))


def request_values():
    return dict(store_id=STORE, product_ids=[B, A], cutoff_date=D,
                history_start_date=date(2026, 9, 1))


def observation(**changes):
    return dict(store_id=STORE, product_id=A, sales_date=D,
                quantity='0', selling_unit='cup') | changes


def prepared_values():
    return dict(request=request_values(), schema_version=1,
                timezone='Asia/Ho_Chi_Minh',
                products=[dict(product_id=B, selling_unit='piece'),
                          dict(product_id=A, selling_unit='cup')],
                observations=[observation()], forecast_dates=list(DATES))


def result_values():
    return dict(model_type='synthetic-fixture', model_version='v1',
                predictions=[dict(product_id=p, forecast_date=d,
                                  p25='0.125', p50='1.375', p75='2.625')
                             for p in (B, A) for d in reversed(DATES)])


@pytest.mark.parametrize('changes', [
    {'product_ids': []}, {'product_ids': [A, A]},
    {'history_start_date': D + timedelta(days=1)}, {'horizon_days': 8},
    {'cutoff_date': date.max},
])
def test_invalid_request(changes):
    with pytest.raises(ValidationError):
        ForecastExecutionInput(**(request_values() | changes))


@pytest.mark.parametrize('cutoff,first,last', [
    (D, date(2026, 9, 12), date(2026, 9, 18)),
    (date(2026, 9, 28), date(2026, 9, 29), date(2026, 10, 5)),
    (date(2026, 12, 29), date(2026, 12, 30), date(2027, 1, 5)),
    (date(2028, 2, 27), date(2028, 2, 28), date(2028, 3, 5)),
])
def test_fixed_seven_business_dates(cutoff, first, last):
    dates = forecast_dates(cutoff)
    assert len(dates) == 7 and dates[0] == first and dates[-1] == last


@pytest.mark.parametrize('zone', ['Invalid/Zone', '', '/absolute', '../UTC'])
def test_timezone_rejected_at_prepared_boundary(zone):
    with pytest.raises(ValidationError):
        PreparedForecastInput(**(prepared_values() | {'timezone': zone}))


@pytest.mark.parametrize('changes', [
    {'schema_version': 2}, {'schema_version': True},
    {'products': []},
    {'products': [dict(product_id=A, selling_unit='cup')]},
    {'products': [dict(product_id=A, selling_unit='cup')] * 2},
    {'products': [dict(product_id=A, selling_unit='cup'), dict(product_id=OTHER, selling_unit='piece')]},
    {'forecast_dates': list(DATES[:-1])},
    {'forecast_dates': [D] + list(DATES[:-1])},
    {'forecast_dates': list(DATES) + [DATES[-1]]},
    {'observations': [observation(), observation()]},
    {'observations': [observation(sales_date=date(2026, 8, 31))]},
    {'observations': [observation(sales_date=D + timedelta(days=1))]},
    {'observations': [observation(store_id=OTHER)]},
    {'observations': [observation(product_id=OTHER)]},
    {'observations': [observation(selling_unit='Cup')]},
    {'observations': [observation(selling_unit=' cup ')]},
    {'observations': [observation(stockout=False)]},
    {'observations': [observation(closure=False)]},
])
def test_invalid_prepared_semantics(changes):
    with pytest.raises(ValidationError):
        PreparedForecastInput(**(prepared_values() | changes))


@pytest.mark.parametrize('quantity', ['-1', 'NaN', 'sNaN', 'Infinity', '-Infinity', 0.5, True, None])
def test_invalid_observed_quantity(quantity):
    with pytest.raises(ValidationError):
        PreparedForecastInput(**(prepared_values() | {'observations': [observation(quantity=quantity)]}))


def test_sparse_explicit_zero_no_fabricated_facts():
    prepared = PreparedForecastInput(**prepared_values())
    assert len(prepared.observations) == 1
    row = prepared.observations[0]
    assert row.quantity == Decimal('0') and row.sales_date == D
    assert set(row.model_dump()) == {'store_id', 'product_id', 'sales_date', 'quantity', 'selling_unit'}
    assert not any(r.product_id == B for r in prepared.observations)
    assert PreparedForecastInput(**(prepared_values() | {'observations': []})).observations == ()


def test_caller_mutation_and_deep_frozen_capture():
    values = prepared_values()
    prepared = PreparedForecastInput(**values)
    values['request']['product_ids'].clear()
    values['products'][0]['selling_unit'] = 'changed'
    values['products'].clear()
    values['observations'][0]['quantity'] = '999'
    values['forecast_dates'].clear()
    assert prepared.request.product_ids == (A, B)
    assert prepared.products[1].selling_unit == 'piece'
    assert prepared.observations[0].quantity == Decimal('0')
    assert prepared.forecast_dates == DATES
    with pytest.raises(ValidationError):
        prepared.observations[0].quantity = Decimal('9')
    exported = prepared.model_dump(mode='json')
    exported['products'][0]['selling_unit'] = 'changed'
    assert prepared.products[0].selling_unit == 'cup'


def test_full_fourteen_keys_accepted_without_rounding_or_artifact():
    prepared = PreparedForecastInput(**prepared_values())
    result = validate_engine_result(prepared, ForecastEngineResult(**result_values()))
    assert len(result.predictions) == 14
    assert {(p.product_id, p.forecast_date) for p in result.predictions} == {
        (p, d) for p in (A, B) for d in DATES}
    assert result.predictions[0].p50 == Decimal('1.375')
    assert result.artifact_identity is None and result.warnings == ()
    baseline = ForecastEngineResult(**(result_values() | {'model_type': 'baseline'}))
    assert baseline.model_type == 'baseline' and baseline.artifact_identity is None


@pytest.mark.parametrize('kind', ['empty', 'missing', 'duplicate', 'wrong_product', 'extra_date', 'cutoff_day'])
def test_output_exact_coverage_rejected(kind):
    values = result_values()
    predictions = values['predictions']
    if kind == 'empty':
        values['predictions'] = []
    elif kind == 'missing':
        predictions.pop()
    elif kind == 'duplicate':
        predictions.append(predictions[0].copy())
    elif kind == 'wrong_product':
        predictions[0]['product_id'] = OTHER
    elif kind == 'extra_date':
        predictions.append(predictions[0] | {'forecast_date': DATES[-1] + timedelta(days=1)})
    else:
        predictions[0]['forecast_date'] = D
    with pytest.raises(ForecastSemanticError):
        validate_engine_result(PreparedForecastInput(**prepared_values()), ForecastEngineResult(**values))


@pytest.mark.parametrize('field', ['p25', 'p50', 'p75'])
@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '-Infinity', True, 0.25])
def test_quantile_boundary_rejects_invalid(field, value):
    values = result_values()['predictions'][0] | {field: value}
    with pytest.raises(ValidationError):
        ForecastExecutionPrediction(**values)


@pytest.mark.parametrize('quantiles', [('2', '1', '3'), ('0', '3', '2')])
def test_unordered_quantiles(quantiles):
    with pytest.raises(ValidationError):
        ForecastExecutionPrediction(product_id=A, forecast_date=DATES[0],
                                    p25=quantiles[0], p50=quantiles[1], p75=quantiles[2])


def test_decimal_policy_accepts_strings_integer_decimal_zero_and_equal():
    prediction = ForecastExecutionPrediction(product_id=A, forecast_date=DATES[0],
                                             p25=0, p50='0', p75=Decimal('0'))
    assert prediction.p25 == prediction.p50 == prediction.p75 == Decimal('0')


@pytest.mark.parametrize('changes', [
    {'model_type': ''}, {'model_version': ' '}, {'artifact_identity': ''},
    {'metrics_json': {}}, {'recommended_strategy': 'LEAN'},
])
def test_invalid_engine_metadata_or_non_forecast_fields(changes):
    with pytest.raises(ValidationError):
        ForecastEngineResult(**(result_values() | changes))


@pytest.mark.parametrize('field', ['model_type', 'model_version'])
def test_actual_metadata_required(field):
    values = result_values()
    del values[field]
    with pytest.raises(ValidationError):
        ForecastEngineResult(**values)


def test_ordering_deterministic_and_result_capture():
    values = prepared_values()
    values['observations'] += [observation(product_id=B, selling_unit='piece', sales_date=date(2026, 9, 1))]
    prepared = PreparedForecastInput(**values)
    reversed_values = dict(values, products=list(reversed(values['products'])),
                           observations=list(reversed(values['observations'])), forecast_dates=list(reversed(DATES)))
    assert PreparedForecastInput(**reversed_values) == prepared
    values = result_values()
    warning = dict(code='SPARSE_HISTORY', severity='WARNING', field='observations',
                   entity='product', impact='Model-specific readiness still required', product_id=B)
    values['warnings'] = [warning, warning | {'product_id': A}]
    result = validate_engine_result(prepared, ForecastEngineResult(**values))
    reverse = dict(values, predictions=list(reversed(values['predictions'])), warnings=list(reversed(values['warnings'])))
    assert validate_engine_result(prepared, ForecastEngineResult(**reverse)) == result
    assert [(p.forecast_date, p.product_id) for p in result.predictions] == sorted(
        (p.forecast_date, p.product_id) for p in result.predictions)
    values['predictions'][0]['p50'] = '99'
    warning['impact'] = 'changed'
    assert result.predictions[-1].p50 == Decimal('1.375')
    assert all(w.impact != 'changed' for w in result.warnings)


def test_validation_revalidates_constructed_boundary_instances():
    prepared = PreparedForecastInput(**prepared_values())
    bad = ForecastEngineResult.model_construct(model_type='', model_version='v1', predictions=())
    with pytest.raises(ValidationError):
        validate_engine_result(prepared, bad)


def test_s1_empty_completion_contract_is_preserved():
    data = CompleteForecastRunInput(store_id=STORE, run_id=A, predictions=(),
                                   completed_at=datetime(2026, 9, 12, tzinfo=timezone.utc), input_fingerprint='fixture')
    assert data.predictions == ()


def test_pure_validation_uses_only_values():
    validate_quantiles(Decimal('0'), Decimal('1.375'), Decimal('2.625'))
    validate_output_coverage((A, B), D, tuple((p, d) for p in (A, B) for d in DATES))
    with pytest.raises(ForecastSemanticError):
        validate_quantiles(Decimal('NaN'), Decimal('1'), Decimal('2'))


def test_domain_validation_import_without_application_frameworks():
    import subprocess
    import sys
    code = '''
import sys
class RejectDependencies:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('pydantic', 'fastapi', 'sqlalchemy', 'httpx',
                                'app.application', 'app.models', 'app.api', 'app.infrastructure')):
            raise AssertionError('Domain imported forbidden dependency: ' + fullname)
sys.meta_path.insert(0, RejectDependencies())
from datetime import date
from decimal import Decimal
from uuid import UUID
from app.domain.forecasting.validation import forecast_dates, validate_quantiles, validate_output_coverage
validate_quantiles(Decimal('0'), Decimal('0.125'), Decimal('1.5'))
validate_output_coverage((UUID(int=1),), date(2026, 9, 11),
    tuple((UUID(int=1), d) for d in forecast_dates(date(2026, 9, 11))))
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)
