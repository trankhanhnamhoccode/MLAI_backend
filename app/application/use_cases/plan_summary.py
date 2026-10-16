"""Synchronous durable summary lifecycle; provider work never holds a Session."""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.application.use_cases.forecast_execution import _is_uncertain_commit
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_configuration import ConfigurationError
from app.application.contracts.plan_summary import (
    SummaryGeneration, SummaryView, SummaryDiagnostics, SummaryExpression,
)
from app.application.decision_evidence_projection import project_evidence
from app.application.plan_summary_rendering import render_summary, DEFAULT_EXPRESSION
from app.application.summary_narrative import versions, render_narrative, replay_narrative, diagnostics_v2
from app.application.contracts.summary_narrative import SummaryNarrative
from app.application.planning_serialization import digest, canonical_bytes
from app.application.use_cases.planning_public import READ_PERMISSIONS
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.auth_crypto import digest as key_digest
from app.infrastructure.planning_process import current_process, liveness
from app.infrastructure.plan_summary_provider import payload_for
from app.repositories.planning import PlanningRepository
from app.repositories.plan_summary import SummaryRepository


def decode_summary(row):
    if row is None: raise AuthError('RESOURCE_NOT_FOUND',404)
    try:
        if row.record_digest != digest('summary',row.record_json): raise ValueError('Summary digest mismatch')
        result = SummaryGeneration.model_validate(row.record_json)
        if canonical_bytes(result) != canonical_bytes(row.record_json): raise ValueError('Noncanonical summary')
        for column, field in (('id','generation_id'),('actor_id','actor_id'),('store_id','store_id'),
                              ('run_id','run_id'),('identity_digest','identity_digest'),('status','status'),('created_at','created_at')):
            if getattr(row,column) != getattr(result,field): raise ValueError('Summary identity mismatch')
        return result
    except (ValueError,TypeError,ValidationError) as error:
        raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error


def view(record):
    return SummaryView(**record.model_dump(include=set(SummaryView.model_fields)))


class _ReceiptReplay(Exception):
    """A concurrent immutable key won; roll back our unreferenced insertion."""


