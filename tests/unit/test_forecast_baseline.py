"""S2.2 baseline acceptance from synthetic captured facts, no DB/model/provider."""
from datetime import date, timedelta
from decimal import Decimal, Inexact, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError

import app.application.use_cases.forecast_baseline as baseline
from app.application.contracts.forecast_execution import PreparedForecastInput, validate_engine_result
from app.domain.forecasting.baseline import BaselineNotReadyError, historical_quantiles
from app.domain.forecasting.validation import ForecastSemanticError, forecast_dates

STORE, A, B, C, E = (UUID(int=i) for i in range(100, 105))
D = date(2026, 9, 11)


def captured_values(samples):
    """Map Products to real observed quantities on distinct dates; never fill gaps."""
    return dict(request=dict(store_id=STORE, product_ids=list(reversed(samples)),
                             cutoff_date=D, history_start_date=date(2026, 1, 1)),
                timezone='Asia/Ho_Chi_Minh',
                products=[dict(product_id=p, selling_unit='cup') for p in reversed(samples)],
                observations=[dict(store_id=STORE, product_id=p,
                                   sales_date=date(2026, 1, 1) + timedelta(days=i),
                                   quantity=q, selling_unit='cup')
                              for p, quantities in samples.items() for i, q in enumerate(quantities)],
                forecast_dates=forecast_dates(D))


def prepared(samples):
    return PreparedForecastInput(**captured_values(samples))


def test_empty_history_readiness_and_execution_failure():
    data = prepared({A: []})
    report = baseline.assess_baseline_readiness(data)
    assert len(report) == 1
    item = report[0]
    assert item.product_id == A and item.status == 'NOT_READY_NO_HISTORY'
    assert item.observed_count == 0
    assert item.first_observed_date is None and item.last_observed_date is None
    with pytest.raises(BaselineNotReadyError) as caught:
        baseline.run_historical_quantile_baseline(data)
    assert caught.value.product_ids == (A,)
    assert caught.value.readiness == report and caught.value.code == 'BASELINE_NOT_READY'


def test_one_observation_ready_and_seven_equal_predictions():
    data = prepared({A: ['12.5']})
    report = baseline.assess_baseline_readiness(data)
    assert report[0].status == 'READY' and report[0].observed_count == 1
    assert report[0].first_observed_date == report[0].last_observed_date == date(2026, 1, 1)
    result = baseline.run_historical_quantile_baseline(data)
    assert len(result.predictions) == 7
    assert all(p.p25 == p.p50 == p.p75 == Decimal('12.5') for p in result.predictions)
    assert tuple(p.forecast_date for p in result.predictions) == forecast_dates(D)


def test_mixed_scope_reports_every_not_ready_product_before_math(monkeypatch):
    data = prepared({A: ['10', '20'], B: [], C: ['5'], E: []})
    report = baseline.assess_baseline_readiness(data)
    assert [(r.product_id, r.status, r.observed_count) for r in report] == [
        (A, 'READY', 2), (B, 'NOT_READY_NO_HISTORY', 0),
        (C, 'READY', 1), (E, 'NOT_READY_NO_HISTORY', 0)]
    def reject_math(*args, **kwargs):
        pytest.fail('Quantiles must not be computed for any Product when scope is not ready')
    monkeypatch.setattr(baseline, 'historical_quantiles', reject_math)
    with pytest.raises(BaselineNotReadyError) as caught:
        baseline.run_historical_quantile_baseline(data)
    assert caught.value.product_ids == (B, E)
    assert caught.value.readiness == report
    assert str(B) in str(caught.value) and str(E) in str(caught.value)


