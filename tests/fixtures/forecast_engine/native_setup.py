"""Tiny bounded synthetic correctness artifact; never research training/promotion.

Three constant-target boosters, 14 rows each, two rounds, one thread. Frozen
synthetic point/CQR offsets exercise stage separation, not fitted accuracy.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
from uuid import UUID

from app.application.contracts.forecast_challenger import (
    ArtifactFile, ChallengerArtifact, ChallengerInput, FitWindow,
)
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.storage.forecast_challenger import ChallengerStorage

STORE = UUID('00000000-0000-0000-0000-000000000001')
PRODUCTS = (UUID('00000000-0000-0000-0000-000000000011'),
            UUID('00000000-0000-0000-0000-000000000012'))


def create_native_fixture(root: Path) -> ChallengerInput:
    import lightgbm as lgb
    import numpy as np
    from shelfcash_forecast.config import ForecastConfig
    from shelfcash_forecast.features.specification import MODEL_FEATURES, CATEGORICAL_MODEL_COLUMNS
    from shelfcash_forecast.calibration.point import PointCorrector, PointCorrectionValue
    from shelfcash_forecast.calibration.cqr import CQRCalibrator, CalibrationValue

    runtime = current_runtime()
    instant = datetime.now(timezone.utc)
    cutoff = (instant + timedelta(hours=7)).date() - timedelta(days=1)
    start = cutoff - timedelta(days=59)
    products = [{'product_id': pid, 'selling_unit': unit} for pid, unit in zip(PRODUCTS, ('cup', 'piece'))]
    config = ForecastConfig(lightgbm_params={'num_threads': 1, 'seed': 42, 'verbosity': -1})
    files = {}
    matrix = np.zeros((14, len(MODEL_FEATURES)))
    for i in range(14):
        matrix[i, 0] = 0
        matrix[i, 1] = i % 2
        matrix[i, 2] = (i % 7) + 1
    for q, offset in [(25, 2.0), (50, 0.0), (75, -2.0)]:
        dataset = lgb.Dataset(matrix, label=np.full(14, offset), feature_name=MODEL_FEATURES,
                              categorical_feature=CATEGORICAL_MODEL_COLUMNS)
        booster = lgb.train({'objective': 'quantile', 'alpha': q/100, 'seed': 42, 'num_threads': 1,
            'verbosity': -1, 'min_data_in_leaf': 1, 'num_leaves': 2, 'deterministic': True,
            'force_col_wise': True}, dataset, num_boost_round=2)
        files[f'model_q{q}.txt'] = booster.model_to_string().encode()
    model_version = 'e2-synthetic-constant-residual/1'
    window = lambda a, b: FitWindow(start=cutoff-timedelta(days=a), end=cutoff-timedelta(days=b),
        labels_available_at=instant-timedelta(seconds=1))
    train, point_window, calibration = window(90, 77), window(76, 63), window(62, 61)
    point = PointCorrector(method='horizon_shrunk_median_residual',
        global_value=PointCorrectionValue(offset=1.0, task_count=14, distinct_target_dates=14, source='synthetic_fixed'),
        by_horizon={}, fit_target_start=str(point_window.start), fit_target_end=str(point_window.end),
        fit_actual_known_at_cutoff=point_window.labels_available_at.isoformat(), model_id=model_version,
        availability_validation='SYNTHETIC_CORRECTNESS_ONLY', availability_timezone='Asia/Ho_Chi_Minh')
    calibrator = CQRCalibrator(desired_coverage=0.5, minimum_samples=20, by_horizon={},
        global_value=CalibrationValue(correction=2.0, sample_count=20, quantile_level=0.5, source='global'),
        calibration_target_semantics='observed_sales_non_stockout',
        fit_target_start=str(calibration.start), fit_target_end=str(calibration.end),
        distinct_target_dates=2, point_corrector_id=model_version)
    native_json = {
        'preprocessing_config.json': config.to_dict(),
        'feature_schema.json': {'schema_version': '3.0', 'features': MODEL_FEATURES,
            'categorical_features': CATEGORICAL_MODEL_COLUMNS, 'target_strategy': 'seasonal_residual_signed',
            'residual_blend_lambda': 1.0},
        'category_mappings.json': {'store_key': {str(STORE): 0},
                                  'product_key': {str(pid): i for i, pid in enumerate(PRODUCTS)}},
        'point_corrector.json': point.to_dict(), 'calibrator.json': calibrator.to_dict(),
        'model_metadata.json': {'model_version': model_version, 'training_label_cutoff': str(train.end),
            'point_fit_label_cutoff': str(point_window.end), 'calibration_label_cutoff': str(calibration.end),
            'artifact_fitted_at': instant.isoformat(), 'promotion_status': 'trained_candidate',
            'production_available_at': None, 'holdout_status': 'SYNTHETIC_ONLY',
            'runtime_versions': {'python_version': runtime.python,
                **{p.name+'_version': p.version for p in runtime.dependencies}}},
        'training_manifest.json': {'scope': {'store_id': STORE, 'products': products,
            'timezone': 'Asia/Ho_Chi_Minh'}, 'purpose': 'SYNTHETIC_CORRECTNESS_ONLY',
            'training_rows': 14, 'rounds': 2, 'constant_residual_targets': [2, 0, -2],
            'postprocess_fixture': 'fixed offsets, not empirical calibration'},
    }
    files.update({name: canonical_bytes(data) for name, data in native_json.items()})
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    files['artifact_checksums.json'] = canonical_bytes({'algorithm': 'sha256', 'files': hashes})
    manifest = ChallengerArtifact(model_version=model_version, purpose='synthetic_correctness',
        holdout_status='SYNTHETIC_ONLY', promotion_status='trained_candidate', production_available_at=None,
        store_id=STORE, products=products, timezone='Asia/Ho_Chi_Minh', runtime=runtime,
        training=train, point_fit=point_window, calibration=calibration, fitted_at=instant,
        published_at=instant, available_at=instant, publication_basis='local_snapshot_admission',
        config_digest=hashes['preprocessing_config.json'], feature_digest=hashes['feature_schema.json'],
        postprocess_digest=challenger_digest('postprocess', {'point': hashes['point_corrector.json'],
            'cqr': hashes['calibrator.json'], 'policy': 'native_stack_weather_excluded/1'}),
        files=tuple(ArtifactFile(name=name, digest=hashlib.sha256(data).hexdigest()) for name, data in files.items()))
    identity = ChallengerStorage(root).publish_artifact(manifest, files)
    observations = []
    for i in range(60):
        if i == 6:  # absent day, not zero
            continue
        for p in products:
            day = start+timedelta(days=i)
            quantity = '0' if i in (0, 1) else '2' if i == 43 else '10'
            observations.append({'store_id': STORE, 'product_id': p['product_id'], 'sales_date': day,
                'selling_unit': p['selling_unit'], 'quantity': quantity,
                'is_stockout': True if i in (0, 43) else None if i == 2 else False,
                'available_at': instant-timedelta(seconds=1), 'source': 'synthetic-raw-observation/1'})
    value = ChallengerInput(request={'store_id': STORE, 'product_ids': PRODUCTS,
        'history_start_date': start, 'cutoff_date': cutoff}, timezone='Asia/Ho_Chi_Minh',
        inference_at=instant+timedelta(seconds=1), products=products, observations=observations,
        forecast_dates=tuple(cutoff+timedelta(days=i) for i in range(1, 8)), artifact_identity=identity,
        calendar=tuple({'store_id': STORE, 'day': start+timedelta(days=i), 'closed': i == 66,
            'holiday': False, 'available_at': instant-timedelta(seconds=1),
            'source': 'synthetic-owner-calendar/1'} for i in range(67)))
    return value
