"""Opt-in internal detached challenger values; no DB/public serving contract change."""
from datetime import date
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from app.application.contracts.common import Contract, FiniteDecimal, Nonblank, NonnegativeDecimal
from app.application.contracts.forecast_execution import (
    CapturedForecastProduct, ForecastEngineResult, ForecastExecutionInput, ObservedSalesRecord,
)

ENGINE_COMMIT = '62b94fa4d67cb04141d32be4e57d6f9740c2a8fc'
ENGINE_SOURCE_DIGEST = '99ef7c2631f3bb349c303b311718fb0bd81471469715928fb99c9e28de28aca4'
ENGINE_DISTRIBUTION = 'shelfcash-forecast-challenger-snapshot'
ENGINE_VERSION = '0.1.0+62b94fa.e2'
ARM = 'C_engine_native_reconstruction_v1'
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Version = Annotated[int, Field(strict=True, ge=1, le=1)]
Count = Annotated[int, Field(strict=True, ge=0)]


class ChallengerFailure(str, Enum):
    UNSUPPORTED = 'UNSUPPORTED'
    DATA_BLOCKED = 'DATA_BLOCKED'
    ARTIFACT_CORRUPTION = 'ARTIFACT_CORRUPTION'
    DEPENDENCY_MISMATCH = 'DEPENDENCY_MISMATCH'
    TECHNICAL_FAILURE = 'TECHNICAL_FAILURE'


class ChallengerError(ValueError):
    """Safe code/category only; do not expose provider/native exception text."""
    def __init__(self, category: ChallengerFailure, code: str):
        self.category, self.code = category, code
        super().__init__(code)


class CanonicalObservation(ObservedSalesRecord):
    available_at: AwareDatetime
    source: Nonblank


class CalendarFact(Contract):
    store_id: UUID
    day: date
    closed: StrictBool
    holiday: StrictBool
    available_at: AwareDatetime
    source: Nonblank


class ChallengerInput(Contract):
    schema_version: Version = 1
    adapter_version: Literal['forecast_challenger/1'] = 'forecast_challenger/1'
    arm: Literal['C_engine_native_reconstruction_v1'] = ARM
    reconstruction_policy: Literal['engine_native_reconstruction_v1'] = 'engine_native_reconstruction_v1'
    quantity_basis: Literal['canonical_observed_sales'] = 'canonical_observed_sales'
    weather_policy: Literal['exclude_all_weather_features'] = 'exclude_all_weather_features'
    mode: Literal['challenger', 'production'] = 'challenger'
    request: ForecastExecutionInput
    timezone: Nonblank
    inference_at: AwareDatetime
    products: tuple[CapturedForecastProduct, ...]
    observations: tuple[CanonicalObservation, ...]
    forecast_dates: tuple[date, ...]
    calendar: tuple[CalendarFact, ...]
    artifact_identity: Digest

    @model_validator(mode='after')
    def ordering(self):
        object.__setattr__(self, 'products', tuple(sorted(self.products, key=lambda p: p.product_id)))
        object.__setattr__(self, 'observations', tuple(sorted(self.observations,
            key=lambda r: (r.sales_date, r.product_id))))
        object.__setattr__(self, 'calendar', tuple(sorted(self.calendar, key=lambda r: r.day)))
        object.__setattr__(self, 'forecast_dates', tuple(sorted(self.forecast_dates)))
        return self


class DependencyPin(Contract):
    name: Nonblank
    version: Nonblank


class RuntimeIdentity(Contract):
    engine_commit: Literal['62b94fa4d67cb04141d32be4e57d6f9740c2a8fc'] = ENGINE_COMMIT
    engine_source_digest: Digest = ENGINE_SOURCE_DIGEST
    adapter_code_digest: Digest
    python: Nonblank
    platform: Nonblank
    machine: Nonblank
    dependencies: tuple[DependencyPin, ...]


class ArtifactFile(Contract):
    name: Nonblank
    digest: Digest


class FitWindow(Contract):
    start: date
    end: date
    labels_available_at: AwareDatetime

    @model_validator(mode='after')
    def valid_window(self):
        if self.start > self.end:
            raise ValueError('Invalid fit window')
        return self


