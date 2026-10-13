"""Internal planning_storage/1 aggregate; not an HTTP/auth contract."""
from typing import Literal
from dataclasses import dataclass
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator, field_validator,model_serializer
from app.application.contracts.planning_public_evidence import PublicPlanningAcceptance,PublicPlanningCapture,PublicPlanningAudit,PublicPlanningExecution
from app.application.contracts.common import Contract, Nonblank
from app.application.contracts.planning_setup import PlanningRequest, ResolvedPlanningSetup
from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2, OperationalPipelineResultV2
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations, prepare_planning_pipeline
from app.application.planning_serialization import canonical_bytes, request_digest, digest


class ProcessIdentity(Contract):
    host: Nonblank
    pid: int = Field(gt=0, strict=True)
    birth: Nonblank


class PlanningClaim(Contract):
    token: UUID
    generation: int = Field(gt=0, strict=True)
    process: ProcessIdentity


_OUTCOMES = {
        'RECOMMENDATION_AVAILABLE': ('completed', 'recommendation_available'),
        'NO_ELIGIBLE_CANDIDATE': ('completed', 'no_eligible_candidate'),
        'NO_COMPUTABLE_PRODUCTS': ('completed', 'no_computable_products'),
        'CAPTURE_BLOCKED': ('completed', 'computation_blocked'),
        'COMPUTATION_BLOCKED': ('completed', 'computation_blocked'),
        'NUMERIC_UNSUPPORTED': ('completed', 'computation_blocked'),
        'EXECUTION_ERROR': ('failed', 'execution_error'),
}


def outcome_mapping(result: OperationalPipelineResultV2):
    result = OperationalPipelineResultV2.model_validate(result)
    return _OUTCOMES[result.outcome]


