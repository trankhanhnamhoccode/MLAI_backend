"""S2 execution boundary, separate from S1 supplied-prediction persistence."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BeforeValidator, StringConstraints, model_validator

from app.application.contracts.common import (
    Contract, Metadata, Nonblank, NonnegativeDecimal, Unit,
)
from app.domain.forecasting.validation import (
    validate_output_coverage, validate_prepared_input, validate_quantiles, validate_request,
)


class ForecastExecutionInput(Contract):
    store_id: UUID
    product_ids: tuple[UUID, ...]
    cutoff_date: date
    history_start_date: date

    @model_validator(mode='after')
    def valid_request(self) -> 'ForecastExecutionInput':
        validate_request(self.product_ids, self.history_start_date, self.cutoff_date)
        object.__setattr__(self, 'product_ids', tuple(sorted(self.product_ids)))
        return self


class CapturedForecastProduct(Contract):
    product_id: UUID
    selling_unit: Unit


class ObservedSalesRecord(Contract):
    store_id: UUID
    product_id: UUID
    sales_date: date
    quantity: NonnegativeDecimal
    selling_unit: Unit


def _schema_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError('Schema version must be integer 1')
    return value


class PreparedForecastInput(Contract):
    """By-value capture. Empty/sparse observations do not establish model readiness."""

    schema_version: Annotated[Literal[1], BeforeValidator(_schema_version)] = 1
    request: ForecastExecutionInput
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    products: tuple[CapturedForecastProduct, ...]
    observations: tuple[ObservedSalesRecord, ...]
    forecast_dates: tuple[date, ...]

    @model_validator(mode='after')
    def valid_capture(self) -> 'PreparedForecastInput':
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('Store timezone must be a resolvable IANA timezone') from error
        request = self.request
        validate_prepared_input(
            request.store_id, request.product_ids, request.history_start_date, request.cutoff_date,
            tuple((p.product_id, p.selling_unit) for p in self.products),
            tuple((r.store_id, r.product_id, r.sales_date, r.quantity, r.selling_unit)
                  for r in self.observations), self.forecast_dates,
        )
        object.__setattr__(self, 'products', tuple(sorted(self.products, key=lambda p: p.product_id)))
        object.__setattr__(self, 'observations', tuple(sorted(
            self.observations, key=lambda r: (r.sales_date, r.product_id))))
        object.__setattr__(self, 'forecast_dates', tuple(sorted(self.forecast_dates)))
        return self


class ForecastExecutionPrediction(Contract):
    product_id: UUID
    forecast_date: date
    p25: NonnegativeDecimal
    p50: NonnegativeDecimal
    p75: NonnegativeDecimal

    @model_validator(mode='after')
    def valid_quantiles(self) -> 'ForecastExecutionPrediction':
        validate_quantiles(self.p25, self.p50, self.p75)
        return self


class ForecastWarning(Contract):
    code: Metadata
    severity: Literal['INFO', 'WARNING', 'ERROR']
    field: Nonblank
    entity: Nonblank
    impact: Nonblank
    product_id: UUID | None = None


class ForecastEngineResult(Contract):
    """Raw typed engine return; call validate_engine_result before future persistence."""

    model_type: Metadata
    model_version: Metadata
    artifact_identity: Nonblank | None = None
    predictions: tuple[ForecastExecutionPrediction, ...]
    warnings: tuple[ForecastWarning, ...] = ()

    @model_validator(mode='after')
    def canonical_order(self) -> 'ForecastEngineResult':
        object.__setattr__(self, 'predictions', tuple(sorted(
            self.predictions, key=lambda p: (p.forecast_date, p.product_id))))
        object.__setattr__(self, 'warnings', tuple(sorted(self.warnings, key=lambda w: (
            w.code, w.severity, w.field, w.entity, w.impact,
            '' if w.product_id is None else str(w.product_id)))))
        return self


def validate_engine_result(prepared: PreparedForecastInput,
                           result: ForecastEngineResult) -> ForecastEngineResult:
    """Pure boundary validation, not execution/readiness/orchestration/persistence."""
    prepared = PreparedForecastInput.model_validate(prepared)
    result = ForecastEngineResult.model_validate(result)
    validate_output_coverage(prepared.request.product_ids, prepared.request.cutoff_date,
                             tuple((p.product_id, p.forecast_date) for p in result.predictions))
    return result
