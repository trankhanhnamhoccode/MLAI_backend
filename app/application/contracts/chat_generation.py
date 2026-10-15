"""Task-specific conversational generation, sealed evidence cards and durable claim."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator, model_serializer
from app.application.contracts.auth import DTO
from app.application.contracts.assistant_chat import ChatRequest, AssistantResponse, ChatClaim
from app.application.contracts.decision_evidence import EvidenceIdentity
from app.application.contracts.planning_run import ProcessIdentity


class ChatProfile(DTO):
    version: Literal['chat_profile/1']='chat_profile/1'
    enabled: bool=False
    model: str = Field(default='UNCONFIGURED',min_length=1,max_length=200)
    providers: tuple[str,...]=()
    max_tokens: int = Field(default=768,ge=128,le=1200)
    input_bytes: int = Field(default=12000,ge=1000,le=24000)
    timeout_seconds: float = Field(default=25.0,gt=0,le=30)
    deadline_seconds: float = Field(default=30.0,gt=0,le=60)
    max_prompt_price: str = '0.3'
    max_completion_price: str = '2.5'
    completion_limit: int = Field(default=1,ge=1,le=2)
    max_request_cost_usd: str = '0.10'

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.completion_limit==1:data.pop('completion_limit',None)
        if self.max_request_cost_usd=='0.10':data.pop('max_request_cost_usd',None)
        return data

    @model_validator(mode='after')
    def prices(self):
        from decimal import Decimal,InvalidOperation
        for value in (self.max_prompt_price,self.max_completion_price,self.max_request_cost_usd):
            try:valid=Decimal(value).is_finite() and Decimal(value)>0
            except InvalidOperation:valid=False
            if not valid:raise ValueError('Positive finite USD/M token price required')
        return self


class FactCard(DTO):
    fact_id: str
    kind: str
    meaning: str
    display: str | None = None
    unit: str | None = None
    entity_id: str | None = None
    path: str | None = None
    requested: str | None = None
    lost_sales: str | None = None
    service_percent: str | None = None
    option_role: Literal['viewed','recommended'] | None = None
    evidence_ids: tuple[str,...]
    label: str | None = None

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.label is None:data.pop('label',None)
        return data


class ChatEvidencePlan(DTO):
    version: Literal['chat_evidence/1','chat_evidence/2','chat_evidence/3']='chat_evidence/1'
    resolver_version: Literal['chat_resolution/2','chat_resolution/3']='chat_resolution/2'
    identity: EvidenceIdentity
    intent: str
    option_id: str | None
    ingredient_id: UUID | None
    facts: tuple[FactCard,...]
    required: tuple[str,...]
    safety_claims: tuple[ChatClaim,...]
    fallback: AssistantResponse


class ModelStatement(DTO):
    text: str = Field(min_length=1,max_length=1500)
    fact_ids: tuple[str,...] = Field(min_length=1,max_length=8)


class ConversationalOutput(DTO):
    statements: tuple[ModelStatement,...] = Field(min_length=1,max_length=8)


class ProposedAssertion(DTO):
    fact_id: str
    value: str | None
    unit: str | None
    entity_id: str | None
    path: str | None
    option_role: Literal['viewed','recommended'] | None
    polarity: Literal['affirmed','unavailable']
    text: str = Field(min_length=1,max_length=1500)


class SemanticOutput(DTO):
    assertions: tuple[ProposedAssertion,...] = Field(min_length=1,max_length=16)


class ChatGeneration(DTO):
    storage_version: Literal['chat_generation/1']='chat_generation/1'
    generation_id: UUID
    actor_id: UUID
    store_id: UUID
    run_id: UUID
    key_digest: str
    request_digest: str
    request: ChatRequest
    profile: ChatProfile
    evidence_digest: str
    plan_digest: str
    selection_version: Literal['chat_evidence/2','chat_evidence/3']='chat_evidence/2'
    prompt_version: Literal['conversational_chat_prompt/1','conversational_chat_prompt/2','conversational_chat_prompt/3']='conversational_chat_prompt/2'
    validator_version: Literal['chat_assertion_grammar/1','chat_assertion_grammar/2','chat_assertions/3']='chat_assertion_grammar/2'
    schema_version: Literal['conversational_output/1','conversational_assertions/2']='conversational_output/1'
    process: ProcessIdentity
    claim_token: UUID
    created_at: AwareDatetime
    finished_at: AwareDatetime | None=None
    status: Literal['running','completed','failed']='running'
    result: AssistantResponse | None=None
    output: ConversationalOutput | SemanticOutput | None=None
    error_code: Literal['AUTHORITY_CHANGED','EXECUTION_ERROR','PROCESS_INTERRUPTED'] | None=None

    @model_serializer(mode='wrap')
    def retained_shape(self,handler):
        data=handler(self)
        if self.selection_version=='chat_evidence/2':data.pop('selection_version',None)
        return data

    @model_validator(mode='after')
    def lifecycle(self):
        if self.status=='running':
            if self.result or self.output or self.finished_at or self.error_code:raise ValueError('Running generation is terminal')
        elif self.status=='completed':
            if not self.result or not self.finished_at or self.error_code:raise ValueError('Incomplete terminal result')
        elif self.result or self.output or not self.finished_at or not self.error_code:raise ValueError('Invalid failed generation')
        if self.finished_at and self.finished_at<self.created_at:raise ValueError('Invalid time order')
        if self.result and (self.result.run_id,self.result.evidence_version)!=(self.run_id,self.request.expected_evidence_version):
            raise ValueError('Foreign generation result')
        return self
