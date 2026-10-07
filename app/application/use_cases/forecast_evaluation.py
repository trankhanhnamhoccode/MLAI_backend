"""Chronological rolling-origin comparison. Actuals are read only after prediction."""
from datetime import date, timedelta

from app.application.contracts.forecast_execution import ForecastExecutionInput, PreparedForecastInput
from app.application.contracts.forecast_model import EvaluationReport, ExcludedOriginProduct, MetricSummary
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_baseline import run_historical_quantile_baseline
from app.domain.forecasting.evaluation import ScoredPrediction, metric_values
from app.domain.forecasting.validation import forecast_dates
from app.infrastructure.forecast_model import train_quantiles, predict_quantiles, ModelNotReadyError


def at_origin(prepared: PreparedForecastInput, origin) -> PreparedForecastInput:
    if not prepared.request.history_start_date <= origin <= prepared.request.cutoff_date:
        raise ValueError('Origin must be inside captured history window')
    return PreparedForecastInput(request=ForecastExecutionInput(store_id=prepared.request.store_id,
        product_ids=prepared.request.product_ids, history_start_date=prepared.request.history_start_date,
        cutoff_date=origin), timezone=prepared.timezone, products=prepared.products,
        observations=tuple(o for o in prepared.observations if o.sales_date <= origin),
        forecast_dates=forecast_dates(origin))


def choose_family(validation, holdout_origins_count: int):
    """Pure selection; accepts validation points, never holdout scores."""
    model, baseline = validation['lightgbm_quantile'], validation['historical_quantile_baseline']
    if (len({p.origin for p in model}) < 2 or holdout_origins_count < 2 or not model
            or len(model) != len(baseline)):
        return 'historical_quantile_baseline', 'INSUFFICIENT_VALIDATION'
    if metric_values(tuple(model))['mean_pinball'] < metric_values(tuple(baseline))['mean_pinball']:
        return 'lightgbm_quantile', 'VALIDATION_IMPROVEMENT'
    return 'historical_quantile_baseline', 'BASELINE_TIE_OR_BETTER'


def backtest(prepared: PreparedForecastInput, dataset_label='USER_PROVIDED_UNVERIFIED') -> EvaluationReport:
    prepared = PreparedForecastInput.model_validate(prepared)
    origins = []
    for ordinal in range(prepared.request.history_start_date.toordinal()+41,
                         prepared.request.cutoff_date.toordinal()-6,7):
        origins.append(date.fromordinal(ordinal))
    midpoint = len(origins)//2
    validation, holdout = tuple(origins[:midpoint]), tuple(origins[midpoint:])
    points = {(family,partition): [] for family in ('lightgbm_quantile','historical_quantile_baseline')
              for partition in ('validation','holdout')}
    excluded, missing = [], 0
    # The actual lookup is never passed into feature generation/training/inference.
    actuals = {(r.product_id,r.sales_date):r.quantity for r in prepared.observations}
    for partition, partition_origins in (('validation', validation), ('holdout',holdout)):
        for origin in partition_origins:
            captured = at_origin(prepared, origin)
            missing += sum((pid,day) not in actuals for pid in captured.request.product_ids
                           for day in captured.forecast_dates)
            try:
                model = train_quantiles(captured)
            except ModelNotReadyError as error:
                excluded.extend(ExcludedOriginProduct(origin=origin, product_id=r.product_id,
                    reason=r.status if r.status != 'READY' else 'SCOPE_NOT_READY') for r in error.readiness)
                continue
            trained, crossings, _ = predict_quantiles(model, captured)
            baseline = run_historical_quantile_baseline(captured)
            for result in (trained,baseline):
                for prediction in result.predictions:
                    key = (prediction.product_id,prediction.forecast_date)
                    if key not in actuals:
                        continue
                    points[result.model_type,partition].append(ScoredPrediction(origin,
                        prediction.product_id, (prediction.forecast_date-origin).days,
                        actuals[key], (prediction.p25,prediction.p50,prediction.p75),
                        result.model_type == 'lightgbm_quantile' and key in crossings))
    validation_points = {family:points[family,'validation'] for family in (
        'lightgbm_quantile','historical_quantile_baseline')}
    usable_holdout = len({p.origin for p in points['lightgbm_quantile','holdout']})
    selected,reason = choose_family(validation_points,usable_holdout)
    metrics = []
    for (family,partition), values in points.items():
        groups = [(None,None,values)]
        groups += [(None,h,[p for p in values if p.horizon==h]) for h in range(1,8)]
        groups += [(pid,None,[p for p in values if p.product_id==pid]) for pid in prepared.request.product_ids]
        groups += [(pid,h,[p for p in values if p.product_id==pid and p.horizon==h])
                   for pid in prepared.request.product_ids for h in range(1,8)]
        for pid,h,group in groups:
            metrics.append(MetricSummary(family=family, partition=partition, product_id=pid,
                horizon=h, **metric_values(tuple(group))))
    return EvaluationReport(dataset_label=dataset_label, input_fingerprint=serialize_prepared(prepared).digest,
        validation_origins=validation, holdout_origins=holdout, missing_targets=missing,
        excluded=excluded, metrics=metrics, selected_family=selected, selection_reason=reason)
