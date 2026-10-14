"""Detached challenger admission: no DB, filesystem, native model or provider."""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from pydantic import ValidationError

from app.application.contracts.forecast_challenger import (
    ChallengerArtifact, ChallengerError, ChallengerFailure as Failure, ChallengerInput,
    ChallengerOutput,
)
from app.domain.forecasting.validation import (
    ForecastSemanticError, validate_output_coverage, validate_prepared_input,
)


def require(condition: bool, code: str, category: Failure = Failure.UNSUPPORTED) -> None:
    if not condition:
        raise ChallengerError(category, code)


def admit_input(value: ChallengerInput) -> None:
    r = value.request
    try:
        zone = ZoneInfo(value.timezone)
        validate_prepared_input(r.store_id, r.product_ids, r.history_start_date, r.cutoff_date,
            tuple((p.product_id, p.selling_unit) for p in value.products),
            tuple((o.store_id, o.product_id, o.sales_date, o.quantity, o.selling_unit)
                  for o in value.observations), value.forecast_dates)
    except (ForecastSemanticError, ValueError, KeyError) as error:
        raise ChallengerError(Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE') from error
    require(value.inference_at.astimezone(zone).date() > r.cutoff_date,
            'INFERENCE_BEFORE_END_OF_CUTOFF', Failure.DATA_BLOCKED)
    require({o.product_id for o in value.observations} == set(r.product_ids),
            'PRODUCT_HISTORY_MISSING', Failure.DATA_BLOCKED)
    require(all(o.available_at <= value.inference_at for o in value.observations),
            'OBSERVATION_NOT_AVAILABLE', Failure.DATA_BLOCKED)
    calendar = {c.day: c for c in value.calendar}
    require(len(calendar) == len(value.calendar), 'DUPLICATE_CALENDAR')
    require(all(c.store_id == r.store_id for c in value.calendar), 'FOREIGN_CALENDAR')
    require(all(c.available_at <= value.inference_at for c in value.calendar),
            'CALENDAR_NOT_AVAILABLE', Failure.DATA_BLOCKED)
    first = min(o.sales_date for o in value.observations)
    days = {first + timedelta(days=i) for i in range((value.forecast_dates[-1] - first).days + 1)}
    require(set(calendar) == days, 'CALENDAR_COVERAGE', Failure.DATA_BLOCKED)
    require(all(not calendar[o.sales_date].closed or o.quantity == 0 for o in value.observations),
            'CLOSED_DAY_OBSERVATION_CONFLICT', Failure.DATA_BLOCKED)


def admit_artifact(value: ChallengerInput, artifact: ChallengerArtifact) -> None:
    require(artifact.store_id == value.request.store_id and artifact.products == value.products
            and artifact.timezone == value.timezone, 'ARTIFACT_SCOPE_OR_UNIT_MISMATCH')
    require(artifact.arm == value.arm and artifact.reconstruction_policy == value.reconstruction_policy,
            'ARTIFACT_POLICY_MISMATCH')
    windows = (artifact.training, artifact.point_fit, artifact.calibration)
    require(all(w.end <= value.request.cutoff_date and w.labels_available_at <= artifact.fitted_at
                for w in windows), 'ARTIFACT_LABELS_NOT_AVAILABLE', Failure.DATA_BLOCKED)
    require(artifact.training.end < artifact.point_fit.start and
            artifact.point_fit.end < artifact.calibration.start,
            'ARTIFACT_FIT_WINDOWS_OVERLAP', Failure.DATA_BLOCKED)
    require(artifact.fitted_at <= artifact.published_at <= artifact.available_at <= value.inference_at,
            'ARTIFACT_NOT_AVAILABLE', Failure.DATA_BLOCKED)
    require(not (artifact.purpose != 'production' and artifact.promotion_status == 'promoted'),
            'RESEARCH_PROMOTION_CONFLICT', Failure.DATA_BLOCKED)
    if value.mode == 'production':
        require(artifact.purpose == 'production' and artifact.promotion_status == 'promoted'
                and artifact.holdout_status == 'UNSEEN' and artifact.production_available_at is not None
                and artifact.available_at <= artifact.production_available_at <= value.inference_at,
                'ARTIFACT_NOT_PRODUCTION_ELIGIBLE', Failure.DATA_BLOCKED)
        require(False, 'PRODUCTION_SERVING_NOT_ENABLED_E2')


def validate_output(value: ChallengerInput, output: ChallengerOutput) -> None:
    try:
        output = ChallengerOutput.model_validate(output)
    except ValidationError as error:
        raise ChallengerError(Failure.TECHNICAL_FAILURE, 'INVALID_NATIVE_OUTPUT') from error
    try:
        validate_output_coverage(value.request.product_ids, value.request.cutoff_date,
            tuple((p.product_id, p.forecast_date) for p in output.forecast.predictions))
    except ForecastSemanticError as error:
        raise ChallengerError(Failure.TECHNICAL_FAILURE, 'NATIVE_OUTPUT_COVERAGE') from error
    keys = {(p.product_id, p.forecast_date) for p in output.forecast.predictions}
    require(output.forecast.artifact_identity == value.artifact_identity and
            output.forecast.model_type == output.artifact.model_type and
            output.forecast.model_version == output.artifact.model_version,
            'OUTPUT_MODEL_IDENTITY', Failure.ARTIFACT_CORRUPTION)
    for rows in (output.cqr, output.native_predictions):
        require(len(rows) == len(keys) and {(p.product_id, p.forecast_date) for p in rows} == keys,
                'DIAGNOSTIC_COVERAGE', Failure.TECHNICAL_FAILURE)
    quantiles = {(p.product_id, p.forecast_date): p for p in output.forecast.predictions}
    calendar = {c.day: c for c in value.calendar}
    observations = {(o.product_id, o.sales_date): o for o in value.observations}
    first = min(o.sales_date for o in value.observations)
    history_dates = {first + timedelta(days=i) for i in range((value.request.cutoff_date-first).days+1)}
    require(len(output.reconstruction) == len(value.request.product_ids)*len(history_dates) and
            {(r.product_id, r.day) for r in output.reconstruction} ==
            {(pid, day) for pid in value.request.product_ids for day in history_dates},
            'RECONSTRUCTION_COVERAGE', Failure.TECHNICAL_FAILURE)
    for row in output.reconstruction:
        original = observations.get((row.product_id, row.day))
        expected_sales = None if original is None or calendar[row.day].closed else Decimal(str(float(original.quantity)))
        require(row.row_observed == (original is not None) and row.observed_sales == expected_sales and
                row.stockout == (None if original is None else original.is_stockout),
                'RECONSTRUCTION_OBSERVATION_MISMATCH', Failure.TECHNICAL_FAILURE)
        if row.latest_reference is not None:
            support = observations.get((row.product_id, row.latest_reference))
            require(row.latest_reference < row.day and (row.day-row.latest_reference).days <= 84 and
                    support is not None and support.is_stockout is False and not calendar[row.latest_reference].closed,
                    'RECONSTRUCTION_SUPPORT_LEAKAGE', Failure.TECHNICAL_FAILURE)
        if row.applied:
            require(row.stockout is True and row.reference_count >= 3 and row.confidence in ('medium', 'high') and
                    row.demand_proxy is not None and row.observed_sales is not None and
                    row.demand_proxy >= row.observed_sales and row.feature_demand == row.demand_proxy,
                    'RECONSTRUCTION_ESTIMATE_INVALID', Failure.TECHNICAL_FAILURE)
    for interval in output.cqr:
        prediction = quantiles[interval.product_id, interval.forecast_date]
        require(interval.lower <= prediction.p50 <= interval.upper and
                0 < interval.nominal_coverage < 1, 'INVALID_CQR_INTERVAL', Failure.TECHNICAL_FAILURE)
        if calendar[interval.forecast_date].closed:
            require(prediction.p25 == prediction.p50 == prediction.p75 == interval.lower == interval.upper == 0,
                    'CLOSED_DAY_NOT_ZERO', Failure.TECHNICAL_FAILURE)
