"""Causal per-origin feature/label tables using unchanged host and pinned native code."""
from datetime import date, timedelta
from dataclasses import dataclass

from app.application.contracts.forecast_benchmark import BenchmarkDataset, BenchmarkPlan
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_benchmark_admission import at_origin, calendar_at_origin, holdout_dates, next_run
from app.application.forecast_challenger_validation import require
from app.application.contracts.forecast_challenger import ChallengerFailure as Failure


def prepared_at(data: BenchmarkDataset, origin: date, *, exclude=frozenset()) -> PreparedForecastInput:
    observations = at_origin(data, origin)
    require({o.product_id for o in observations} == {p.product_id for p in data.products},
            'PRODUCT_HISTORY_MISSING', Failure.DATA_BLOCKED)
    first = min(o.sales_date for o in observations)
    return PreparedForecastInput(schema_version=2, demand_policy='causal_stockout_v1',
        request={'store_id': data.store_id, 'product_ids': tuple(p.product_id for p in data.products),
                 'history_start_date': first, 'cutoff_date': origin}, timezone=data.timezone,
        products=data.products, observations=tuple(o.model_dump(exclude={'available_at','source'})
            for o in observations if o.sales_date not in exclude),
        forecast_dates=tuple(origin+timedelta(days=h) for h in range(1, 8)))


def native_frame(data: BenchmarkDataset, origin: date, config):
    """One reconstruction from raw observations per independent captured prefix."""
    import pandas as pd
    from shelfcash_forecast.data.adapter import adapt_forecast_input
    from shelfcash_forecast.data.validator import validate_sales, validate_calendar
    from shelfcash_forecast.data.panel_builder import build_daily_panel, resolve_missing_sales
    from shelfcash_forecast.data.demand_reconstruction import reconstruct_demand
    from shelfcash_forecast.features.historical import add_historical_features
    from shelfcash_forecast.features.training_table import build_runtime_rows, add_target_seasonal_lags
    from shelfcash_forecast.features.future import add_calendar_future_features, add_deterministic_future_features
    observations = at_origin(data, origin)
    require(observations, 'PRODUCT_HISTORY_MISSING', Failure.DATA_BLOCKED)
    calendar = calendar_at_origin(data, origin)
    sales = pd.DataFrame([{'date': str(o.sales_date), 'store_id': str(o.store_id),
        'product_id': str(o.product_id), 'product_name': str(o.product_id),
        'quantity_sold': float(o.quantity), 'is_stockout': o.is_stockout, 'unit': o.selling_unit}
        for o in observations])
    dates = pd.DataFrame([{'date': str(c.day), 'is_store_closed': c.closed, 'is_holiday': c.holiday}
                          for c in calendar])
    adapted = adapt_forecast_input({'sales_history':sales, 'calendar_features':dates}, config)
    sales, quality = validate_sales(adapted.sales_history)
    calendar_frame = validate_calendar(adapted.calendar_features, quality)
    panel = reconstruct_demand(resolve_missing_sales(build_daily_panel(sales, calendar_frame, end_date=str(origin))), config)
    features = add_historical_features(panel, config)
    frame = build_runtime_rows(features, pd.Timestamp(origin), 7)
    frame = add_target_seasonal_lags(frame, features, config)
    frame = add_calendar_future_features(add_deterministic_future_features(frame), calendar_frame)
    require(frame[['target_temperature','target_rainfall']].isna().all().all(), 'WEATHER_POLICY_VIOLATION')
    return panel, frame


@dataclass(frozen=True)
class HostRows:
    features: tuple
    targets: tuple
    keys: tuple
    quarantined_labels: int


def host_rows(data: BenchmarkDataset, origin: date, plan: BenchmarkPlan, guard) -> HostRows:
    from app.application.forecast_demand import usable_histories
    from app.domain.forecasting.features import feature_values
    labels = usable_histories(prepared_at(data, origin))
    forbidden = holdout_dates(plan)
    rows, targets, keys, excluded = [], [], [], 0
    first = min(o.sales_date for o in at_origin(data, origin))
    for ordinal in range(first.toordinal()+27, origin.toordinal()):
        guard.check()
        day = date.fromordinal(ordinal)
        history = usable_histories(prepared_at(data, day))
        for code, product in enumerate(data.products):
            samples = history[product.product_id]
            if len(samples) < 28:
                continue
            actuals = dict(labels[product.product_id])
            for h in range(1,8):
                target = day+timedelta(days=h)
                if target > origin or target not in actuals:
                    continue
                if target in forbidden:
                    excluded += 1
                    continue
                rows.append(feature_values(samples, day, h, code))
                targets.append(actuals[target])
                keys.append((str(product.product_id), day, h))
    require(all(sum(k[0]==str(p.product_id) for k in keys) >= 14 for p in data.products),
            'HOST_TRAINING_NOT_READY', Failure.DATA_BLOCKED)
    return HostRows(tuple(rows), tuple(targets), tuple(keys), excluded)