class PlanSummaries:
    def __init__(self, planning, profile, provider, *, clock=None):
        self.planning, self.auth, self.engine = planning, planning.auth, planning.engine
        self.profile, self.provider = profile, provider
        self.clock = clock or (lambda:datetime.now(timezone.utc))

    def _authority(self, session, token, run_id, csrf=None):
        store = PlanningRepository(session).owning_store(run_id)
        if store is None:
            self.auth._resolve(session,token)
            raise AuthError('RESOURCE_NOT_FOUND',404)
        actor,_,_ = self.auth.authorize_in_session(session,token,store,READ_PERMISSIONS,
            **({'csrf':csrf or ''} if csrf is not None else {}))
        return actor,store

    def _evidence(self, token, run_id, request):
        record, projected = self.planning.read_record(token,run_id,evidence_only=True)
        if projected.response_version != request.expected_evidence_version:
            raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
        winner = projected.result.winner_option_id if projected.result else None
        return project_evidence(record,projected,option_id=request.option_id or winner,include_comparisons=True)

    def _check(self, record, evidence):
        if digest('summary-evidence',evidence) != record.evidence_digest:
            raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        expected = digest('summary-identity',dict(actor=record.actor_id,run=record.run_id,store=record.store_id,
            request=record.request,profile=record.profile,evidence=record.evidence_digest,
            **versions(record.profile)))
        if expected != record.identity_digest: raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
        if record.result:
            diagnostics=record.result.diagnostics
            if diagnostics.reason=='MODEL_DISABLED':
                if record.profile.enabled or diagnostics.attempts or diagnostics.disposition!='FALLBACK':
                    raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            elif diagnostics.requested_model!=record.profile.model:
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            if diagnostics.disposition=='ACCEPTED' and (not record.profile.enabled or diagnostics.reason!='NONE'):
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)
            expression = record.result.presentation
            try:
                expected_result = (replay_narrative(evidence,record.request,record.result)
                    if record.profile.version == 'summary_profile/2' else
                    render_summary(evidence,record.request,record.result.diagnostics,expression))
            except ValueError as error:
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503) from error
            if canonical_bytes(expected_result) != canonical_bytes(record.result):
                raise AuthError('RESULT_INTEGRITY_UNAVAILABLE',503)

    def read(self, token, run_id, ident):
        with auth_session(self.engine) as session:
            _,store = self._authority(session,token,run_id)
            record = decode_summary(SummaryRepository(session).get(store,run_id,ident))
            session.commit()
        evidence = self._evidence(token,run_id,record.request)
        self._check(record,evidence)
        # Recheck current authority after materialization, before delivery.
        with auth_session(self.engine) as session:
            self._authority(session,token,run_id)
            session.commit()
        return view(record)

    def _publish(self, claimed, result=None, error=None, *, token=None, csrf=None):
        with auth_session(self.engine) as session:
            if token is not None: self._authority(session,token,claimed.run_id,csrf)
            repo = SummaryRepository(session)
            row = repo.get(claimed.store_id,claimed.run_id,claimed.generation_id,lock=True)
            old = decode_summary(row)
            if old.status != 'running' or old.claim_token != claimed.claim_token:
                raise ConfigurationError('STALE_SUMMARY_CLAIM',409)
            run = PlanningRepository(session).get(old.store_id,old.run_id)
            if not error and (run is None or run.record_digest != old.request.expected_evidence_version):
                raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
            proposed = SummaryGeneration.model_validate({**old.model_dump(),
                'status':'failed' if error else 'completed','finished_at':self.clock(),'result':result,'error_code':error})
            repo.save(row,proposed)
            session.info['summary_transition']=proposed.status
            session.commit()
        return proposed

    def create(self, token, run_id, request, key, csrf):
        # None means a read to the shared authority helper. Mutations must pass
        # an explicit value even when the header is absent, so Auth rejects it.
        csrf=csrf or ''
        try:
            if key is None or str(UUID(key)) != key: raise ValueError()
        except (TypeError,ValueError): raise ConfigurationError('INVALID_REQUEST',400) from None
        kd = key_digest(key)
        fingerprint = digest('summary-request',request)
        # Replay authority precedes any receipt/summary contents. The request body
        # alone owns idempotency; profile/config changes never start a replay call.
        with auth_session(self.engine) as session:
            actor,store = self._authority(session,token,run_id,csrf)
            receipt = SummaryRepository(session).receipt(actor.user_id,store,run_id,kd)
            if receipt:
                if receipt.request_digest != fingerprint: raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
                prior = decode_summary(SummaryRepository(session).get(store,run_id,receipt.generation_id))
                session.commit()
            else: prior = None
        if prior:
            if prior.status == 'running':
                if liveness(prior.process) != 'DEAD': raise ConfigurationError('GENERATION_IN_PROGRESS',409)
                # Explicit replay may fail work owned by an OS-proven dead process;
                # never repeat an ambiguous billed attempt after restart.
                prior = self._publish(prior,error='PROCESS_INTERRUPTED',token=token,csrf=csrf)
            return self.read(token,run_id,prior.generation_id)
        evidence = self._evidence(token,run_id,request)
        evidence_digest = digest('summary-evidence',evidence)
        claimed = None
        try:
            with auth_session(self.engine) as session:
                actor,store = self._authority(session,token,run_id,csrf)
                run = PlanningRepository(session).get(store,run_id)
                if run.record_digest != request.expected_evidence_version: raise ConfigurationError('EVIDENCE_VERSION_CONFLICT',409)
                identity = digest('summary-identity',dict(actor=actor.user_id,run=run_id,store=store,request=request,
                    profile=self.profile,evidence=evidence_digest,**versions(self.profile)))
                claimed = SummaryGeneration(generation_id=uuid4(),run_id=run_id,store_id=store,actor_id=actor.user_id,
                    identity_digest=identity,request=request,profile=self.profile,evidence_digest=evidence_digest,
                    process=current_process(),claim_token=uuid4(),created_at=self.clock(),finished_at=None,
                    status='running',result=None,error_code=None)
                repo = SummaryRepository(session)
                receipt, inserted = repo.accept(claimed,kd,fingerprint)
                if receipt.request_digest != fingerprint: raise ConfigurationError('IDEMPOTENCY_KEY_REUSED',409)
                if inserted and receipt.generation_id!=claimed.generation_id:raise _ReceiptReplay()
                if inserted and repo.running_count(store)>20:raise ConfigurationError('GENERATION_LIMIT_EXCEEDED',429)
                ident = receipt.generation_id
                session.info['summary_accept']=True
                session.commit()
        except _ReceiptReplay:
            return self.create(token,run_id,request,key,csrf)
        except SQLAlchemyError as primary:
            if claimed is None or not _is_uncertain_commit(primary): raise AuthError('SERVICE_UNAVAILABLE',503) from primary
            with auth_session(self.engine) as session:
                actor,store = self._authority(session,token,run_id,csrf)
                repo=SummaryRepository(session)
                receipt=repo.receipt(actor.user_id,store,run_id,kd)
                if receipt is None or receipt.request_digest!=fingerprint: raise AuthError('SERVICE_UNAVAILABLE',503) from primary
                actual=decode_summary(repo.get(store,run_id,receipt.generation_id))
                inserted=actual.generation_id==claimed.generation_id
                if inserted and canonical_bytes(actual)!=canonical_bytes(claimed): raise AuthError('SERVICE_UNAVAILABLE',503) from primary
                ident=actual.generation_id
                session.commit()
        if not inserted:
            existing = self.read(token,run_id,ident)
            if existing.status == 'running': raise ConfigurationError('GENERATION_IN_PROGRESS',409)
            return existing
        try:
            profile,provider=claimed.profile,self.provider
            narrative_mode = profile.version == 'summary_profile/2'
            renderer = render_narrative if narrative_mode else render_summary
            fallback_diagnostics = SummaryDiagnostics(disposition='FALLBACK',reason='MODEL_DISABLED',requested_model=None)
            answer = renderer(evidence,request,fallback_diagnostics)
            if profile.enabled:
                try:
                    payload = payload_for(evidence,request,answer,profile)
                    # Payload selection may take time. Repeat current rights at
                    # dispatch, then release the connection before any network.
                    with auth_session(self.engine) as session:
                        self._authority(session,token,run_id,csrf)
                        session.commit()
                    presented = provider.present(payload,profile)  # No Session or transaction alive here.
                    expression = SummaryExpression.model_validate(presented.expression.model_dump()) if presented.expression else DEFAULT_EXPRESSION
                    diagnostics = SummaryDiagnostics.model_validate(presented.diagnostics.model_dump())
                    if diagnostics.disposition == 'ACCEPTED' and not (presented.narrative if narrative_mode else presented.expression):
                        raise ValueError('Missing material presentation')
                    if diagnostics.requested_model != profile.model or diagnostics.resolved_model not in (None,profile.model):
                        raise ValueError('Provider model identity differs from accepted profile')
                    if profile.providers and diagnostics.resolved_provider is not None and diagnostics.resolved_provider not in profile.providers:
                        raise ValueError('Provider route differs from accepted profile')
                    if narrative_mode:
                        diagnostics = diagnostics_v2(diagnostics)
                        if diagnostics.disposition == 'ACCEPTED':
                            narrative = SummaryNarrative.model_validate(presented.narrative.model_dump())
                            try:
                                answer = render_narrative(evidence,request,diagnostics,narrative)
                            except ValueError:
                                diagnostics = diagnostics.model_copy(update={'disposition':'FALLBACK','reason':'GROUNDING_REJECTED'})
                except (ValueError,ValidationError) as error:
                    diagnostics = SummaryDiagnostics(disposition='FALLBACK',reason='INPUT_LIMIT' if str(error)=='INPUT_LIMIT' else 'SCHEMA_REJECTED',requested_model=profile.model)
                    expression = DEFAULT_EXPRESSION
                except (OSError,TimeoutError):
                    diagnostics = SummaryDiagnostics(disposition='FALLBACK',reason='PROVIDER_UNAVAILABLE',requested_model=profile.model)
                    expression = DEFAULT_EXPRESSION
                if not narrative_mode or diagnostics.disposition != 'ACCEPTED':
                    answer = renderer(evidence,request,diagnostics,expression) if not narrative_mode else renderer(evidence,request,diagnostics)
            self._publish(claimed,answer,token=token,csrf=csrf)
        except AuthError as primary:
            try: self._publish(claimed,error='AUTHORITY_CHANGED')
            except Exception as cleanup: primary.add_note('Summary failure publication failed: '+type(cleanup).__name__)
            raise
        except Exception as primary:
            # Technical failures are never converted into a business success.
            # An uncertain terminal commit is reconciled by replay/read below.
            try:
                with auth_session(self.engine) as session:
                    row = SummaryRepository(session).get(store,run_id,claimed.generation_id)
                    actual = decode_summary(row)
            except Exception as secondary:
                primary.add_note('Summary reconciliation failed: '+type(secondary).__name__)
                if isinstance(primary,SQLAlchemyError): raise AuthError('SERVICE_UNAVAILABLE',503) from primary
                raise primary
            if not (isinstance(primary,SQLAlchemyError) and _is_uncertain_commit(primary) and
                    actual.status=='completed' and actual.claim_token==claimed.claim_token and
                    canonical_bytes(actual.result)==canonical_bytes(answer)):
                if actual.status == 'running':
                    try:self._publish(claimed,error='EXECUTION_ERROR')
                    except Exception as cleanup:primary.add_note('Summary failure publication failed: '+type(cleanup).__name__)
                if isinstance(primary,SQLAlchemyError):raise AuthError('SERVICE_UNAVAILABLE',503) from primary
                raise
        return self.read(token,run_id,claimed.generation_id)
