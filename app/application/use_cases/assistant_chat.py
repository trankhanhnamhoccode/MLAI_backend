"""Authorized retained read intents, deterministic durable replay; never a model call."""
from uuid import UUID
from pydantic import ValidationError
from app.application.contracts.auth import AuthError
from app.application.contracts.assistant_chat import ChatRequest, AssistantResponse
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.decision_evidence_projection import project_evidence
from app.application.assistant_chat_rendering import scope_question, render_chat
from app.application.planning_serialization import canonical_bytes, digest
from app.application.use_cases.planning_public import READ_PERMISSIONS
from app.infrastructure.auth_crypto import digest as key_digest
from app.infrastructure.database.auth_session import auth_session
from app.repositories.planning import PlanningRepository
from app.repositories.assistant_message import MessageRepository


class AssistantChat:
    def __init__(self, planning, profile=None, provider=None,*,presentation_version=6):
        if presentation_version not in (6,7,8):raise ValueError('Unsupported presentation version')
        self.presentation_version=presentation_version
        self.planning,self.auth,self.engine=planning,planning.auth,planning.engine
        from app.application.contracts.chat_generation import ChatProfile
        self.profile=profile or ChatProfile()
        self.provider=provider

    def _authority(self, session, token, run_id, csrf):
        store=PlanningRepository(session).owning_store(run_id)
        if store is None:
            self.auth._resolve(session,token)
            raise AuthError('RESOURCE_NOT_FOUND',404)
        actor,_,_=self.auth.authorize_in_session(session,token,store,READ_PERMISSIONS,csrf=csrf or '')
        return actor.user_id,store

    def _answer(self, token, run_id, request, conversational=False):
        if conversational:
            from app.application.use_cases.conversational_chat import ConversationalChat
            _,plan=ConversationalChat(self).prepare(token,run_id,request,
                'chat_assertions/8' if conversational==9 else 'chat_assertions/7' if conversational==8 else 'chat_assertion_grammar/2' if conversational==2 else 'chat_assertions/3',
                'chat_evidence/8' if conversational==9 else 'chat_evidence/7' if conversational==8 else 'chat_evidence/2' if conversational in (2,3) else 'chat_evidence/3')
            diagnostics=plan.fallback.diagnostics.model_copy(update={'validator_version':f'decision_chat_renderer/{conversational}'})
            return plan.fallback.model_copy(update={'diagnostics':diagnostics})
        record,view=self.planning.read_record(token,run_id,evidence_only=True)
        if view.response_version!=request.expected_evidence_version:
            raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
        winner=view.result.winner_option_id if view.result else None
        option=request.option_id or winner
        evidence=project_evidence(record,view,option_id=option,include_comparisons=True)
        scope=scope_question(request,evidence)
        if scope.ingredient_id is not None and not scope.clarification:
            evidence=project_evidence(record,view,option_id=request.option_id,ingredient_id=scope.ingredient_id,include_comparisons=True)
        return render_chat(evidence,request,scope)

    def _decode(self, row, request, expected):
        if row.request_digest!=digest('assistant-message-request',request):
            raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
        try:
            raw=row.record_json
            if row.record_digest!=digest('assistant-message',raw): raise ValueError('Message hash mismatch')
            if set(raw)!={'storage_version','request','response'} or raw['storage_version']!='assistant_message/1':
                raise ValueError('Unsupported message record')
            saved_request=ChatRequest.model_validate(raw['request'])
            response=AssistantResponse.model_validate(raw['response'])
            encoded=response.model_dump(mode='json')
            legacy_fields={'reason','prompt_version','validator_version','model'}
            if set(raw['response']['diagnostics'])<=legacy_fields:
                encoded['diagnostics']={k:v for k,v in encoded['diagnostics'].items() if k in legacy_fields}
            if raw['response'].get('clarification') and 'option_candidates' not in raw['response']['clarification']:
                encoded['clarification'].pop('option_candidates',None)
            if response.source=='model':raise ValueError('Provider result requires generation verification')
            if canonical_bytes(raw)!=canonical_bytes(dict(storage_version='assistant_message/1',request=saved_request,response=encoded)):
                raise ValueError('Noncanonical retained message')
            if canonical_bytes(saved_request)!=canonical_bytes(request) or canonical_bytes(response)!=canonical_bytes(expected):
                raise ValueError('Retained message differs from pinned evidence/renderer')
            if (response.run_id,response.evidence_version)!=(row.run_id,request.expected_evidence_version):
                raise ValueError('Message belongs to another Run')
            return response
        except (ValueError,TypeError,KeyError,ValidationError) as error:
            raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error

    def create(self, token, run_id, request, key, csrf):
        try:
            if key is None or str(UUID(key))!=key: raise ValueError()
        except (ValueError,TypeError): raise ConfigurationError('INVALID_REQUEST',400) from None
        kd=key_digest(key)
        # Current rights/CSRF precede evidence materialization and receipt reads.
        with auth_session(self.engine) as session:
            actor,store=self._authority(session,token,run_id,csrf)
            MessageRepository(session).lock_key(actor,store,run_id,kd)
            prior=MessageRepository(session).get(actor,store,run_id,kd)
            if prior and prior.request_digest!=digest('assistant-message-request',request):
                raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
            from app.repositories.chat_generation import ChatGenerationRepository
            generation=ChatGenerationRepository(session).get(actor,store,run_id,kd)
            if generation is not None and generation.request_digest!=digest('assistant-message-request',request):
                raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
            use_generation=generation is not None or (self.profile.enabled and prior is None)
            session.commit()
        if use_generation:
            from app.application.use_cases.conversational_chat import ConversationalChat
            return ConversationalChat(self).create(token,run_id,request,key,csrf)
        # New model-OFF work uses the same resolver/evidence-family fallback.
        # Retained /1 renderer receipts keep their original interpretation.
        renderer=prior.record_json.get('response',{}).get('diagnostics',{}).get('validator_version') if prior else None
        use_new_renderer=9 if renderer=='decision_chat_renderer/9' or (prior is None and self.presentation_version==8) else 8 if renderer=='decision_chat_renderer/8' or (prior is None and self.presentation_version==7) else 4 if prior is None or renderer=='decision_chat_renderer/4' else 3 if renderer=='decision_chat_renderer/3' else 2 if renderer=='decision_chat_renderer/2' else False
        answer=self._answer(token,run_id,request,use_new_renderer)
        with auth_session(self.engine) as session:
            current_actor,current_store=self._authority(session,token,run_id,csrf)
            MessageRepository(session).lock_key(actor,store,run_id,kd)
            if (current_actor,current_store)!=(actor,store): raise AuthError('PERMISSION_DENIED')
            row=PlanningRepository(session).get(store,run_id)
            if row.record_digest!=request.expected_evidence_version:
                raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
            generation=ChatGenerationRepository(session).get(actor,store,run_id,kd)
            if generation is None:
                receipt=MessageRepository(session).accept(actor,store,run_id,kd,
                    digest('assistant-message-request',request),dict(storage_version='assistant_message/1',request=request,response=answer))
                result=self._decode(receipt,request,answer)
            session.commit()
        if generation is not None:
            from app.application.use_cases.conversational_chat import ConversationalChat
            return ConversationalChat(self).create(token,run_id,request,key,csrf)
        # No provider/engine runs at any point. Lost commit ACK can safely be
        # retried explicitly with this key; an unapplied receipt returns no 200.
        with auth_session(self.engine) as session:
            self._authority(session,token,run_id,csrf)
            session.commit()
        return result
