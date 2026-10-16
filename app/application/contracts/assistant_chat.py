"""L3 bounded question/history and server-owned evidence answer."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator, model_serializer
from app.application.contracts.auth import DTO
from app.application.contracts.plan_summary import SummaryRequest, SummaryMeta
from app.application.contracts.decision_evidence import EvidenceReference


class HistoryMessage(DTO):
    role: Literal['user','assistant']
    content: str = Field(min_length=1,max_length=2000)


class PendingQuestion(DTO):
    original_question: str = Field(min_length=1,max_length=2000)
    candidate_ids: tuple[UUID,...] = Field(max_length=30)
    entity_kind: Literal['ingredient','product'] = 'ingredient'

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.entity_kind=='ingredient':data.pop('entity_kind',None)
        return data


class ChatContext(DTO):
    run_id: UUID
    evidence_version: str
    option_id: str | None = None
    comparison_pair: tuple[str,str] | None = None
    ingredient_id: UUID | None = None
    product_id: UUID | None = None
    pending: PendingQuestion | None = None
    topic: Literal['purchase','purchase_rationale','stock','daily_shortage','daily_ending'] | None = None


class ChatRequest(SummaryRequest):
    question: str = Field(min_length=1,max_length=2000)
    ingredient_id: UUID | None
    history: tuple[HistoryMessage,...] = Field(max_length=6)
    context: ChatContext | None = None

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.context is None:data.pop('context',None)
        return data

    @model_validator(mode='after')
    def bounded(self):
        if not self.question.strip() or sum(len(m.content) for m in self.history)>4000:
            raise ValueError('Empty question or history exceeds 4000 characters')
        return self


class ChatClaim(DTO):
    text: str
    evidence_ids: tuple[str,...]


class IngredientCandidate(DTO):
    ingredient_id: UUID
    name: str


class OptionCandidate(DTO):
    option_id: str
    source_strategies: tuple[Literal['lean','balanced','protected'],...]


class ProductCandidate(DTO):
    product_id: UUID
    name: str


class Clarification(DTO):
    code: Literal['ENTITY_AMBIGUOUS','ENTITY_CONTEXT_MISMATCH','QUERY_UNSUPPORTED']
    question: str
    candidates: tuple[IngredientCandidate,...]
    original_question: str
    option_candidates: tuple[OptionCandidate,...] = ()
    product_candidates: tuple[ProductCandidate,...] = ()

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if not self.product_candidates:data.pop('product_candidates',None)
        return data


class ChatDiagnostics(DTO):
    reason: Literal['NONE','MODEL_DISABLED','EVIDENCE_INSUFFICIENT','PROVIDER_UNAVAILABLE','PREFLIGHT_REJECTED',
                    'SCHEMA_REJECTED','GROUNDING_REJECTED','COVERAGE_REJECTED','INPUT_LIMIT','PROCESS_INTERRUPTED','WORDING_UNSUPPORTED']
    prompt_version: str | None = None
    validator_version: str = 'decision_chat_renderer/1'
    model: str | None = None
    resolved_model: str | None = None
    provider: str | None = None
    attempts: int = Field(default=0,ge=0,le=2)
    input_tokens: int | None = Field(default=None,ge=0)
    output_tokens: int | None = Field(default=None,ge=0)
    cost_usd: str | None = None
    latency_ms: int | None = Field(default=None,ge=0)
    finish_reason: str | None = None
    disposition: Literal['ACCEPTED','REPAIRED','TRIMMED','REGENERATED','FALLBACK','CLARIFICATION'] = 'FALLBACK'
    prompt_hash: str | None = None
    schema_hash: str | None = None
    evidence_hash: str | None = None
    failure_trace: tuple[str,...] = ()

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if not self.failure_trace:data.pop('failure_trace',None)
        return data


class AssistantResponse(DTO):
    schema_version: Literal['decision_assistant/1'] = 'decision_assistant/1'
    run_id: UUID
    evidence_version: str
    result_digest: str | None
    option_id: str | None
    ingredient_id: UUID | None
    locale: Literal['vi','en']
    kind: Literal['answer','clarification']
    source: Literal['model','deterministic_fallback','deterministic_clarification']
    answer: str
    claims: tuple[ChatClaim,...]
    references: tuple[EvidenceReference,...]
    clarification: Clarification | None
    diagnostics: ChatDiagnostics
    context: ChatContext | None = None

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.context is None:data.pop('context',None)
        return data

    @model_validator(mode='after')
    def consistent(self):
        if (self.kind=='clarification') != (self.clarification is not None):
            raise ValueError('Clarification kind mismatch')
        if self.kind=='answer':
            if self.source not in ('model','deterministic_fallback') or not self.claims:
                raise ValueError('Answer requires grounded claims')
            if self.answer!='\n\n'.join(c.text for c in self.claims):
                raise ValueError('Answer differs from claims')
        elif self.source!='deterministic_clarification' or self.claims or self.references:
            raise ValueError('Clarification cannot assert facts')
        issued={r.evidence_id for r in self.references}
        if any(not c.evidence_ids or not set(c.evidence_ids)<=issued for c in self.claims):
            raise ValueError('Ungrounded chat claim')
        return self


class ChatEnvelope(DTO):
    data: AssistantResponse
    meta: SummaryMeta
    error: None = None
