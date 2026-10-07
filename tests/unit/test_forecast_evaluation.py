from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

from app.domain.forecasting.evaluation import ScoredPrediction, metric_values
from app.application.use_cases.forecast_evaluation import backtest, at_origin, choose_family
from scripts.forecast_demo import synthetic_input


def test_metrics_zero_denominator_pinball_and_inclusive_coverage():
    points = (ScoredPrediction(date(2026,1,1),UUID(int=1),1,Decimal(0),
        (Decimal(0),Decimal(2),Decimal(4)),True),)
    values = metric_values(points)
    assert values['wape'] is None and values['mae_p50'] == 2
    assert (values['pinball_p25'],values['pinball_p50'],values['pinball_p75']) == (0,1,1)
    assert values['coverage'] == 1 and values['mean_interval_width'] == 4
    assert values['raw_crossings'] == 1 and values['post_crossings'] == 0
    assert metric_values(())['sample_count'] == 0
    assert metric_values(())['coverage'] is None


def test_metrics_are_target_weighted_not_origin_weighted_and_context_independent():
    p = ScoredPrediction(date(2026,1,1),UUID(int=1),1,Decimal(10), (Decimal(0),Decimal(0),Decimal(0)))
    other = ScoredPrediction(date(2026,1,2),UUID(int=2),2,Decimal(0), (Decimal(0),Decimal(0),Decimal(0)))
    expected = metric_values((p,other,other))
    with localcontext() as ctx:
        ctx.prec = 2
        assert metric_values((p,other,other)) == expected
    assert expected['sample_count'] == 3 and expected['wape'] == 1


def test_selection_tie_and_insufficient_never_claim_superiority():
    points = [ScoredPrediction(date(2026,1,d),UUID(int=1),1,Decimal(10),
              (Decimal(10),Decimal(10),Decimal(10))) for d in (1,8)]
    values = dict(lightgbm_quantile=points, historical_quantile_baseline=points)
    assert choose_family(values,2) == ('historical_quantile_baseline','BASELINE_TIE_OR_BETTER')
    assert choose_family(values,1)[1] == 'INSUFFICIENT_VALIDATION'


def test_backtest_temporal_split_missing_breakdowns_and_synthetic_label():
    prepared = synthetic_input(80,2)
    data = prepared.model_dump()
    missing_day = prepared.request.history_start_date.fromordinal(prepared.request.history_start_date.toordinal()+76)
    data['observations'] = [o for o in data['observations'] if not (
        o['sales_date']==missing_day and o['product_id']==prepared.request.product_ids[1])]
    report = backtest(type(prepared).model_validate(data),'SYNTHETIC')
    assert report.real_data_quality == 'NOT EVALUATED'
    assert report.missing_targets == 1
    assert max(report.validation_origins) < min(report.holdout_origins)
    aggregate = [m for m in report.metrics if m.horizon is None and m.product_id is None]
    for partition in ('validation','holdout'):
        both = [m for m in aggregate if m.partition==partition]
        assert both[0].sample_count == both[1].sample_count
        assert both[0].sample_count > 0
    for family in ('lightgbm_quantile','historical_quantile_baseline'):
        total = next(m.sample_count for m in aggregate if m.family==family and m.partition=='holdout')
        assert sum(m.sample_count for m in report.metrics if m.family==family and
            m.partition=='holdout' and m.horizon is None and m.product_id is not None) == total


def test_holdout_actual_corrections_do_not_change_selection_or_validation():
    prepared = synthetic_input(80,1)
    original = backtest(prepared,'SYNTHETIC')
    validation_last_target = original.validation_origins[-1].toordinal()+7
    data = prepared.model_dump()
    for row in data['observations']:
        if row['sales_date'].toordinal() > validation_last_target:
            row['quantity'] = Decimal(999)
    changed = backtest(type(prepared).model_validate(data),'SYNTHETIC')
    assert original.selected_family == changed.selected_family
    assert original.selection_reason == changed.selection_reason
    assert [m for m in original.metrics if m.partition=='validation'] == [
        m for m in changed.metrics if m.partition=='validation']


def test_sparse_product_excludes_scope_without_fabricated_targets():
    prepared = synthetic_input(80,2)
    data = prepared.model_dump()
    pid = prepared.request.product_ids[1]
    data['observations'] = [o for o in data['observations'] if o['product_id'] != pid or o['sales_date'].day==1]
    report = backtest(type(prepared).model_validate(data),'SYNTHETIC')
    assert report.excluded and {e.reason for e in report.excluded} == {'NOT_READY_HISTORY','SCOPE_NOT_READY'}
    assert all(m.sample_count==0 for m in report.metrics)
    assert report.selection_reason == 'INSUFFICIENT_VALIDATION'


def test_short_window_returns_honest_empty_evaluation():
    report = backtest(synthetic_input(35,1),'SYNTHETIC')
    assert not report.validation_origins and not report.holdout_origins
    assert report.selection_reason == 'INSUFFICIENT_VALIDATION'
    assert all(m.mean_pinball is None for m in report.metrics)


def test_date_max_valid_short_window_does_not_overflow_backtest():
    from app.application.contracts.forecast_execution import PreparedForecastInput, ForecastExecutionInput
    from app.domain.forecasting.validation import forecast_dates
    source = synthetic_input(1,1)
    cutoff = date(9999,12,24)
    prepared = PreparedForecastInput(request=ForecastExecutionInput(store_id=source.request.store_id,
        product_ids=source.request.product_ids,history_start_date=cutoff,cutoff_date=cutoff),
        timezone=source.timezone,products=source.products,observations=(),forecast_dates=forecast_dates(cutoff))
    assert not backtest(prepared,'SYNTHETIC').validation_origins