class ChallengerArtifact(Contract):
    schema_version: Version = 1
    model_type: Literal['forecast_engine_challenger'] = 'forecast_engine_challenger'
    model_version: Nonblank
    purpose: Literal['synthetic_correctness', 'research_candidate', 'production']
    holdout_status: Literal['SYNTHETIC_ONLY', 'EXPOSED', 'UNSEEN']
    promotion_status: Literal['trained_candidate', 'promoted']
    production_available_at: AwareDatetime | None
    store_id: UUID
    products: tuple[CapturedForecastProduct, ...]
    timezone: Nonblank
    arm: Literal['C_engine_native_reconstruction_v1'] = ARM
    reconstruction_policy: Literal['engine_native_reconstruction_v1'] = 'engine_native_reconstruction_v1'
    runtime: RuntimeIdentity
    training: FitWindow
    point_fit: FitWindow
    calibration: FitWindow
    fitted_at: AwareDatetime
    published_at: AwareDatetime
    available_at: AwareDatetime
    publication_basis: Literal['local_snapshot_admission', 'original_publication']
    config_digest: Digest
    feature_digest: Digest
    postprocess_digest: Digest
    files: tuple[ArtifactFile, ...]

    @model_validator(mode='after')
    def ordering(self):
        object.__setattr__(self, 'products', tuple(sorted(self.products, key=lambda p: p.product_id)))
        object.__setattr__(self, 'files', tuple(sorted(self.files, key=lambda f: f.name)))
        return self


class CQRInterval(Contract):
    product_id: UUID
    forecast_date: date
    lower: NonnegativeDecimal
    upper: NonnegativeDecimal
    correction: FiniteDecimal
    source: Nonblank
    nominal_coverage: NonnegativeDecimal
    semantics: Literal['cqr-order-statistic-v2'] = 'cqr-order-statistic-v2'
    calibrator_digest: Digest
    point_corrector_digest: Digest


class NativePredictionEvidence(Contract):
    product_id: UUID
    forecast_date: date
    model_raw: tuple[FiniteDecimal, FiniteDecimal, FiniteDecimal]
    quantity_raw: tuple[NonnegativeDecimal, NonnegativeDecimal, NonnegativeDecimal]
    repaired: tuple[NonnegativeDecimal, NonnegativeDecimal, NonnegativeDecimal]
    point_offset: FiniteDecimal
    raw_crossing: StrictBool
    target_strategy: Literal['absolute', 'seasonal_residual_signed']
    method: Literal['FIXED_LIGHTGBM_POINT_CQR'] = 'FIXED_LIGHTGBM_POINT_CQR'
    seasonal_anchor: NonnegativeDecimal
    anchor_reference_date: date | None
    anchor_fallback: StrictBool
    anchor_warning: str
    planned_closed: StrictBool
    warnings: tuple[str, ...]


class ReconstructionEvidence(Contract):
    product_id: UUID
    day: date
    row_observed: StrictBool
    observed_sales: NonnegativeDecimal | None
    stockout: StrictBool | None
    demand_proxy: NonnegativeDecimal | None
    feature_demand: NonnegativeDecimal | None
    applied: StrictBool
    method: Nonblank
    confidence: Nonblank
    reference_count: Count
    latest_reference: date | None
    reference_recency_days: Count | None
    relative_iqr: NonnegativeDecimal | None
    rejection_reasons: tuple[str, ...]
    train_eligible: StrictBool


class ChallengerOutput(Contract):
    schema_version: Version = 1
    float_policy: Literal['decimal_str_float/1'] = 'decimal_str_float/1'
    input_digest: Digest
    runtime: RuntimeIdentity
    artifact: ChallengerArtifact
    forecast: ForecastEngineResult
    cqr: tuple[CQRInterval, ...]
    native_predictions: tuple[NativePredictionEvidence, ...]
    reconstruction: tuple[ReconstructionEvidence, ...]
    warnings: tuple[str, ...]


class ChallengerEvidence(Contract):
    schema_version: Version = 1
    cache_identity: Digest
    input: ChallengerInput
    output: ChallengerOutput
