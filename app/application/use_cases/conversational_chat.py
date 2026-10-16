"""AS03 bounded generation/publication, explicit replay without paid recovery."""
from datetime import datetime,timezone
from uuid import uuid4
import time
from decimal import Decimal
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.contracts.assistant_chat import ChatDiagnostics
from app.application.contracts.chat_generation import ChatGeneration
from app.application.planning_serialization import digest,canonical_bytes,exact_json
from app.application.decision_evidence_projection import project_evidence
from app.application.chat_resolution import resolve_question
from app.application.chat_evidence_selection import select_chat_evidence
from app.application.chat_grounding import model_answer,GroundingFailure
from app.application.use_cases.forecast_execution import _is_uncertain_commit
from app.infrastructure.auth_crypto import digest as key_digest
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.planning_process import current_process,liveness
from app.infrastructure.conversational_provider import payload_for
from app.repositories.planning import PlanningRepository
from app.repositories.assistant_message import MessageRepository
from app.repositories.chat_generation import ChatGenerationRepository


def decode_generation(row):
    if row is None:raise AuthError('RESOURCE_NOT_FOUND',404)
    try:
        if row.record_digest!=digest('chat-generation',row.record_json):raise ValueError('Chat hash mismatch')
        record=ChatGeneration.model_validate(row.record_json)
        if canonical_bytes(record)!=canonical_bytes(row.record_json):raise ValueError('Noncanonical generation')
        for column,field in (('id','generation_id'),('actor_id','actor_id'),('store_id','store_id'),('run_id','run_id'),
                             ('key_digest','key_digest'),('request_digest','request_digest'),('status','status'),('created_at','created_at')):
            if getattr(row,column)!=getattr(record,field):raise ValueError('Generation column mismatch')
        if record.request_digest!=digest('assistant-message-request',record.request):raise ValueError('Request digest mismatch')
        return record
    except (ValueError,TypeError,ValidationError) as error:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error


