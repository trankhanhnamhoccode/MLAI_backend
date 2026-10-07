"""Trusted LightGBM boundary: CPU float features/models, exact typed Decimal outputs."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import math

import lightgbm as lgb
import numpy as np
import scipy

from app.application.contracts.forecast_execution import (
    PreparedForecastInput, ForecastEngineResult, ForecastExecutionPrediction,
    ForecastWarning, validate_engine_result,
)
from app.application.contracts.forecast_model import FEATURE_NAMES, MODEL_TYPE, MODEL_VERSION, ModelReadiness
from app.domain.forecasting.features import feature_values


class ModelNotReadyError(Exception):
    def __init__(self, readiness: tuple[ModelReadiness, ...]):
        self.readiness = readiness
        super().__init__('TRAINED_MODEL_NOT_READY')


class ModelBoundaryError(Exception):
    pass


@dataclass(frozen=True)
class TrainingRows:
    features: tuple[tuple[int | Decimal | None, ...], ...]
    targets: tuple[Decimal, ...]
    keys: tuple[tuple[str, date, int], ...]
    readiness: tuple[ModelReadiness, ...]


@dataclass(frozen=True)
class QuantileModel:
    prepared: PreparedForecastInput
    boosters: tuple[lgb.Booster, ...]


def require_dependencies() -> None:
    if (lgb.__version__, np.__version__, scipy.__version__) != ('4.6.0', '2.2.6', '1.17.1'):
        raise ModelBoundaryError('DEPENDENCY_INCOMPATIBLE')


def histories(prepared: PreparedForecastInput):
    return {pid: tuple((r.sales_date, r.quantity) for r in prepared.observations if r.product_id == pid)
            for pid in prepared.request.product_ids}


def inference_readiness(prepared: PreparedForecastInput) -> tuple[ModelReadiness, ...]:
    prepared = PreparedForecastInput.model_validate(prepared)
    return tuple(ModelReadiness(product_id=p, observation_count=len(history),
                 status='READY' if len(history) >= 28 else 'NOT_READY_HISTORY')
                 for p, history in histories(prepared).items())


def training_rows(prepared: PreparedForecastInput) -> TrainingRows:
    prepared = PreparedForecastInput.model_validate(prepared)
    features, targets, keys, readiness = [], [], [], []
    for code, (pid, history) in enumerate(histories(prepared).items()):
        by_date = dict(history)
        count = 0
        origin = prepared.request.history_start_date
        while origin < prepared.request.cutoff_date:
            if sum(day <= origin for day, _ in history) >= 28:
                for horizon in range(1, 8):
                    target_day = origin + timedelta(days=horizon)
                    if target_day <= prepared.request.cutoff_date and target_day in by_date:
                        features.append(feature_values(history, origin, horizon, code))
                        targets.append(by_date[target_day])
                        keys.append((str(pid), origin, horizon))
                        count += 1
            origin += timedelta(days=1)
        readiness.append(ModelReadiness(product_id=pid, observation_count=len(history), supervised_count=count,
            status='NOT_READY_HISTORY' if len(history) < 28 else
                   'NOT_READY_TRAINING_ROWS' if count < 14 else 'READY'))
    return TrainingRows(tuple(features), tuple(targets), tuple(keys), tuple(readiness))


def _float(value: int | Decimal | None) -> float:
    if value is None:
        return math.nan
    converted = float(value)
    if not math.isfinite(converted):
        raise ModelBoundaryError('NONFINITE_MODEL_INPUT')
    return converted


def _matrix(rows) -> np.ndarray:
    return np.asarray([[_float(v) for v in row] for row in rows], dtype=np.float64)


def train_quantiles(prepared: PreparedForecastInput) -> QuantileModel:
    require_dependencies()
    prepared = PreparedForecastInput.model_validate(prepared)
    rows = training_rows(prepared)
    if any(r.status != 'READY' for r in rows.readiness):
        raise ModelNotReadyError(rows.readiness)
    matrix, targets = _matrix(rows.features), np.asarray([_float(v) for v in rows.targets])
    # LightGBM stores labels as float32 even with a float64 input array.
    if np.any(targets > np.finfo(np.float32).max):
        raise ModelBoundaryError('MODEL_LABEL_OUT_OF_RANGE')
    boosters = []
    for q in (.25, .50, .75):
        dataset = lgb.Dataset(matrix, label=targets, feature_name=list(FEATURE_NAMES),
                              categorical_feature=['product_code'], free_raw_data=True)
        boosters.append(lgb.train(dict(objective='quantile', alpha=q, num_threads=1,
            deterministic=True, force_col_wise=True, seed=1729, num_leaves=7,
            learning_rate=.05, min_data_in_leaf=5, verbosity=-1), dataset, num_boost_round=40))
    return QuantileModel(prepared, tuple(boosters))


def postprocess(values: tuple[float, float, float]) -> tuple[tuple[Decimal, ...], bool, int]:
    if any(not math.isfinite(v) for v in values):
        raise ModelBoundaryError('NONFINITE_MODEL_OUTPUT')
    raw = tuple(Decimal(str(float(v))) for v in values)
    crossing = not raw[0] <= raw[1] <= raw[2]
    negatives = sum(v < 0 for v in raw)
    return tuple(sorted(max(Decimal(0), v) for v in raw)), crossing, negatives


def require_compatible(model: QuantileModel, prepared: PreparedForecastInput) -> None:
    source = model.prepared
    if (source.request.store_id != prepared.request.store_id or source.products != prepared.products
            or source.timezone != prepared.timezone or source.request.product_ids != prepared.request.product_ids
            or source.request.cutoff_date > prepared.request.cutoff_date):
        raise ModelBoundaryError('ARTIFACT_SCOPE_OR_CUTOFF_INCOMPATIBLE')


def predict_quantiles(model: QuantileModel, prepared: PreparedForecastInput,
                     artifact_identity: str | None = None) -> tuple[ForecastEngineResult, tuple[tuple, ...], int]:
    require_dependencies()
    prepared = PreparedForecastInput.model_validate(prepared)
    require_compatible(model, prepared)
    readiness = inference_readiness(prepared)
    if any(r.status != 'READY' for r in readiness):
        raise ModelNotReadyError(readiness)
    rows, keys = [], []
    for code, (pid, history) in enumerate(histories(prepared).items()):
        for h, day in enumerate(prepared.forecast_dates, 1):
            rows.append(feature_values(history, prepared.request.cutoff_date, h, code))
            keys.append((pid, day))
    matrix = _matrix(rows)
    predictions = tuple(b.predict(matrix, num_threads=1) for b in model.boosters)
    if len(predictions) != 3 or any(len(p) != len(keys) for p in predictions):
        raise ModelBoundaryError('MODEL_OUTPUT_SHAPE')
    outputs, crossing_keys, negatives = [], [], 0
    for i, (pid, day) in enumerate(keys):
        values, crossed, negative = postprocess(tuple(p[i] for p in predictions))
        if crossed:
            crossing_keys.append((pid, day))
        negatives += negative
        outputs.append(ForecastExecutionPrediction(product_id=pid, forecast_date=day,
                       p25=values[0], p50=values[1], p75=values[2]))
    warnings = []
    if crossing_keys or negatives:
        warnings.append(ForecastWarning(code='QUANTILE_POSTPROCESSING', severity='WARNING',
            field='predictions', entity='ForecastRun',
            impact=f'Clamped {negatives} negative values; rearranged {len(crossing_keys)} crossing rows (version 1).'))
    result = ForecastEngineResult(model_type=MODEL_TYPE, model_version=MODEL_VERSION,
        artifact_identity=artifact_identity, predictions=outputs, warnings=warnings)
    return validate_engine_result(prepared, result), tuple(crossing_keys), negatives