@pytest.mark.parametrize('sample,expected', [
    (['10'], ['10', '10', '10']),
    (['10', '20'], ['12.5', '15', '17.5']),
    (['30', '10', '20'], ['15', '20', '25']),
    (['0', '10', '20'], ['5', '10', '15']),
    (['0', '0', '10', '20'], ['0', '5', '12.5']),
    (['0', '0', '0'], ['0', '0', '0']),
    (['2.125', '2.125'], ['2.125', '2.125', '2.125']),
    (['0.1', '0.2'], ['0.125', '0.15', '0.175']),
    (['1000', '10', '20', '30'], ['17.5', '25', '272.5']),
])
def test_known_exact_historical_quantiles(sample, expected):
    quantities = tuple(Decimal(q) for q in sample)
    assert historical_quantiles(quantities) == tuple(Decimal(q) for q in expected)
    result = baseline.run_historical_quantile_baseline(prepared({A: sample}))
    assert all((p.p25, p.p50, p.p75) == tuple(Decimal(q) for q in expected)
               for p in result.predictions)


def test_missing_day_is_absent_zero_is_real_sample():
    values = captured_values({A: ['10', '0']})
    values['observations'][0]['sales_date'] = date(2026, 9, 7)  # Monday
    values['observations'][1]['sales_date'] = date(2026, 9, 9)  # Wednesday; Tuesday absent
    data = PreparedForecastInput(**values)
    before = data.model_dump()
    report = baseline.assess_baseline_readiness(data)
    assert report[0].observed_count == 2
    assert report[0].first_observed_date == date(2026, 9, 7)
    assert report[0].last_observed_date == date(2026, 9, 9)
    result = baseline.run_historical_quantile_baseline(data)
    assert all((p.p25, p.p50, p.p75) == (Decimal('2.5'), Decimal('5'), Decimal('7.5'))
               for p in result.predictions)
    assert data.model_dump() == before and len(data.observations) == 2


def test_unsorted_history_same_result_and_capture_unchanged():
    data = prepared({A: ['30', '10', '20']})
    before = data.model_dump()
    result = baseline.run_historical_quantile_baseline(data)
    assert result == baseline.run_historical_quantile_baseline(prepared({A: ['10', '20', '30']}))
    assert data.model_dump() == before
    assert tuple(r.quantity for r in data.observations) == tuple(map(Decimal, ['30', '10', '20']))


def test_full_scope_exact_order_metadata_and_determinism():
    data = prepared({B: ['3'], A: ['10', '20']})
    report = baseline.assess_baseline_readiness(data)
    assert report == baseline.assess_baseline_readiness(data)
    assert tuple(r.product_id for r in report) == (A, B)
    result = baseline.run_historical_quantile_baseline(data)
    assert result == baseline.run_historical_quantile_baseline(data)
    assert validate_engine_result(data, result) == result
    assert len(result.predictions) == 14
    assert tuple((p.forecast_date, p.product_id) for p in result.predictions) == tuple(
        (d, p) for d in forecast_dates(D) for p in (A, B))
    assert result.model_type == 'historical_quantile_baseline' and result.model_version == '1'
    assert result.artifact_identity is None and result.warnings == ()
    assert set(result.model_dump()) == {'model_type', 'model_version', 'artifact_identity', 'predictions', 'warnings'}


def test_caller_mutation_after_capture_does_not_change_execution():
    values = captured_values({A: ['10', '20']})
    data = PreparedForecastInput(**values)
    report = baseline.assess_baseline_readiness(data)
    result = baseline.run_historical_quantile_baseline(data)
    values['request']['product_ids'].clear()
    values['products'][0]['selling_unit'] = 'changed'
    values['observations'][0]['quantity'] = '999'
    values['observations'].clear()
    assert baseline.assess_baseline_readiness(data) == report
    assert baseline.run_historical_quantile_baseline(data) == result


def test_readiness_results_are_frozen():
    from dataclasses import FrozenInstanceError
    report = baseline.assess_baseline_readiness(prepared({A: ['0']}))
    assert isinstance(report, tuple) and report[0].status == 'READY'
    with pytest.raises(FrozenInstanceError):
        report[0].observed_count = 99


