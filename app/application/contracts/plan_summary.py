"""Versioned public summary boundary; backend retains authority over every fact."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from app.application.contracts.auth import DTO
from app.application.contracts.planning_setup import Version
from app.application.contracts.planning_public import OptionId
from app.application.contracts.decision_evidence import EvidenceReference, EvidenceIdentity
from app.application.contracts.planning_run import ProcessIdentity

BlockKey = Literal['outcome','cost','requirements','coverage','proof','limitations']


class SummaryRequest(DTO):
    expected_evidence_version: Version
    option_id: OptionId | None
    locale: Literal['vi','en']
    detail_level: Literal['simple','technical']


class SummaryExpression(DTO):
    """No free-form claims/numbers/entities, including hidden optional fields."""
    ordering: tuple[BlockKey, ...] = Field(min_length=6,max_length=6)
    tone: Literal['plain','brief']

    @model_validator(mode='after')
    def coverage(self):
        if set(self.ordering) != {'outcome','cost','requirements','coverage','proof','limitations'}:
            raise ValueError('All material summary families are required exactly once')
        if self.ordering[0] != 'outcome': raise ValueError('Summary must lead with outcome')
        return self


class SummaryProfile(DTO):
    enabled: bool = False
    model: str = Field(min_length=1,max_length=200)
    providers: tuple[str,...] = ()
    max_tokens: int = Field(default=256,ge=64,le=4096)
    input_bytes: int = Field(default=16000,ge=1000,le=64000)
    timeout_seconds: float = Field(default=20.0,gt=0,le=30)
    deadline_seconds: float = Field(default=25.0,gt=0,le=60)
    attempts: int = Field(default=1,ge=1,le=2)
    version: Literal['summary_profile/1','summary_profile/2','summary_profile/3','summary_profile/4'] = 'summary_profile/1'


class SummaryDiagnostics(DTO):
    disposition: Literal['ACCEPTED','FALLBACK']
    reason: Literal['NONE','MODEL_DISABLED','PROVIDER_UNAVAILABLE','SCHEMA_REJECTED','GROUNDING_REJECTED','INPUT_LIMIT','PROCESS_INTERRUPTED']
    prompt_version: Literal['plan_summary_prompt/1','plan_summary_prompt/2','plan_summary_prompt/3'] = 'plan_summary_prompt/1'
    validator_version: Literal['summary_presentation_guard/1','summary_narrative_guard/2'] = 'summary_presentation_guard/1'
    requested_model: str | None
    resolved_model: str | None = Field(default=None,max_length=200)
    resolved_provider: str | None = Field(default=None,max_length=200)
    attempts: int = Field(default=0,ge=0,le=2)
    input_tokens: int | None = Field(default=None,ge=0)
    output_tokens: int | None = Field(default=None,ge=0)


class SummaryClaim(DTO):
    family: BlockKey
    text: str
    evidence_ids: tuple[str,...]


class SummaryAnswer(DTO):
    schema_version: Literal['plan_summary/1'] = 'plan_summary/1'
    identity: EvidenceIdentity
    option_id: str | None
    locale: Literal['vi','en']
    detail_level: Literal['simple','technical']
    source: Literal['deterministic_fallback','model_presentation']
    presentation: SummaryExpression
    answer: str
    claims: tuple[SummaryClaim,...]
    references: tuple[EvidenceReference,...]
    diagnostics: SummaryDiagnostics
    renderer_version: Literal['plan_summary_renderer/1','plan_summary_renderer/2'] = 'plan_summary_renderer/1'


class SummaryGeneration(DTO):
    storage_version: Literal['summary_generation/1'] = 'summary_generation/1'
    generation_id: UUID
    run_id: UUID
    store_id: UUID
    actor_id: UUID
    identity_digest: str
    request: SummaryRequest
    profile: SummaryProfile
    evidence_digest: str
    process: ProcessIdentity
    claim_token: UUID
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    status: Literal['running','completed','failed']
    result: SummaryAnswer | None
    error_code: Literal['AUTHORITY_CHANGED','EXECUTION_ERROR','PROCESS_INTERRUPTED'] | None

    @model_validator(mode='after')
    def lifecycle(self):
        if self.status == 'running':
            if self.finished_at or self.result or self.error_code: raise ValueError('Running generation contains terminal facts')
        elif self.status == 'completed':
            if self.result is None or self.finished_at is None or self.error_code: raise ValueError('Incomplete summary publication')
        elif self.finished_at is None or self.error_code is None or self.result is not None:
            raise ValueError('Failed generation must retain only sanitized failure')
        if self.finished_at and self.finished_at < self.created_at: raise ValueError('Summary time ordering invalid')
        if self.result and (self.result.identity.run_id,self.result.identity.store_id,self.result.identity.aggregate_digest) != (self.run_id,self.store_id,self.request.expected_evidence_version):
            raise ValueError('Summary result does not bind accepted Run/version')
        return self


class SummaryView(DTO):
    generation_id: UUID
    run_id: UUID
    status: Literal['running','completed','failed']
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    result: SummaryAnswer | None
    error_code: str | None


class SummaryMeta(DTO):
    request_id: str


class SummaryEnvelope(DTO):
    data: SummaryView
    meta: SummaryMeta
    error: None = None
