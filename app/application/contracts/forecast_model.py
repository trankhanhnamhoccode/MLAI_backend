"""S2 trained model/evaluation boundaries; immutable nested values, no opaque metrics."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, model_validator

from app.application.contracts.common import Contract, NonnegativeDecimal
from app.application.contracts.forecast_execution import PreparedForecastInput, ForecastWarning
from app.application.contracts.forecast import ForecastRunResult
from app.domain.forecasting.features import FEATURE_NAMES

Count = Annotated[int, Field(strict=True, ge=0)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
MODEL_TYPE = 'lightgbm_quantile'
MODEL_VERSION = '1'


def _integer_version(value):
    if type(value) is not int:
        raise ValueError('Version must be integer 1')
    return value


Version = Annotated[Literal[1], BeforeValidator(_integer_version)]


class ModelReadiness(Contract):
    product_id: UUID
    observation_count: Count
    supervised_count: Count = 0
    status: Literal['READY', 'NOT_READY_HISTORY', 'NOT_READY_TRAINING_ROWS']


class MetricSummary(Contract):
    family: Literal['lightgbm_quantile', 'historical_quantile_baseline']
    partition: Literal['validation', 'holdout']
    product_id: UUID | None = None
    horizon: Annotated[int, Field(strict=True, ge=1, le=7)] | None = None
    sample_count: Count
    mae_p50: NonnegativeDecimal | None
    wape: NonnegativeDecimal | None
    pinball_p25: NonnegativeDecimal | None
    pinball_p50: NonnegativeDecimal | None
    pinball_p75: NonnegativeDecimal | None
    mean_pinball: NonnegativeDecimal | None
    coverage: NonnegativeDecimal | None
    nominal_coverage: Literal['0.50'] = '0.50'
    mean_interval_width: NonnegativeDecimal | None
    raw_crossings: Count
    post_crossings: Count


class ExcludedOriginProduct(Contract):
    origin: date
    product_id: UUID
    reason: Literal['NOT_READY_HISTORY', 'NOT_READY_TRAINING_ROWS', 'SCOPE_NOT_READY']


class EvaluationReport(Contract):
    schema_version: Version = 1
    policy_version: Version = 1
    dataset_label: Literal['SYNTHETIC', 'USER_PROVIDED_UNVERIFIED']
    real_data_quality: Literal['NOT EVALUATED'] = 'NOT EVALUATED'
    input_fingerprint: Digest
    validation_origins: tuple[date, ...]
    holdout_origins: tuple[date, ...]
    missing_targets: Count
    excluded: tuple[ExcludedOriginProduct, ...]
    metrics: tuple[MetricSummary, ...]
    selected_family: Literal['lightgbm_quantile', 'historical_quantile_baseline']
    selection_reason: Literal['VALIDATION_IMPROVEMENT', 'BASELINE_TIE_OR_BETTER', 'INSUFFICIENT_VALIDATION']

    @model_validator(mode='after')
    def chronological(self) -> 'EvaluationReport':
        origins = self.validation_origins + self.holdout_origins
        if tuple(sorted(set(origins))) != origins:
            raise ValueError('Evaluation origins must be unique and chronological')
        if (self.selected_family == MODEL_TYPE) != (self.selection_reason == 'VALIDATION_IMPROVEMENT'):
            raise ValueError('Selection family/reason mismatch')
        return self


class ModelFile(Contract):
    name: Literal['p25.txt', 'p50.txt', 'p75.txt']
    digest: Digest


class ArtifactManifest(Contract):
    schema_version: Version = 1
    feature_version: Version = 1
    policy_version: Version = 1
    postprocessing_version: Version = 1
    model_type: Literal['lightgbm_quantile'] = MODEL_TYPE
    model_version: Literal['1'] = MODEL_VERSION
    feature_names: tuple[str, ...] = FEATURE_NAMES
    lightgbm_version: Literal['4.6.0'] = '4.6.0'
    numpy_version: Literal['2.2.6'] = '2.2.6'
    scipy_version: Literal['1.17.1'] = '1.17.1'
    seed: Literal[1729] = 1729
    rounds: Literal[40] = 40
    num_leaves: Literal[7] = 7
    min_data_in_leaf: Literal[5] = 5
    learning_rate: Literal['0.05'] = '0.05'
    training_input: PreparedForecastInput
    training_fingerprint: Digest
    evaluation: EvaluationReport
    files: tuple[ModelFile, ...]

    @model_validator(mode='after')
    def fixed_schema(self) -> 'ArtifactManifest':
        if self.feature_names != FEATURE_NAMES or tuple(f.name for f in self.files) != ('p25.txt', 'p50.txt', 'p75.txt'):
            raise ValueError('Unsupported feature/model file schema')
        if self.evaluation.input_fingerprint != self.training_fingerprint:
            raise ValueError('Evaluation/training input identity mismatch')
        return self


class ExecutionDetails(Contract):
    schema_version: Version = 1
    selection_reason: Literal['TRAINED_SELECTED', 'NO_ARTIFACT', 'ARTIFACT_MISSING',
                              'NOT_READY_HISTORY', 'BASELINE_SELECTED', 'LEGACY_BASELINE']
    candidate_artifact_identity: Digest | None = None
    postprocessing_version: Version = 1
    raw_crossings: Count = 0
    negative_values: Count = 0
    warnings: tuple[ForecastWarning, ...] = ()


class ModelForecastRunResult(Contract):
    run: ForecastRunResult
    execution: ExecutionDetails
