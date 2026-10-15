"""AS03 acceptance/one attempt/publication, explicit replay without paid recovery."""
from datetime import datetime,timezone
from uuid import uuid4
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

    def prepare(self,token,run,request):
        record,view=self.owner.planning.read_record(token,run,evidence_only=True)
        if view.response_version!=request.expected_evidence_version:raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
        winner=view.result.winner_option_id if view.result else None
        evidence=project_evidence(record,view,option_id=request.option_id or winner,include_comparisons=True)
        scope=resolve_question(request,evidence)
        option=request.option_id or scope.option_id
        if scope.option_id and not scope.clarification:
            evidence=project_evidence(record,view,option_id=option,include_comparisons=True)
        if scope.ingredient_id is not None and not scope.clarification:
            evidence=project_evidence(record,view,option_id=option,ingredient_id=scope.ingredient_id,include_comparisons=True)
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
        evidence,plan=self.prepare(token,run,record.request)
        if digest('chat-evidence',evidence)!=record.evidence_digest or digest('chat-plan',plan)!=record.plan_digest:
            raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        result=record.result;diag=result.diagnostics
        if diag.attempts and diag.prompt_version!=record.prompt_version:raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        if result.source=='model':
            if not record.profile.enabled or diag.reason!='NONE' or diag.disposition!='ACCEPTED' or \
                diag.model!=record.profile.model or diag.resolved_model!=record.profile.model or diag.attempts!=1 or record.output is None:
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            try:expected=model_answer(record.output,plan,diag)
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
                        process=current_process(),claim_token=uuid4(),created_at=self.clock())
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
                if len(plan.facts)>8:
                    answer=plan.fallback.model_copy(update={'diagnostics':ChatDiagnostics(reason='INPUT_LIMIT',model=claimed.profile.model)})
                else:
                    # All sessions and acceptance locks have closed before preflight/provider.
                    try:
                        presented=self.owner.provider.generate(payload_for(plan,request),claimed.profile,
                            before_completion=lambda:self.before_completion(token,claimed,csrf))
                    except (TimeoutError,OSError):
                        from app.infrastructure.conversational_provider import ChatProviderResult
                        presented=ChatProviderResult(None,ChatDiagnostics(reason='PROVIDER_UNAVAILABLE',model=claimed.profile.model,attempts=1,
                            prompt_version=claimed.prompt_version,validator_version=claimed.validator_version))
                    diag=ChatDiagnostics.model_validate(presented.diagnostics.model_dump())
                    compatible=diag.model==claimed.profile.model and diag.resolved_model==claimed.profile.model and diag.provider and diag.attempts==1
                    if diag.disposition=='ACCEPTED' and not compatible:
                        diag=diag.model_copy(update={'model':claimed.profile.model,'reason':'GROUNDING_REJECTED','disposition':'FALLBACK'})
                    if presented.output is not None and diag.reason=='NONE' and diag.disposition=='ACCEPTED':
                        try:answer=model_answer(presented.output,plan,diag);output=presented.output
                        except GroundingFailure as error:
                            answer=plan.fallback.model_copy(update={'diagnostics':diag.model_copy(update={'reason':error.reason,'disposition':'FALLBACK'})})
                    else:answer=plan.fallback.model_copy(update={'diagnostics':diag})
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
