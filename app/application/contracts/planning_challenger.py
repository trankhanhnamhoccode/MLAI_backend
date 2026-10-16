"""F4 private test-only acceptance pin; no request DTO or production eligibility."""
from typing import Literal
from pydantic import model_validator
from app.application.contracts.common import Contract
from app.application.contracts.forecast_challenger import ChallengerInput, ChallengerArtifact, RuntimeIdentity,Digest
from app.application.contracts.forecast_execution import PreparedForecastInput


def canonical_matches(prepared: PreparedForecastInput,value: ChallengerInput) -> bool:
    return (prepared.schema_version==3 and prepared.request==value.request and prepared.timezone==value.timezone
        and prepared.products==value.products and prepared.forecast_dates==value.forecast_dates
        and tuple(o.model_dump(exclude={'available_at','source'}) for o in value.observations)
            ==tuple(o.model_dump() for o in prepared.observations))


class ChallengerTestPin(Contract):
    schema_version: Literal['planning_challenger_test/1']='planning_challenger_test/1'
    variant: Literal['C0_TEST_ONLY']='C0_TEST_ONLY'
    closure_policy: Literal['native_explicit_calendar_once/1']='native_explicit_calendar_once/1'
    eligibility: Literal['synthetic_test_only']='synthetic_test_only'
    input: ChallengerInput
    artifact: ChallengerArtifact
    runtime: RuntimeIdentity
    integration_code_digest: Digest

    @model_validator(mode='after')
    def test_only(self):
        if (self.input.mode!='challenger' or self.artifact.purpose!='synthetic_correctness'
                or self.artifact.holdout_status!='SYNTHETIC_ONLY'
                or self.artifact.promotion_status!='trained_candidate'
                or self.artifact.production_available_at is not None or self.runtime!=self.artifact.runtime):
            raise ValueError('F4 accepts only unpromoted synthetic correctness artifacts')
        from app.application.forecast_challenger_serialization import challenger_digest
        from app.application.forecast_challenger_validation import admit_input,admit_artifact
        if challenger_digest('artifact',self.artifact)!=self.input.artifact_identity:
            raise ValueError('Artifact/input pin differs')
        admit_input(self.input);admit_artifact(self.input,self.artifact)
        return self
