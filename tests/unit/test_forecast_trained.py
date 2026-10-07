from datetime import timedelta
from decimal import Decimal, localcontext
import math

import pytest

from app.domain.forecasting.features import FEATURE_NAMES, feature_values
from app.infrastructure.forecast_model import (
    train_quantiles, training_rows, predict_quantiles, inference_readiness,
    postprocess, ModelBoundaryError, ModelNotReadyError,
)
from scripts.forecast_demo import synthetic_input


def test_features_are_causal_and_missing_is_not_zero():
    p = synthetic_input(50, 1)
    origin = p.request.history_start_date + timedelta(days=29)
    known = ((origin, Decimal(0)),)
    original = feature_values(known, origin, 7, 0)
    changed = feature_values(known + ((origin+timedelta(days=1), Decimal(999)),), origin, 7, 0)
    assert original == changed
    assert original[5] == 0 and original[6] is None and original[7] is None
    assert original[8:] == (Decimal(0), 1, Decimal(0), 1)


def test_training_origin_horizon_targets_and_future_correction():
    p = synthetic_input(50, 1)
    rows = training_rows(p)
    observations = {(str(o.product_id),o.sales_date):o.quantity for o in p.observations}
    for key,target,features in zip(rows.keys,rows.targets,rows.features):
        pid, origin, horizon = key
        assert target == observations[pid, origin+timedelta(days=horizon)]
        assert features[1] == horizon
    boundary = p.request.history_start_date + timedelta(days=40)
    data = p.model_dump()
    for o in data['observations']:
        if o['sales_date'] > boundary:
            o['quantity'] = Decimal(1000)
    changed = training_rows(type(p).model_validate(data))
    # Future corrections do not change features even in rows whose target changed.
    assert [(k,f) for k,f in zip(rows.keys,rows.features) if k[1] <= boundary] == [
        (k,f) for k,f in zip(changed.keys,changed.features) if k[1] <= boundary]
    assert [(k,t) for k,t in zip(rows.keys,rows.targets) if k[1]+timedelta(days=k[2]) <= boundary] == [
        (k,t) for k,t in zip(changed.keys,changed.targets) if k[1]+timedelta(days=k[2]) <= boundary]


def test_training_missing_target_skipped_zero_retained():
    p = synthetic_input(45, 1)
    data = p.model_dump()
    data['observations'] = list(data['observations'])
    missing = data['observations'].pop(32)['sales_date']
    data['observations'][-1]['quantity'] = Decimal(0)
    rows = training_rows(type(p).model_validate(data))
    assert all(origin+timedelta(days=h) != missing for _,origin,h in rows.keys)
    assert Decimal(0) in rows.targets


def test_model_train_inference_schema_complete_and_deterministic():
    p = synthetic_input(50)
    model = train_quantiles(p)
    assert all(tuple(b.feature_name()) == FEATURE_NAMES for b in model.boosters)
    with localcontext() as ctx:
        ctx.prec = 3
        result, _, _ = predict_quantiles(model, p)
    second, _, _ = predict_quantiles(train_quantiles(p),p)
    assert result == second
    assert len(result.predictions) == 14
    assert result.model_type == 'lightgbm_quantile'
    assert all(isinstance(r.p25,Decimal) and 0 <= r.p25 <= r.p50 <= r.p75 for r in result.predictions)
    assert [(r.forecast_date,r.product_id) for r in result.predictions] == sorted(
        (r.forecast_date,r.product_id) for r in result.predictions)


def test_readiness_not_quality_and_not_baseline_readiness():
    p = synthetic_input(1,1)
    assert inference_readiness(p)[0].status == 'NOT_READY_HISTORY'
    with pytest.raises(ModelNotReadyError):
        train_quantiles(p)
    p = synthetic_input(28,1)
    assert inference_readiness(p)[0].status == 'READY'
    with pytest.raises(ModelNotReadyError) as error:
        train_quantiles(p)
    assert error.value.readiness[0].status == 'NOT_READY_TRAINING_ROWS'


@pytest.mark.parametrize('values', [(math.nan,1,2),(0,math.inf,2),(0,1,-math.inf)])
def test_nonfinite_output_rejected(values):
    with pytest.raises(ModelBoundaryError):
        postprocess(values)


def test_postprocess_counts_and_float_decimal_policy():
    values,crossed,negatives = postprocess((2.1,-1.0,.3))
    assert values == (Decimal(0),Decimal('.3'),Decimal('2.1'))
    assert crossed and negatives == 1


def test_float_input_overflow_is_error_not_fallback():
    from app.infrastructure.forecast_model import _float
    with pytest.raises(ModelBoundaryError, match='NONFINITE_MODEL_INPUT'):
        _float(Decimal('1e1000'))


def test_native_float32_label_limit_rejected_before_training():
    p = synthetic_input(35,1)
    data = p.model_dump()
    data['observations'][-1]['quantity'] = Decimal('1e40')
    with pytest.raises(ModelBoundaryError,match='MODEL_LABEL_OUT_OF_RANGE'):
        train_quantiles(type(p).model_validate(data))
