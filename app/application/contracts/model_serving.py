"""Explicit serving policy and identity, separate from forecasting algorithms."""
from typing import Literal
from datetime import date
from pydantic import Field,model_validator
from app.application.contracts.auth import DTO
from app.application.contracts.planning_setup import ResourceId,Version


class ServingPolicy(DTO):
    mode: Literal['BASELINE','TRAINED']
    artifact_identity: str | None
    fallback_policy: Literal['ADR015_RECOGNIZED_ONLY']
    features_version: Literal[1]=1
    postprocessing_version: Literal[1]=1
    dependency_versions: tuple[tuple[str,str],...]

    @model_validator(mode='after')
    def coherent(self):
        if self.mode=='BASELINE' and self.artifact_identity is not None:
            raise ValueError('Baseline has no artifact')
        if len({k for k,v in self.dependency_versions})!=len(self.dependency_versions):
            raise ValueError('Duplicate dependency version')
        return self


class ServingRecord(DTO):
    version: Version
    policy: ServingPolicy


class OperatorConfigurationCommand(DTO):
    store_id: ResourceId
    action: Literal['BASELINE','DEFAULT_BASE95']
    expected_version: Version | None
    evidence_reference: str=Field(min_length=1,max_length=1000)


class ForecastIdentity(DTO):
    prepared_digest: str
    source_digest: str
    serving_version: Version
    model_type: str
    model_version: str
    artifact_identity: str | None
    candidate_artifact_identity: str | None
    selection_reason: str
    features_version: Literal[1]
    postprocessing_version: Literal[1]
    dependency_versions: tuple[tuple[str,str],...]
    configuration_dependency_versions: tuple[tuple[str,str],...]
    training_start_date: date
    training_end_date: date
