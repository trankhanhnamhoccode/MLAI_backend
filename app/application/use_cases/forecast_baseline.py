"""Safe internal baseline entrypoints; no Session, run lifecycle or persistence."""
from uuid import UUID

from app.application.contracts.forecast_execution import (
    ForecastEngineResult, ForecastExecutionPrediction, PreparedForecastInput, validate_engine_result,
)
from app.domain.forecasting.baseline import (
    BaselineNotReadyError, BaselineProductReadiness, ObservedQuantity,
    assess_product_readiness, historical_quantiles,
    BASELINE_MODEL_TYPE, BASELINE_MODEL_VERSION,
)


def _validated_histories(prepared: PreparedForecastInput) -> tuple[
        PreparedForecastInput, dict[UUID, tuple[ObservedQuantity, ...]]]:
    prepared = PreparedForecastInput.model_validate(prepared)
    histories: dict[UUID, list[ObservedQuantity]] = {p: [] for p in prepared.request.product_ids}
    for row in prepared.observations:
        histories[row.product_id].append((row.sales_date, row.quantity))
    return prepared, {p: tuple(rows) for p, rows in histories.items()}


def _readiness(histories: dict[UUID, tuple[ObservedQuantity, ...]]) -> tuple[BaselineProductReadiness, ...]:
    return tuple(assess_product_readiness(p, rows) for p, rows in histories.items())


def assess_baseline_readiness(prepared: PreparedForecastInput) -> tuple[BaselineProductReadiness, ...]:
    """Validate capture, then report every requested Product in canonical UUID order."""
    _, histories = _validated_histories(prepared)
    return _readiness(histories)


def run_historical_quantile_baseline(prepared: PreparedForecastInput) -> ForecastEngineResult:
    """Validate -> all-Product readiness -> exact quantiles -> mandatory result gate."""
    prepared, histories = _validated_histories(prepared)
    report = _readiness(histories)
    if any(r.status == 'NOT_READY_NO_HISTORY' for r in report):
        raise BaselineNotReadyError(report)
    quantiles = {p: historical_quantiles(tuple(q for _, q in rows)) for p, rows in histories.items()}
    predictions = tuple(ForecastExecutionPrediction(
        product_id=p, forecast_date=day, p25=quantiles[p][0],
        p50=quantiles[p][1], p75=quantiles[p][2],
    ) for day in prepared.forecast_dates for p in prepared.request.product_ids)
    result = ForecastEngineResult(model_type=BASELINE_MODEL_TYPE, model_version=BASELINE_MODEL_VERSION,
                                  artifact_identity=None, predictions=predictions)
    return validate_engine_result(prepared, result)