class ConversationalChat:
    def __init__(self,assistant):
        self.owner=assistant;self.engine=assistant.engine
        self.clock=lambda:datetime.now(timezone.utc)

    def prepare(self,token,run,request,version='chat_assertions/6',selection_version='chat_evidence/6'):
        record,view=self.owner.planning.read_record(token,run,evidence_only=True)
        if view.response_version!=request.expected_evidence_version:raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
        winner=view.result.winner_option_id if view.result else None
        evidence=project_evidence(record,view,option_id=request.option_id or winner,include_comparisons=True)
        context=None
        if version in ('chat_assertions/3','chat_assertions/4','chat_assertions/5','chat_assertions/6'):
            from app.application.chat_context import resolve_context
            request,scope,context=resolve_context(request,evidence,'chat_resolution/3' if version=='chat_assertions/3' else 'chat_resolution/4')
        else:scope=resolve_question(request,evidence)
        option=request.option_id or scope.option_id
        if scope.option_id and not scope.clarification:
            evidence=project_evidence(record,view,option_id=option,include_comparisons=True)
        if scope.ingredient_id is not None and not scope.clarification:
            evidence=project_evidence(record,view,option_id=option,ingredient_id=scope.ingredient_id,include_comparisons=True)
        if version in ('chat_assertions/3','chat_assertions/4','chat_assertions/5','chat_assertions/6'):
            from app.application.conversational_evidence import select_evidence
            if context:context=context.model_copy(update={'option_id':evidence.option.option_id if evidence.option else None})
            return evidence,select_evidence(evidence,request,scope,context,selection_version)
        return evidence,select_chat_evidence(evidence,request,scope)

    def publish(self,claimed,answer=None,output=None,error=None,*,token=None,csrf=None):
        with auth_session(self.engine) as session:
            if token is not None:self.owner._authority(session,token,claimed.run_id,csrf)
            repo=ChatGenerationRepository(session)
            old=decode_generation(repo.get(claimed.actor_id,claimed.store_id,claimed.run_id,claimed.key_digest,lock=True))
            if old.status!='running' or old.claim_token!=claimed.claim_token:raise ConfigurationError('STALE_CHAT_CLAIM',409)
            if error is None:
                run=PlanningRepository(session).get(old.store_id,old.run_id)
                if run is None or run.record_digest!=old.request.expected_evidence_version:raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
            proposed=ChatGeneration.model_validate({**old.model_dump(),'status':'failed' if error else 'completed',
                'finished_at':self.clock(),'result':answer,'output':output,'error_code':error})
            row=repo.get(old.actor_id,old.store_id,old.run_id,old.key_digest)
            repo.save(row,proposed)
            if answer is not None:
                receipt=MessageRepository(session).accept(old.actor_id,old.store_id,old.run_id,old.key_digest,old.request_digest,
                    dict(storage_version='assistant_message/2',request=old.request,response=answer,generation_id=old.generation_id))
                if canonical_bytes(receipt.record_json)!=canonical_bytes(dict(storage_version='assistant_message/2',request=old.request,response=answer,generation_id=old.generation_id)):
                    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            session.info['chat_transition']=proposed.status
            session.commit()
        return proposed

    def before_completion(self,token,claimed,csrf):
        with auth_session(self.engine) as session:
            self.owner._authority(session,token,claimed.run_id,csrf)
            row=PlanningRepository(session).get(claimed.store_id,claimed.run_id)
            if row is None or row.record_digest!=claimed.request.expected_evidence_version:
                raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
            session.commit()

    def read(self,token,run,request,key,csrf):
        kd=key_digest(key)
        with auth_session(self.engine) as session:
            actor,store=self.owner._authority(session,token,run,csrf)
            record=decode_generation(ChatGenerationRepository(session).get(actor,store,run,kd))
            if record.request_digest!=digest('assistant-message-request',request):raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
            receipt=MessageRepository(session).get(actor,store,run,kd)
            if record.status=='completed':
                expected=dict(storage_version='assistant_message/2',request=record.request,response=record.result,generation_id=record.generation_id)
                if receipt is None or receipt.record_digest!=digest('assistant-message',receipt.record_json) or \
                    receipt.request_digest!=record.request_digest or canonical_bytes(receipt.record_json)!=canonical_bytes(expected):
                    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            elif receipt is not None:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            session.commit()
        if record.status=='running':raise ConfigurationError('GENERATION_IN_PROGRESS',409)
        if record.status=='failed':raise ConfigurationError('GENERATION_FAILED',409)
        evidence,plan=self.prepare(token,run,record.request,record.validator_version,record.selection_version)
        if digest('chat-evidence',evidence)!=record.evidence_digest or digest('chat-plan',plan)!=record.plan_digest:
            raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        result=record.result;diag=result.diagnostics
        if diag.attempts and diag.prompt_version!=record.prompt_version:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        if diag.attempts and diag.validator_version!=record.validator_version:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        if result.source=='model':
            if not record.profile.enabled or diag.reason!='NONE' or diag.disposition not in ('ACCEPTED','REPAIRED','TRIMMED','REGENERATED') or \
                diag.model!=record.profile.model or diag.resolved_model!=record.profile.model or not 1<=diag.attempts<=record.profile.completion_limit or record.output is None:
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            try:
                if record.validator_version in ('chat_assertions/3','chat_assertions/4','chat_assertions/5','chat_assertions/6'):
                    from app.application.chat_assertions import semantic_answer
                    expected=semantic_answer(record.output,plan,diag)
                else:expected=model_answer(record.output,plan,diag)
            except (ValueError,ValidationError) as error:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error
        else:
            if record.output is not None or diag.reason=='NONE':raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            expected=plan.fallback.model_copy(update={'diagnostics':diag})
        if canonical_bytes(expected)!=canonical_bytes(result):raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        with auth_session(self.engine) as session:
            self.owner._authority(session,token,run,csrf);session.commit()
        return result

    def create(self,token,run,request,key,csrf):
        evidence,plan=self.prepare(token,run,request)
        kd=key_digest(key);fingerprint=digest('assistant-message-request',request)
        claimed=None;inserted=False;legacy=False
        try:
            with auth_session(self.engine) as session:
                actor,store=self.owner._authority(session,token,run,csrf)
                MessageRepository(session).lock_key(actor,store,run,kd)
                repo=ChatGenerationRepository(session)
                row=repo.get(actor,store,run,kd)
                if row is not None:
                    claimed=decode_generation(row)
                    if claimed.request_digest!=fingerprint:raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
                elif MessageRepository(session).get(actor,store,run,kd) is not None:legacy=True
                else:
                    retained=PlanningRepository(session).get(store,run)
                    if retained.record_digest!=request.expected_evidence_version:raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
                    if repo.running_count(store)>=20:raise ConfigurationError('GENERATION_LIMIT_EXCEEDED',429)
                    claimed=ChatGeneration(generation_id=uuid4(),actor_id=actor,store_id=store,run_id=run,key_digest=kd,
                        request_digest=fingerprint,request=request,profile=self.owner.profile,
                        evidence_digest=digest('chat-evidence',evidence),plan_digest=digest('chat-plan',plan),
                        process=current_process(),claim_token=uuid4(),created_at=self.clock(),prompt_version='conversational_chat_prompt/5',
                        validator_version='chat_assertions/6',schema_version='conversational_assertions/2')
                    claimed=claimed.model_copy(update={'selection_version':'chat_evidence/6'})
                    repo.accept(claimed);inserted=True
                session.info['chat_accept']=inserted
                session.commit()
        except SQLAlchemyError as error:
            if claimed is None or not inserted or not _is_uncertain_commit(error):raise AuthError('SERVICE_UNAVAILABLE',503) from error
            with auth_session(self.engine) as session:
                self.owner._authority(session,token,run,csrf)
                row=ChatGenerationRepository(session).get(claimed.actor_id,claimed.store_id,run,kd)
                actual=decode_generation(row) if row else None
                if actual is None or canonical_bytes(actual)!=canonical_bytes(claimed):raise AuthError('SERVICE_UNAVAILABLE',503) from error
                session.commit()
        if legacy:return self.owner.create(token,run,request,key,csrf)
        if not inserted:
            if claimed.status=='running' and liveness(claimed.process)=='DEAD':
                self.publish(claimed,error='PROCESS_INTERRUPTED',token=token,csrf=csrf)
            return self.read(token,run,request,key,csrf)
        answer=plan.fallback;output=None
        try:
            if plan.fallback.kind=='answer' and not plan.facts:
                answer=plan.fallback.model_copy(update={'diagnostics':ChatDiagnostics(reason='WORDING_UNSUPPORTED',model=claimed.profile.model)})
            if plan.fallback.kind=='answer' and plan.facts:
                if len(plan.required)>16 or len(plan.facts)>24:
                    answer=plan.fallback.model_copy(update={'diagnostics':ChatDiagnostics(reason='INPUT_LIMIT',model=claimed.profile.model)})
                else:
                    answer,output=self.generate(claimed,plan,request,token,csrf)
            self.publish(claimed,answer,output,token=token,csrf=csrf)
        except AuthError as error:
            try:self.publish(claimed,error='AUTHORITY_CHANGED')
            except Exception as cleanup:error.add_note('Chat failure publication: '+type(cleanup).__name__)
            raise
        except Exception as error:
            # Do not turn programming/DB failures into a fabricated successful answer.
            with auth_session(self.engine) as session:
                row=ChatGenerationRepository(session).get(claimed.actor_id,claimed.store_id,run,kd)
                actual=decode_generation(row)
                session.commit()
            if not (isinstance(error,SQLAlchemyError) and _is_uncertain_commit(error) and actual.status=='completed' and
                    actual.claim_token==claimed.claim_token and canonical_bytes(actual.result)==canonical_bytes(answer)):
                if actual.status=='running':
                    try:self.publish(claimed,error='EXECUTION_ERROR')
                    except Exception as cleanup:error.add_note('Chat cleanup publication: '+type(cleanup).__name__)
                if isinstance(error,SQLAlchemyError):raise AuthError('SERVICE_UNAVAILABLE',503) from error
                raise
        return self.read(token,run,request,key,csrf)

    def generate(self,claimed,plan,request,token,csrf):
        from app.application.chat_assertions import inspect_output,semantic_answer
        from app.application.contracts.chat_generation import SemanticOutput
        from app.infrastructure.conversational_provider import ChatProviderResult
        from pydantic import ValidationError
        started=time.monotonic();payload=payload_for(plan,request);trace=[];attempts=0;cost=Decimal(0);unknown_cost=False
        inputs=outputs=0;reserved=Decimal(0);last=None;unknown_input=unknown_output=False
        # The complete serialized request is byte-bounded; byte count plus1024
        # conservatively bounds text tokens, including protocol overhead.
        bound=(Decimal(claimed.profile.input_bytes+1024)*Decimal(claimed.profile.max_prompt_price)+
            Decimal(claimed.profile.max_tokens)*Decimal(claimed.profile.max_completion_price))/1000000
        for iteration in range(claimed.profile.completion_limit):
            remaining=claimed.profile.deadline_seconds-(time.monotonic()-started)
            if remaining<=0 or reserved+bound>Decimal(claimed.profile.max_request_cost_usd):
                trace.append('SHARED_DEADLINE_OR_COST_BOUND');break
            profile=claimed.profile.model_copy(update={'deadline_seconds':remaining})
            try:
                presented=self.owner.provider.generate(payload,profile,before_completion=lambda:self.before_completion(token,claimed,csrf))
            except (TimeoutError,OSError):
                presented=ChatProviderResult(None,ChatDiagnostics(reason='PROVIDER_UNAVAILABLE',model=claimed.profile.model,attempts=1,
                    prompt_version=claimed.prompt_version,validator_version=claimed.validator_version))
            diag=presented.diagnostics;last=diag
            attempts+=diag.attempts
            if diag.attempts:
                reserved+=bound
                unknown_input=unknown_input or diag.input_tokens is None
                unknown_output=unknown_output or diag.output_tokens is None
                if diag.cost_usd is None:unknown_cost=True
                else:cost+=Decimal(diag.cost_usd)
            inputs+=diag.input_tokens or 0;outputs+=diag.output_tokens or 0
            updates=dict(attempts=attempts,input_tokens=None if unknown_input else inputs,output_tokens=None if unknown_output else outputs,
                cost_usd=None if unknown_cost else str(cost),latency_ms=int((time.monotonic()-started)*1000),failure_trace=tuple(trace))
            diag=diag.model_copy(update=updates)
            compatible=diag.model==claimed.profile.model and diag.resolved_model==claimed.profile.model and diag.provider and presented.diagnostics.attempts==1
            if presented.output is None or diag.reason!='NONE' or diag.disposition!='ACCEPTED' or not compatible:
                # Transport/schema/refusal/unknown billing outcomes are terminal:
                # regeneration is only for a known schema-valid semantic result.
                return plan.fallback.model_copy(update={'diagnostics':diag.model_copy(update={'reason':diag.reason if diag.reason!='NONE' else 'GROUNDING_REJECTED','disposition':'FALLBACK'})}),None
            try:checked=inspect_output(SemanticOutput.model_validate(presented.output),plan,request.locale)
            except ValidationError:
                return plan.fallback.model_copy(update={'diagnostics':diag.model_copy(update={'reason':'SCHEMA_REJECTED','disposition':'FALLBACK'})}),None
            trace.extend(checked.failures)
            if checked.output is not None:
                diag=diag.model_copy(update={'disposition':'REGENERATED' if iteration else checked.disposition,'failure_trace':tuple(trace)})
                return semantic_answer(checked.output,plan,diag),checked.output
            payload={**payload,'feedback':{'failures':list(checked.failures),
                'permitted_wording':[{k:f[k] for k in ('fact_id','wording')} for f in payload['facts']],
                'instruction':'Use only the original sealed facts. Use permitted wording for unsupported material prose; cover required facts.'}}
        if last is None:last=ChatDiagnostics(reason='PREFLIGHT_REJECTED',model=claimed.profile.model,prompt_version=claimed.prompt_version,validator_version=claimed.validator_version)
        reason='COVERAGE_REJECTED' if any('MISSING_MAIN' in t for t in trace) else 'GROUNDING_REJECTED'
        diag=last.model_copy(update={'reason':reason,'disposition':'FALLBACK','failure_trace':tuple(trace),'attempts':attempts,
            'input_tokens':None if unknown_input else inputs or None,'output_tokens':None if unknown_output else outputs or None,'cost_usd':None if unknown_cost else str(cost),
            'latency_ms':int((time.monotonic()-started)*1000)})
        return plan.fallback.model_copy(update={'diagnostics':diag}),None
