"""Recompute retained A/B/C outputs and inspect causal fit tables without fitting."""
from datetime import date, timedelta

from app.application.contracts.forecast_benchmark import ARMS
from app.application.forecast_benchmark_admission import holdout_dates, next_run
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.forecast_challenger_validation import require
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.forecast_benchmark_features import prepared_at
from app.infrastructure.forecast_benchmark_training import fit_identity, raw_records


def replay_checkpoint(data, plan, task, checkpoint, configuration, storage, artifacts):
    identity = fit_identity(data, plan, task, checkpoint.arm, configuration)
    require(checkpoint.identity == identity and checkpoint.input_digest == identity,
            'FIT_IDENTITY_MISMATCH')
    require(checkpoint.origin == task.origin and checkpoint.status == 'COMPLETED',
            'INCOMPLETE_REPLAY_CHECKPOINT')
    directory = storage.path('fits', identity)
    forbidden = holdout_dates(plan)
    if checkpoint.arm == ARMS[2]:
        rows = storage.load(directory, 'training-table.json')
        for row in rows:
            origin = date.fromisoformat(row['cutoff_date'][:10])
            target = date.fromisoformat(row['target_date'][:10])
            require(origin < target <= task.train_end and target not in forbidden,
                    'TRAINING_LABEL_LEAKAGE')
        for name, start, end, available in (
            ('point-tasks.json', task.point_start, task.point_end, task.train_end),
            ('calibration-tasks.json', task.calibration_start, task.calibration_end, task.point_end),
        ):
            for row in storage.load(directory, name):
                from datetime import datetime
                origin = date.fromisoformat(row['cutoff_date'][:10])
                target = date.fromisoformat(row['target_date'][:10])
                actual = next(o for o in data.observations if str(o.product_id) == row['product_key'] and o.sales_date == target)
                require(available <= origin < target and start <= target <= end and target not in forbidden,
                        'POSTPROCESS_LABEL_LEAKAGE')
                require(actual.is_stockout is False and actual.available_at <= next_run(end, data.timezone)
                        and datetime.fromisoformat(row['actual_known_at']) == actual.available_at,
                        'POSTPROCESS_LABEL_NOT_AVAILABLE')
        result = ForecastChallenger(artifacts, enabled=True).replay(checkpoint.replay_identity)
        require(result.evidence.input.artifact_identity == checkpoint.artifact_identity,
                'NATIVE_ARTIFACT_IDENTITY_MISMATCH')
        output = result.evidence.output
        crossings = tuple((p.product_id, p.forecast_date) for p in output.native_predictions if p.raw_crossing)
        predictions = raw_records(data, task, checkpoint.arm, output.forecast,
                                  intervals=output.cqr, crossings=crossings)
        require(predictions == checkpoint.predictions, 'BENCHMARK_REPLAY_MISMATCH')
        # Native replay checks exact retained evidence, including every stage and raw output.
        return checkpoint.replay_identity
    if checkpoint.arm == ARMS[0]:
        from app.application.use_cases.forecast_baseline import run_historical_quantile_baseline
        result = run_historical_quantile_baseline(prepared_at(data, task.origin, exclude=forbidden))
        predictions = raw_records(data, task, checkpoint.arm, result)
    else:
        import lightgbm as lgb
        from app.application.forecast_serialization import restore_prepared
        from app.infrastructure.forecast_model import QuantileModel, predict_quantiles
        retained = storage.load(directory, 'host-model.json')
        prepared = restore_prepared(retained['prepared'], 1, retained['input_digest'])
        require(prepared == prepared_at(data, task.origin), 'HOST_CAPTURE_MISMATCH')
        require(challenger_digest('host-artifact', retained['files']) == checkpoint.artifact_identity,
                'HOST_ARTIFACT_IDENTITY_MISMATCH')
        for _, origin, horizon in retained['training_keys']:
            target = date.fromisoformat(origin) + timedelta(days=horizon)
            require(target <= task.origin and target not in forbidden, 'HOST_LABEL_LEAKAGE')
        boosters = tuple(lgb.Booster(model_str=retained['files'][f'p{q}.txt']) for q in (25, 50, 75))
        result, crossings, _ = predict_quantiles(QuantileModel(prepared, boosters), prepared)
        predictions = raw_records(data, task, checkpoint.arm, result, crossings=crossings)
    require(predictions == checkpoint.predictions, 'BENCHMARK_REPLAY_MISMATCH')
    return identity
