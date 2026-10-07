from datetime import date
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from typing import Annotated
from app.application.contracts.common import Contract, JsonObject, Metadata, RunReferenceInput, RunStatus, Strategy


class StartDecisionRunInput(Contract):
    store_id: UUID
    forecast_run_id: UUID
    planning_start_date: date
    planning_end_date: date
    started_at: AwareDatetime

    @model_validator(mode='after')
    def ordered_window(self) -> 'StartDecisionRunInput':
        if self.planning_start_date > self.planning_end_date:
            raise ValueError('Planning window must be ordered')
        return self


class CompleteDecisionRunInput(RunReferenceInput):
    completed_at: AwareDatetime
    input_fingerprint: Metadata
    package_schema_version: Annotated[int, Field(gt=0, strict=True)]
    input_snapshot_json: JsonObject
    decision_package_json: JsonObject
    recommended_strategy: Strategy


class DecisionRunResult(StartDecisionRunInput):
    id: UUID
    status: RunStatus
    completed_at: AwareDatetime | None
    input_fingerprint: Metadata | None
    package_schema_version: int | None
    input_snapshot_json: JsonObject | None
    decision_package_json: JsonObject | None
    recommended_strategy: Strategy | None
    error_code: str | None
    error_summary: str | None
