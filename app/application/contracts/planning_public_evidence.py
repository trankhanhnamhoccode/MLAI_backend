"""Private typed integration evidence retained within the existing Run aggregate."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator,model_serializer
from app.application.contracts.planning_source_evidence import PlanningSourceEvidence
from app.application.contracts.common import Contract
from app.application.contracts.model_serving import ServingRecord,ForecastIdentity
from app.application.contracts.planning_public import PlanningNotification,ForecastView
from app.application.contracts.readiness import SourceVersions


class PublicPlanningAcceptance(Contract):
    schema_version: Literal['planning_public_acceptance/1']='planning_public_acceptance/1'
    session_digest: str=Field(pattern=r'^[0-9a-f]{64}$')
    authorization_version: str
    serving: ServingRecord
    receipt_warnings: tuple[PlanningNotification,...]
    overall_stage_seconds: Literal[180]=180
    offer_eligibility_policy: Literal['offer_eligibility/1'] | None=None

    @model_serializer(mode='wrap')
    def preserve_legacy(self,handler):
        result=handler(self)
        if result.get('offer_eligibility_policy') is None:result.pop('offer_eligibility_policy',None)
        return result


class IngredientLabel(Contract):
    ingredient_id: UUID
    name: str=Field(min_length=1,max_length=200)
    sku: str | None=Field(default=None,max_length=64)


class PublicPlanningCapture(Contract):
    schema_version: Literal['planning_public_capture/1']='planning_public_capture/1'
    forecast: ForecastView | None
    identity: ForecastIdentity | None
    source_versions: SourceVersions
    preparation_seconds: float=Field(ge=0,allow_inf_nan=False)
    operational_evidence: PlanningSourceEvidence | None=None
    ingredient_labels: tuple[IngredientLabel,...] | None=None

    @model_validator(mode='after')
    def distinct_labels(self):
        if self.ingredient_labels is not None and len({i.ingredient_id for i in self.ingredient_labels})!=len(self.ingredient_labels):
            raise ValueError('Duplicate captured ingredient label')
        return self

    @model_serializer(mode='wrap')
    def preserve_prior(self,handler):
        result=handler(self)
        if result.get('operational_evidence') is None:result.pop('operational_evidence',None)
        if result.get('ingredient_labels') is None:result.pop('ingredient_labels',None)
        return result


class PublicPlanningAudit(Contract):
    action: Literal['ACCEPTED','CLAIMED','CAPTURE_RETAINED','COMPLETED','FAILED','RECOVERED']
    actor_id: UUID
    occurred_at: AwareDatetime
    outcome: str | None=None


class PublicPlanningExecution(Contract):
    elapsed_seconds: float=Field(ge=0,allow_inf_nan=False)
    stage_budget_seconds: Literal[180]=180
    stage_overrun_seconds: float=Field(ge=0,allow_inf_nan=False)
    engine_seconds: float | None=Field(default=None,ge=0,allow_inf_nan=False)
    engine_overrun_seconds: float | None=Field(default=None,ge=0,allow_inf_nan=False)

    @model_validator(mode='after')
    def overrun(self):
        if self.stage_overrun_seconds!=max(0,self.elapsed_seconds-self.stage_budget_seconds):
            raise ValueError('Stage overrun must preserve measured elapsed')
        return self
