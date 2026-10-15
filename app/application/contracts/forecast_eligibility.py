"""Detached D2 assessment; not a retained or public serialization format."""
from dataclasses import dataclass
from typing import Literal

from app.application.contracts.forecast_execution import ForecastWarning
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.readiness import Issue


@dataclass(frozen=True)
class ForecastEligibility:
    requested_mode: Literal['BASELINE', 'TRAINED']
    candidate_artifact_identity: str | None
    actual_model_type: str | None
    actual_model_version: str | None
    artifact_identity: str | None
    execution: ExecutionDetails | None
    warnings: tuple[ForecastWarning, ...]
    blockers: tuple[Issue, ...]
    failure_kind: Literal['HISTORY_UNUSABLE', 'ARTIFACT_INVALID', 'DEPENDENCY_UNAVAILABLE', 'RUNTIME_UNAVAILABLE'] | None

    @property
    def can_execute(self) -> bool:
        return not self.blockers