@pytest.mark.parametrize('sample,expected', [
    (['123456789012345678901234567890.125', '123456789012345678901234567890.135'],
     ['123456789012345678901234567890.1275', '123456789012345678901234567890.130', '123456789012345678901234567890.1325']),
    (['0', '0.00000000000000000000000000001'],
     ['0.0000000000000000000000000000025', '0.000000000000000000000000000005', '0.0000000000000000000000000000075']),
    (['0', '1E+12'], ['2.5E+11', '5E+11', '7.5E+11']),
])
def test_decimal_math_independent_of_ambient_precision_and_exponent_bounds(sample, expected):
    data = prepared({A: sample})
    normal = baseline.run_historical_quantile_baseline(data)
    with localcontext() as context:
        context.prec = 3
        context.Emax = 5
        context.Emin = -5
        context.clamp = 1
        context.traps[Inexact] = True
        result = baseline.run_historical_quantile_baseline(data)
        assert result == normal
        assert context.prec == 3 and context.Emax == 5 and context.Emin == -5 and context.clamp == 1
    assert all((p.p25, p.p50, p.p75) == tuple(Decimal(q) for q in expected) for p in result.predictions)


@pytest.mark.parametrize('value', [Decimal('-1'), Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), True, 1.5])
def test_domain_quantile_helper_rejects_invalid_values(value):
    with pytest.raises(ForecastSemanticError):
        historical_quantiles((value,))


def test_empty_quantile_sample_is_undefined():
    with pytest.raises(ForecastSemanticError):
        historical_quantiles(())


@pytest.mark.parametrize('entrypoint', [baseline.assess_baseline_readiness, baseline.run_historical_quantile_baseline])
@pytest.mark.parametrize('kind', ['duplicate', 'outside_window', 'wrong_product', 'wrong_unit', 'negative'])
def test_safe_entrypoints_revalidate_prepared_instances(entrypoint, kind):
    data = prepared({A: ['10', '20']})
    rows = data.observations
    if kind == 'duplicate':
        rows += (rows[0],)
    else:
        change = {'outside_window': {'sales_date': D + timedelta(days=1)},
                  'wrong_product': {'product_id': B}, 'wrong_unit': {'selling_unit': 'piece'},
                  'negative': {'quantity': Decimal('-1')}}[kind]
        rows = (rows[0].model_copy(update=change),) + rows[1:]
    malformed = data.model_copy(update={'observations': rows})  # Deliberately bypass construction validation.
    with pytest.raises(ValidationError):
        entrypoint(malformed)


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'wrong_product', 'unordered'])
def test_mandatory_final_validator_blocks_malformed_result(monkeypatch, kind):
    data = prepared({A: ['10', '20']})
    real_validator = baseline.validate_engine_result
    calls = []
    def corrupt_then_validate(prepared_input, result):
        calls.append(True)
        predictions = result.predictions
        if kind == 'missing':
            predictions = predictions[:-1]
        elif kind == 'duplicate':
            predictions += (predictions[0],)
        else:
            change = {'product_id': B} if kind == 'wrong_product' else {'p25': Decimal('999')}
            predictions = (predictions[0].model_copy(update=change),) + predictions[1:]
        return real_validator(prepared_input, result.model_copy(update={'predictions': predictions}))
    monkeypatch.setattr(baseline, 'validate_engine_result', corrupt_then_validate)
    with pytest.raises((ForecastSemanticError, ValidationError)):
        baseline.run_historical_quantile_baseline(data)
    assert calls == [True]


def test_domain_baseline_imports_without_application_or_io_dependencies():
    import subprocess
    import sys
    code = '''
import sys
class RejectDependencies:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('pydantic', 'fastapi', 'starlette', 'sqlalchemy', 'psycopg',
                                'httpx', 'requests', 'app.application', 'app.repositories',
                                'app.models', 'app.api', 'app.infrastructure')):
            raise AssertionError('Forbidden domain dependency: ' + fullname)
sys.meta_path.insert(0, RejectDependencies())
from decimal import Decimal
from datetime import date
from uuid import UUID
from app.domain.forecasting.baseline import assess_product_readiness, historical_quantiles
r = assess_product_readiness(UUID(int=1), ((date(2026, 1, 1), Decimal('0')),))
assert r.status == 'READY' and r.observed_count == 1
assert historical_quantiles((Decimal('10'), Decimal('20'))) == (Decimal('12.5'), Decimal('15'), Decimal('17.5'))
'''
    subprocess.run([sys.executable, '-B', '-c', code], check=True, capture_output=True, text=True)
