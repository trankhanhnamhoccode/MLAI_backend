"""Compose pinned native inference stages once, without full engine orchestration."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
from uuid import UUID

from pydantic import ValidationError

from app.application.contracts.forecast_challenger import (
    ChallengerError, ChallengerFailure as Failure, ChallengerInput, ChallengerOutput,
    CQRInterval, NativePredictionEvidence, ReconstructionEvidence, RuntimeIdentity,
)
from app.application.contracts.forecast_execution import ForecastEngineResult, ForecastExecutionPrediction
from app.application.forecast_challenger_serialization import canonical_bytes, canonical_value, challenger_digest
from app.application.forecast_challenger_validation import require, validate_output
from app.infrastructure.storage.forecast_challenger import AdmittedArtifactBytes


def native_decimal(value) -> Decimal:
    number = float(value)
    require(math.isfinite(number), 'NONFINITE_NATIVE_VALUE', Failure.TECHNICAL_FAILURE)
    return Decimal(str(number))


def verify_native_manifest(bundle: AdmittedArtifactBytes) -> None:
    """Bytes already checked. Inspect JSON/schema before any booster deserialization."""
    a, directory = bundle.manifest, bundle.directory
    read = lambda name: json.loads((directory / name).read_bytes())
    features = read('feature_schema.json')
    config = read('preprocessing_config.json')
    metadata = read('model_metadata.json')
    point = read('point_corrector.json')
    cqr = read('calibrator.json')
    training = read('training_manifest.json')
    hashes = {f.name: f.digest for f in a.files}
    require(a.config_digest == hashes['preprocessing_config.json'] and
            a.feature_digest == hashes['feature_schema.json'] and
            a.postprocess_digest == challenger_digest('postprocess', {
                'point': hashes['point_corrector.json'], 'cqr': hashes['calibrator.json'],
                'policy': 'native_stack_weather_excluded/1'}),
            'ARTIFACT_COMPONENT_IDENTITY', Failure.ARTIFACT_CORRUPTION)
    from shelfcash_forecast.features.specification import MODEL_FEATURES, CATEGORICAL_MODEL_COLUMNS
    from shelfcash_forecast.config import ForecastConfig
    require(canonical_bytes(ForecastConfig.from_dict(config).to_dict()) == canonical_bytes(config),
            'INCOMPLETE_NATIVE_CONFIGURATION')
    require(features['schema_version'] == '3.0' and features['features'] == MODEL_FEATURES and
            features['categorical_features'] == CATEGORICAL_MODEL_COLUMNS and
            features['target_strategy'] == 'seasonal_residual_signed', 'FEATURE_SCHEMA_UNSUPPORTED')
    require(config['horizons'] == list(range(1, 8)) and config['quantiles'] == [0.25, 0.5, 0.75]
            and config['reconstruction_lookback_days'] == 84 and
            config['reconstruction_minimum_reference_count'] == 3,
            'NATIVE_CONFIGURATION_UNSUPPORTED')
    categories = read('category_mappings.json')
    require(set(categories) == {'store_key', 'product_key'} and
            set(categories['store_key']) == {str(a.store_id)} and
            set(categories['product_key']) == {str(p.product_id) for p in a.products},
            'CATEGORY_SCOPE_MISMATCH')
    for mapping in categories.values():
        require(all(type(c) is int and c >= 0 for c in mapping.values()) and
                len(set(mapping.values())) == len(mapping), 'CATEGORY_SCHEMA_MISMATCH')
    require(metadata['model_version'] == a.model_version and
            metadata['training_label_cutoff'] == str(a.training.end) and
            metadata['point_fit_label_cutoff'] == str(a.point_fit.end) and
            metadata['calibration_label_cutoff'] == str(a.calibration.end) and
            datetime.fromisoformat(metadata['artifact_fitted_at']) == a.fitted_at and
            metadata['promotion_status'] == a.promotion_status and
            metadata['production_available_at'] == (
                None if a.production_available_at is None else a.production_available_at.isoformat()),
            'NATIVE_METADATA_BINDING', Failure.ARTIFACT_CORRUPTION)
    require(metadata['holdout_status'] == a.holdout_status and
            training['scope'] == canonical_value({'store_id': a.store_id,
                'products': a.products, 'timezone': a.timezone}),
            'TRAINING_SCOPE_PROVENANCE_MISSING', Failure.DATA_BLOCKED)
    versions = metadata['runtime_versions']
    pins = {p.name: p.version for p in a.runtime.dependencies}
    require(versions['python_version'] == a.runtime.python and all(
        versions[name + '_version'] == pins[name] for name in ('lightgbm', 'numpy', 'pandas', 'scipy', 'pydantic')),
        'NATIVE_DEPENDENCY_MISMATCH', Failure.DEPENDENCY_MISMATCH)
    require(point['semantics_version'] == 'additive-median-residual-v1' and
            point['fit_target_start'] == str(a.point_fit.start) and
            point['fit_target_end'] == str(a.point_fit.end) and point['model_id'] == a.model_version and
            point['availability_timezone'] == a.timezone and
            datetime.fromisoformat(point['fit_actual_known_at_cutoff']) == a.point_fit.labels_available_at and
            point['calibration_target_semantics'] == 'observed_sales_non_stockout' and
            cqr['semantics_version'] == 'cqr-order-statistic-v2' and
            cqr['fit_target_start'] == str(a.calibration.start) and
            cqr['fit_target_end'] == str(a.calibration.end) and cqr['point_corrector_id'] == a.model_version and
            cqr['calibration_target_semantics'] == 'observed_sales_non_stockout',
            'POSTPROCESS_BINDING_MISMATCH', Failure.ARTIFACT_CORRUPTION)
    require(cqr['desired_coverage'] == config['nominal_coverage'], 'CQR_CONFIG_MISMATCH')


def infer_native(value: ChallengerInput, bundle: AdmittedArtifactBytes,
                 runtime: RuntimeIdentity) -> ChallengerOutput:
    # All optional/native imports are reached only by the opt-in caller.
    import pandas as pd
    from shelfcash_forecast.data.adapter import adapt_forecast_input
    from shelfcash_forecast.data.validator import validate_sales, validate_calendar
    from shelfcash_forecast.data.panel_builder import build_daily_panel, resolve_missing_sales
    from shelfcash_forecast.data.demand_reconstruction import reconstruct_demand
    from shelfcash_forecast.features.historical import add_historical_features
    from shelfcash_forecast.features.training_table import build_runtime_rows, add_target_seasonal_lags
    from shelfcash_forecast.features.future import add_deterministic_future_features, add_calendar_future_features
    from shelfcash_forecast.features.specification import validate_runtime_feature_schema
    from shelfcash_forecast.models.predictor import predict_raw_quantiles
    from shelfcash_forecast.calibration.crossing import correct_quantile_crossing
    from shelfcash_forecast.pipeline.inference_pipeline import (
        ForecastState, correct_forecast_point, calibrate_forecast, build_forecast_package,
    )
    from shelfcash_forecast.registry.loader import load_artifacts
    from shelfcash_forecast.exceptions import ArtifactError, InsufficientDataError, DataValidationError, FeatureSchemaError
    import lightgbm as lgb

    try:
        verify_native_manifest(bundle)
        artifacts = load_artifacts(bundle.directory)
        require(not artifacts.warnings, 'NATIVE_ARTIFACT_WARNING', Failure.ARTIFACT_CORRUPTION)
        for quantile, booster in artifacts.model_bundle.models.items():
            parameters = dict(line[1:-1].split(': ', 1) for line in booster.model_to_string().splitlines()
                              if line.startswith('[') and line.endswith(']') and ': ' in line)
            require(booster.feature_name() == artifacts.model_bundle.feature_names and
                    parameters.get('alpha') == str(quantile) and booster.dump_model()['objective'] == 'quantile',
                    'BOOSTER_SCHEMA_OR_OBJECTIVE', Failure.ARTIFACT_CORRUPTION)
        sales_frame = pd.DataFrame([{
            'date': str(o.sales_date), 'store_id': str(o.store_id), 'product_id': str(o.product_id),
            'product_name': str(o.product_id), 'quantity_sold': float(o.quantity),
            'unit': o.selling_unit, 'is_stockout': o.is_stockout,
        } for o in value.observations])
        require(all(math.isfinite(q) for q in sales_frame['quantity_sold']),
                'QUANTITY_FLOAT_OVERFLOW', Failure.UNSUPPORTED)
        calendar_frame = pd.DataFrame([{'date': str(c.day), 'is_store_closed': c.closed,
                                        'is_holiday': c.holiday} for c in value.calendar])
        adapted = adapt_forecast_input({'sales_history': sales_frame, 'calendar_features': calendar_frame},
                                      artifacts.config)
        sales, quality = validate_sales(adapted.sales_history)
        calendar = validate_calendar(adapted.calendar_features, quality)
        require(len(sales) == len(value.observations) and
                set(quality.warnings) <= {'STOCKOUT_INFORMATION_MISSING'},
                'NATIVE_INPUT_COERCION', Failure.TECHNICAL_FAILURE)
        cutoff = pd.Timestamp(value.request.cutoff_date)
        panel = reconstruct_demand(resolve_missing_sales(build_daily_panel(sales, calendar, end_date=cutoff)),
                                   artifacts.config)
        reconstruction = []
        for r in panel.itertuples(index=False):
            nullable = lambda v: None if pd.isna(v) else native_decimal(v)
            reconstruction.append(ReconstructionEvidence(product_id=UUID(r.product_key), day=r.date.date(),
                row_observed=bool(r.row_observed), observed_sales=nullable(r.observed_sales),
                stockout=None if pd.isna(r.is_stockout) else bool(r.is_stockout),
                demand_proxy=nullable(r.demand_proxy), feature_demand=nullable(r.feature_demand),
                applied=bool(r.reconstruction_applied), method=r.reconstruction_method,
                confidence=r.reconstruction_confidence, reference_count=int(r.reconstruction_reference_count),
                latest_reference=None if pd.isna(r.reconstruction_reference_latest_date)
                    else r.reconstruction_reference_latest_date.date(),
                reference_recency_days=None if pd.isna(r.reconstruction_reference_recency_days)
                    else int(r.reconstruction_reference_recency_days), relative_iqr=nullable(r.reconstruction_relative_iqr),
                rejection_reasons=r.reconstruction_rejection_reasons, train_eligible=bool(r.train_eligible)))
        panel = add_historical_features(panel, artifacts.config)
        frame = build_runtime_rows(panel, cutoff, 7)
        frame = add_target_seasonal_lags(frame, panel, artifacts.config)
        frame = add_calendar_future_features(add_deterministic_future_features(frame), calendar)
        require(frame[['target_temperature', 'target_rainfall']].isna().all().all(),
                'WEATHER_POLICY_VIOLATION', Failure.TECHNICAL_FAILURE)
        frame = artifacts.encoder.transform(frame)
        require(not (frame['product_code'].eq(-1) | frame['store_code'].eq(-1) |
                     frame['history_observation_count'].lt(artifacts.config.minimum_history_observations)).any(),
                'NATIVE_HISTORY_NOT_READY', Failure.DATA_BLOCKED)
        validate_runtime_feature_schema(frame, expected_features=artifacts.model_bundle.feature_names,
                                       expected_categorical_features=artifacts.model_bundle.categorical_features)
        raw = predict_raw_quantiles(artifacts.model_bundle, frame)
        for column in ['model_q25_raw', 'model_q50_raw', 'model_q75_raw', 'p25_raw', 'p50_raw', 'p75_raw']:
            require(all(math.isfinite(float(v)) for v in raw[column]), 'NONFINITE_NATIVE_VALUE', Failure.TECHNICAL_FAILURE)
        repaired = correct_quantile_crossing(raw)
        repaired['forecast_method'] = 'FIXED_LIGHTGBM_POINT_CQR'
        state = ForecastState(repaired, artifacts, cutoff, 7, 'backtest_replay', quality)
        state = correct_forecast_point(state)
        state = calibrate_forecast(state)
        package = build_forecast_package(state)
        units = {p.product_id: p.selling_unit for p in value.products}
        predictions, intervals, diagnostic = [], [], []
        hashes = {f.name: f.digest for f in bundle.manifest.files}
        require(package.model_version == bundle.manifest.model_version, 'NATIVE_MODEL_VERSION', Failure.TECHNICAL_FAILURE)
        row_warnings = {(p.product_id, p.target_date): tuple(p.warnings) for p in package.predictions}
        for p in package.predictions:
            pid = UUID(p.product_id)
            require(p.store_id == str(value.request.store_id) and pid in units and p.unit == units[pid],
                    'NATIVE_OUTPUT_SCOPE_OR_UNIT', Failure.TECHNICAL_FAILURE)
            require(p.horizon == (p.target_date - value.request.cutoff_date).days,
                    'NATIVE_OUTPUT_HORIZON', Failure.TECHNICAL_FAILURE)
            predictions.append(ForecastExecutionPrediction(product_id=pid, forecast_date=p.target_date,
                p25=native_decimal(p.p25), p50=native_decimal(p.p50), p75=native_decimal(p.p75)))
        for r in state.frame.itertuples(index=False):
            pid, day = UUID(r.product_key), r.target_date.date()
            intervals.append(CQRInterval(product_id=pid, forecast_date=day,
                lower=native_decimal(r.interval_lower), upper=native_decimal(r.interval_upper),
                correction=native_decimal(r.calibration_correction), source=r.calibration_source,
                nominal_coverage=Decimal(str(artifacts.calibrator.desired_coverage)),
                calibrator_digest=hashes['calibrator.json'], point_corrector_digest=hashes['point_corrector.json']))
            diagnostic.append(NativePredictionEvidence(product_id=pid, forecast_date=day,
                model_raw=tuple(native_decimal(getattr(r, f'model_q{q}_raw')) for q in (25, 50, 75)),
                quantity_raw=tuple(native_decimal(getattr(r, f'p{q}_raw')) for q in (25, 50, 75)),
                repaired=tuple(native_decimal(getattr(r, f'p{q}_repaired')) for q in (25, 50, 75)),
                point_offset=native_decimal(r.point_correction), raw_crossing=bool(r.had_quantile_crossing),
                target_strategy=r.target_strategy, seasonal_anchor=native_decimal(r.seasonal_anchor),
                anchor_reference_date=None if pd.isna(r.seasonal_reference_date_7)
                    else r.seasonal_reference_date_7.date(), anchor_fallback=bool(r.seasonal_anchor_fallback_used),
                anchor_warning=r.seasonal_anchor_warning, planned_closed=bool(r.target_store_closed),
                warnings=row_warnings[str(pid), day]))
        key = lambda p: (p.forecast_date, p.product_id)
        warnings = set(package.warnings) | {'CHALLENGER_NOT_PROMOTED', 'WEATHER_EXCLUDED_BY_ARM_POLICY'}
        if any(o.is_stockout is None for o in value.observations):
            warnings.add('UNKNOWN_STOCKOUT_OBSERVED_COMPATIBILITY')
        if any(r.stockout is True and not r.applied for r in reconstruction):
            warnings.add('CENSORED_UNSUPPORTED_EXCLUDED')
        if any(r.applied for r in reconstruction):
            warnings.add('NATIVE_RECONSTRUCTION_IS_ESTIMATE')
        output = ChallengerOutput(input_digest=challenger_digest('input', value), runtime=runtime,
            artifact=bundle.manifest, forecast=ForecastEngineResult(model_type=bundle.manifest.model_type,
                model_version=bundle.manifest.model_version, artifact_identity=value.artifact_identity,
                predictions=tuple(predictions)), cqr=tuple(sorted(intervals, key=key)),
            native_predictions=tuple(sorted(diagnostic, key=key)),
            reconstruction=tuple(sorted(reconstruction, key=lambda r: (r.day, r.product_id))),
            warnings=tuple(sorted(warnings)))
        validate_output(value, output)
        return output
    except ChallengerError:
        raise
    except InsufficientDataError as error:
        raise ChallengerError(Failure.DATA_BLOCKED, 'NATIVE_INSUFFICIENT_DATA') from error
    except (ArtifactError, FeatureSchemaError) as error:
        raise ChallengerError(Failure.ARTIFACT_CORRUPTION, 'NATIVE_ARTIFACT_REJECTED') from error
    except (ValidationError, DataValidationError, ValueError, KeyError, TypeError, OverflowError,
            OSError, lgb.basic.LightGBMError) as error:
        raise ChallengerError(Failure.TECHNICAL_FAILURE, 'NATIVE_INFERENCE_FAILED') from error