class PlanningRunRecord(Contract):
    storage_version: Literal['planning_storage/1'] = 'planning_storage/1'
    package_schema_version: Literal[1] = 1
    run_id: UUID
    actor_id: UUID
    store_id: UUID
    operation: Literal['C02'] = 'C02'
    key_digest: Nonblank
    request_digest: Nonblank
    request: PlanningRequest
    resolution: ResolvedPlanningSetup
    accepted_at: AwareDatetime
    status: Literal['queued', 'running', 'completed', 'failed']
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    claim: PlanningClaim | None = None
    declarations: PlanningPipelineDeclarations | None = None
    capture: DecisionCaptureOutcomeV2 | None = None
    input_digest: Nonblank | None = None
    result: OperationalPipelineResultV2 | None = None
    result_digest: Nonblank | None = None
    outcome: Literal['recommendation_available','no_eligible_candidate','no_computable_products',
                     'computation_blocked','execution_error'] | None = None
    error_code: Nonblank | None = None
    # Fixed sanitized summary; detailed primary errors remain chained, not persisted.
    error_summary: Nonblank | None = None
    public_acceptance: PublicPlanningAcceptance | None=None
    public_capture: PublicPlanningCapture | None=None
    public_audit: tuple[PublicPlanningAudit,...] | None=None
    public_execution: PublicPlanningExecution | None=None

    @model_serializer(mode='wrap')
    def preserve_internal_storage(self,handler):
        result=handler(self)
        for key in ('public_acceptance','public_capture','public_audit','public_execution'):
            if result.get(key) is None:result.pop(key,None)
        return result

    @field_validator('package_schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:
            raise ValueError('Package version must be integer1')
        return value

    @model_validator(mode='after')
    def reconcile(self):
        if self.public_acceptance is not None:
            if not self.public_audit or self.public_audit[0].action!='ACCEPTED' or self.public_audit[0].occurred_at!=self.accepted_at or any(e.actor_id!=self.actor_id for e in self.public_audit):
                raise ValueError('Public acceptance audit incomplete')
            actions=tuple(e.action for e in self.public_audit)
            expected=('ACCEPTED',)
            if self.status!='queued':expected+=('CLAIMED',)
            if self.capture is not None:expected+=('CAPTURE_RETAINED',)
            if self.status=='completed':expected+=('COMPLETED',)
            if self.status=='failed':expected+=('RECOVERED' if self.error_code=='PROCESS_INTERRUPTED' and actions[-1]=='RECOVERED' else 'FAILED',)
            if actions!=expected or any(b.occurred_at<a.occurred_at for a,b in zip(self.public_audit,self.public_audit[1:])):
                raise ValueError('Public lifecycle audit differs from retained state')
        elif self.public_capture is not None or self.public_audit is not None or self.public_execution is not None:
            raise ValueError('Public evidence needs public acceptance')
        if self.public_execution is not None and self.status not in ('completed','failed'):
            raise ValueError('Terminal execution metrics cannot be published early')
        if self.public_capture is not None:
            if self.capture is None:raise ValueError('Public capture needs retained operational capture')
            if self.public_capture.forecast is not None and (self.declarations is None or self.public_capture.forecast.forecast_run_id!=self.declarations.forecast_run_id):
                raise ValueError('Public forecast/operational capture identity mismatch')
            public=self.public_capture
            if public.ingredient_labels is not None:
                expected_ids={i.ingredient_id for i in self.capture.prepared.ingredients} if self.capture.prepared else set()
                if {i.ingredient_id for i in public.ingredient_labels}!=expected_ids:
                    raise ValueError('Captured ingredient label scope differs from computed scope')
            sources=public.operational_evidence
            if sources is not None:
                offers={o.term_id:o for o in self.declarations.offers}
                terms={t.id:t for t in self.capture.source.facts.supplier_terms} if self.capture.source else {}
                evidence={e.term_id:e for e in sources.terms}
                if len({b.term_id for b in sources.bounds})!=len(sources.bounds) or {b.term_id for b in sources.bounds}!=set(offers):
                    raise ValueError('Retained offer bound coverage differs from declarations')
                for bound in sources.bounds:
                    term=terms.get(bound.term_id)
                    source=evidence.get(bound.term_id)
                    declared=next((l.maximum_quantity for l in self.declarations.supplier_limits if term and (l.supplier_id,l.ingredient_id)==(term.supplier_id,term.ingredient_id)),None)
                    if term is None or (bound.effective_budget,bound.budget_version,bound.pack_cost,bound.pack_size,bound.maximum_packs,bound.declared_limit_quantity)!=(self.resolution.budget.amount,self.resolution.budget_version,term.pack_cost,term.pack_size_base_quantity,offers[bound.term_id].bound.maximum_packs,declared):
                        raise ValueError('Retained finite bound differs from accepted budget/captured term/limit')
                    expected_max=source.payload.maximum_order_base_quantity if source else None
                    from decimal import Decimal
                    if bound.source_maximum_quantity!=(Decimal(expected_max) if expected_max is not None else None):raise ValueError('Source maximum evidence differs from source term')
            fact=self.capture.source.facts.forecast if self.capture.source else None
            if public.forecast is None:
                if public.identity is not None or fact is not None or self.declarations.forecast_run_id is not None:
                    raise ValueError('Absent public forecast contains fabricated identity')
            else:
                identity=public.identity
                if identity is None or fact is None or identity.serving_version!=self.public_acceptance.serving.version:
                    raise ValueError('Forecast identity not bound to accepted serving/source')
                wire=public.forecast
                if (wire.model_type,wire.model_version,wire.artifact_identity,wire.input_digest)!=(fact.model_type,fact.model_version,fact.artifact_key,fact.retained_digest) or (identity.model_type,identity.model_version,identity.artifact_identity,identity.prepared_digest)!=(fact.model_type,fact.model_version,fact.artifact_key,fact.retained_digest):
                    raise ValueError('Public forecast metadata differs from verified source')
                if fact.retained is None or (wire.start_date,wire.end_date,wire.history_start_date,wire.history_end_date,wire.training_start_date,wire.training_end_date)!=(fact.forecast_start_date,fact.forecast_end_date,fact.retained.request.history_start_date,fact.retained.request.cutoff_date,identity.training_start_date,identity.training_end_date):
                    raise ValueError('Public forecast windows differ from retained provenance')
                if wire.quality_status!='not_evaluated':raise ValueError('No retained evaluation provenance is available')
        if self.store_id != self.resolution.configuration.store_id:
            raise ValueError('Resolution Store mismatch')
        if request_digest(self.request) != self.request_digest or request_digest(self.resolution.request) != self.request_digest:
            raise ValueError('Original request/resolution mismatch')
        if self.started_at is not None and self.started_at < self.accepted_at:
            raise ValueError('Start predates acceptance')
        if self.finished_at is not None and self.finished_at < (self.started_at or self.accepted_at):
            raise ValueError('Finish predates start')
        if (self.capture is None) != (self.declarations is None):
            raise ValueError('Capture/declarations incomplete')
        if self.input_digest != (digest('capture',self.capture) if self.capture is not None else None):
            raise ValueError('Retained input digest mismatch')
        if self.result_digest != (digest('result',self.result) if self.result is not None else None):
            raise ValueError('Retained result digest mismatch')
        if self.capture is not None:
            expected = prepare_planning_pipeline(self.resolution, self.declarations)
            if canonical_bytes(expected) != canonical_bytes(self.capture.request):
                raise ValueError('Capture differs from accepted configuration')
        if self.status == 'queued':
            if any(v is not None for v in (self.started_at,self.finished_at,self.claim,self.capture,self.result,self.outcome,self.error_code,self.error_summary)):
                raise ValueError('Queued aggregate contains execution facts')
        elif self.status == 'running':
            if self.started_at is None or self.claim is None or any(v is not None for v in (self.finished_at,self.result,self.outcome,self.error_code,self.error_summary)):
                raise ValueError('Invalid running aggregate')
        else:
            if self.started_at is None or self.claim is None or self.finished_at is None or self.outcome is None:
                raise ValueError('Terminal execution identity incomplete')
            if self.status == 'completed' and (self.result is None or self.error_code is not None or self.error_summary is not None):
                raise ValueError('Completed requires verified pipeline result, no error')
            if self.status == 'failed' and (self.outcome != 'execution_error' or self.error_code is None or self.error_summary is None):
                raise ValueError('Failed requires technical error')
        if self.result is not None:
            if self.capture is None or canonical_bytes(self.result.capture) != canonical_bytes(self.capture):
                raise ValueError('Result input identity mismatch')
            # Nested result has already been semantically revalidated by Pydantic;
            # avoid rebuilding the same expensive exact graph a second time.
            if _OUTCOMES[self.result.outcome] != (self.status, self.outcome):
                raise ValueError('Pipeline/lifecycle outcome mismatch')
        return self


@dataclass(frozen=True)
class PlanningRead:
    """By-value read receipt around the already verified immutable record."""
    record: PlanningRunRecord
    integrity_validation_seconds: float


class PlanningPersistenceError(Exception):
    def __init__(self, code: str, run_id: UUID | None = None, state: str = 'unknown'):
        self.code, self.run_id, self.state = code, run_id, state
        super().__init__(f'{code}; run_id={run_id}; state={state}')