def native_training_table(data: BenchmarkDataset, train_end: date, plan: BenchmarkPlan, config, encoder, guard):
    import pandas as pd
    from shelfcash_forecast.baselines.seasonal_naive import seasonal_naive_predict_rows
    label_panel, _ = native_frame(data, train_end, config)
    labels = {(str(r.product_key),r.date.date()):r for r in label_panel.itertuples(index=False)}
    forbidden = holdout_dates(plan)
    records, excluded = [], 0
    first = min(o.sales_date for o in at_origin(data, train_end))
    for ordinal in range(first.toordinal()+27, train_end.toordinal()):
        guard.check()
        origin = date.fromordinal(ordinal)
        _, frame = native_frame(data, origin, config)
        frame = encoder.transform(frame)
        anchor = seasonal_naive_predict_rows(frame)
        for i, row in frame.iterrows():
            target_day = row.target_date.date()
            label = labels.get((str(row.product_key),target_day))
            if target_day > train_end or label is None or not label.train_eligible or row.history_observation_count < 28:
                continue
            if target_day in forbidden:
                excluded += 1
                continue
            record = row.to_dict()
            record.update(target=float(label.demand_proxy)-float(anchor.loc[i,'prediction']),
                anchor=float(anchor.loc[i,'prediction']), anchor_fallback=bool(anchor.loc[i,'fallback_used']),
                label_quantity=float(label.demand_proxy))
            records.append(record)
    table = pd.DataFrame(records)
    require(not table.empty and table['target_date'].nunique() >= config.walk_forward_minimum_train_days,
            'NATIVE_TRAINING_DATES_INSUFFICIENT', Failure.DATA_BLOCKED)
    require(set(table['product_key']) == {str(p.product_id) for p in data.products},
            'NATIVE_TRAINING_PRODUCT_MISSING', Failure.DATA_BLOCKED)
    return table, excluded


def postprocess_tasks(data: BenchmarkDataset, start: date, end: date, fit_available: date,
                      plan: BenchmarkPlan, config, encoder, model, guard, point=None):
    import pandas as pd
    from shelfcash_forecast.models.predictor import predict_raw_quantiles
    from shelfcash_forecast.calibration.crossing import correct_quantile_crossing
    from shelfcash_forecast.calibration.point import apply_point_corrector
    actuals = {(str(o.product_id),o.sales_date):o for o in data.observations}
    forbidden = holdout_dates(plan)
    records, purge, quarantine, unscoreable = [], 0, 0, 0
    for ordinal in range((start-timedelta(days=7)).toordinal(), end.toordinal()):
        guard.check()
        origin = date.fromordinal(ordinal)
        if origin < fit_available:
            purge += sum(start <= origin+timedelta(days=h) <= end for h in range(1,8))*len(data.products)
            continue
        _, frame = native_frame(data, origin, config)
        frame = encoder.transform(frame)
        frame = correct_quantile_crossing(predict_raw_quantiles(model, frame))
        if point is not None:
            frame = apply_point_corrector(frame, point)
        for _, row in frame.iterrows():
            day = row.target_date.date()
            if not start <= day <= end:
                continue
            if day in forbidden:
                quarantine += 1
                continue
            actual = actuals.get((str(row.product_key),day))
            if actual is None or actual.is_stockout is not False or actual.available_at > next_run(end,data.timezone):
                unscoreable += 1
                continue
            record = row.to_dict()
            record.update(target=float(actual.quantity), actual_known_at=actual.available_at.isoformat())
            records.append(record)
    frame = pd.DataFrame(records)
    require(not frame.empty, 'POSTPROCESS_LABELS_INSUFFICIENT', Failure.DATA_BLOCKED)
    return frame, {'purged':purge, 'holdout_quarantined':quarantine, 'unscoreable':unscoreable}
