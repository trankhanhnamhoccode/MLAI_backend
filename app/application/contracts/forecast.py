from datetime import date
from uuid import UUID
from pydantic import AwareDatetime, StringConstraints, model_validator
from typing import Annotated
from app.application.contracts.common import Contract, JsonObject, Metadata, Nonblank, NonnegativeDecimal, RunReferenceInput, RunStatus


class StartForecastRunInput(Contract):
    store_id: UUID
    training_start_date: date
    training_end_date: date
    forecast_start_date: date
    forecast_end_date: date
    model_type: Metadata
    model_version: Metadata
    started_at: AwareDatetime
    artifact_key: Nonblank | None = None

    @model_validator(mode='after')
    def ordered_windows(self) -> 'StartForecastRunInput':
        if self.training_start_date > self.training_end_date or self.forecast_start_date > self.forecast_end_date:
            raise ValueError('Training and forecast windows must be ordered')
        return self


class PredictionInput(Contract):
    product_id: UUID
    forecast_date: date
    p25: NonnegativeDecimal
    p50: NonnegativeDecimal
    p75: NonnegativeDecimal

    @model_validator(mode='after')
    def ordered_quantiles(self) -> 'PredictionInput':
        if not self.p25 <= self.p50 <= self.p75:
            raise ValueError('Quantiles must satisfy 0 <= p25 <= p50 <= p75')
        return self


class PredictionResult(PredictionInput):
    id: UUID
    store_id: UUID
    forecast_run_id: UUID


class CompleteForecastRunInput(RunReferenceInput):
    completed_at: AwareDatetime
    input_fingerprint: Metadata
    predictions: tuple[PredictionInput, ...]
    metrics_json: JsonObject | None = None

    @model_validator(mode='after')
    def distinct_predictions(self) -> 'CompleteForecastRunInput':
        keys = [(p.product_id, p.forecast_date) for p in self.predictions]
        if len(keys) != len(set(keys)):
            raise ValueError('Predictions must have distinct Product/date identities')
        return self


class FailRunInput(RunReferenceInput):
    """Caller-sanitized business failure, never an exception/stack dump."""
    completed_at: AwareDatetime
    error_code: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'\S')]
    error_summary: Nonblank


class ForecastRunResult(StartForecastRunInput):
    id: UUID
    status: RunStatus
    completed_at: AwareDatetime | None
    input_fingerprint: Metadata | None
    metrics_json: JsonObject | None
    error_code: str | None
    error_summary: str | None
    predictions: tuple[PredictionResult, ...]
