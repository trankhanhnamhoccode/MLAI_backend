"""Private E3 dataset/plan/result boundaries; no public API or operational writes."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from app.application.contracts.common import Contract, Nonblank, NonnegativeDecimal
from app.application.contracts.forecast_challenger import (
    CalendarFact, CanonicalObservation, Count, Digest, Version,
)
from app.application.contracts.forecast_execution import CapturedForecastProduct
from app.application.forecast_benchmark_plan import ResourceSeconds

ARMS = ('A_be_baseline_causal_v1', 'B_be_lightgbm_causal_v1', 'C_engine_native_reconstruction_v1')
PROTOCOL_DIGEST = '80bf93aa13a2a47b6ad84f37cb755c54c13b436e268c090e5106933623baa164'
DEMO_ABC_PROTOCOL_DIGEST = '6adf514b662b9c0169b00e1a12291285870f265b00d28b971fd488301b3d7259'


class BenchmarkDataset(Contract):
    schema_version: Version = 1
    classification: Literal['SYNTHETIC', 'REAL_EXPOSED', 'REAL_UNSEEN']
    use_authority: Nonblank
    source_revision: Nonblank
    availability_basis: Literal['synthetic_next_run', 'historical_vintages', 'retrospective_current_revision']
    limitations: tuple[Nonblank, ...]
    store_id: UUID
    timezone: Nonblank
    products: tuple[CapturedForecastProduct, ...]
    observations: tuple[CanonicalObservation, ...]
    calendar: tuple[CalendarFact, ...]

    @model_validator(mode='after')
    def ordering(self):
        object.__setattr__(self, 'products', tuple(sorted(self.products, key=lambda p: p.product_id)))
        object.__setattr__(self, 'observations', tuple(sorted(self.observations, key=lambda o: (o.sales_date, o.product_id))))
        object.__setattr__(self, 'calendar', tuple(sorted(self.calendar, key=lambda c: c.day)))
        return self


class BenchmarkOrigin(Contract):
    origin: date
    partition: Literal['validation', 'holdout']
    train_end: date
    point_start: date
    point_end: date
    calibration_start: date
    calibration_end: date


class BenchmarkBudget(Contract):
    maximum_origins: Annotated[int, Field(strict=True, ge=4, le=4)] = 4
    maximum_booster_fits: Annotated[int, Field(strict=True, ge=1, le=24)] = 24
    maximum_postprocess_fits: Annotated[int, Field(strict=True, ge=1, le=8)] = 8
    wall_seconds: ResourceSeconds = 300
    threads: Annotated[int, Field(strict=True, ge=1, le=1)] = 1


class BenchmarkPlan(Contract):
    schema_version: Version = 1
    harness_version: Literal['causal_benchmark/1', 'causal_benchmark/2', 'causal_benchmark/3'] = 'causal_benchmark/1'
    protocol_digest: Digest = PROTOCOL_DIGEST
    dataset_digest: Digest
    configuration_ids: tuple[str, ...] = ARMS
    holdout_fit_policy: Literal['quarantine_all_holdout_targets'] = 'quarantine_all_holdout_targets'
    automatic_promotion: Literal[False] = False
    tasks: tuple[BenchmarkOrigin, ...]
    budget: BenchmarkBudget = BenchmarkBudget()


class BenchmarkPrediction(Contract):
    arm: Literal['A_be_baseline_causal_v1', 'B_be_lightgbm_causal_v1', 'C_engine_native_reconstruction_v1']
    store_id: UUID
    product_id: UUID
    selling_unit: Nonblank
    origin: date
    partition: Literal['validation', 'holdout']
    target_date: date
    horizon: Annotated[int, Field(strict=True, ge=1, le=7)]
    actual: NonnegativeDecimal | None
    stockout: StrictBool | None
    mask: Literal['primary_known_false', 'supplementary_unknown', 'censored_lower_bound', 'missing']
    p25: NonnegativeDecimal
    p50: NonnegativeDecimal
    p75: NonnegativeDecimal
    cqr_lower: NonnegativeDecimal | None = None
    cqr_upper: NonnegativeDecimal | None = None
    raw_crossing: StrictBool = False
    negative_clamps: Count = 0

    @model_validator(mode='after')
    def ordering(self):
        if not self.p25 <= self.p50 <= self.p75:
            raise ValueError('Final quantile crossing')
        if self.cqr_lower is not None and not self.cqr_lower <= self.p50 <= self.cqr_upper:
            raise ValueError('Invalid CQR')
        return self


class ArmCheckpoint(Contract):
    schema_version: Version = 1
    arm: str
    origin: date
    identity: Digest
    status: Literal['COMPLETED', 'DATA_BLOCKED', 'TECHNICAL_FAILURE', 'BUDGET_EXCEEDED']
    reason: str | None
    predictions: tuple[BenchmarkPrediction, ...]
    artifact_identity: Digest | None = None
    input_digest: Digest
    training_seconds: NonnegativeDecimal
    inference_seconds: NonnegativeDecimal
    artifact_bytes: Count = 0
    replay_identity: Digest | None = None
