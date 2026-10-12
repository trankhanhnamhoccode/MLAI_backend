"""Durable internal primitives. No HTTP, auth, scheduler or live replay."""
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4
from collections.abc import Callable
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.application.contracts.planning_setup import PlanningRequest, ResolvedPlanningSetup
from app.application.contracts.planning_run import (
    PlanningRunRecord, PlanningClaim, PlanningRead, PlanningPersistenceError, outcome_mapping,
)
from app.application.contracts.planning_public_evidence import PublicPlanningAudit
from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2, OperationalPipelineResultV2
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations
from app.application.decision_snapshot_source_v2 import DecisionSnapshotSourceV2
from app.application.procurement_solver_v2 import ProductCandidateSearch
from app.application.planning_serialization import canonical_bytes, digest, request_digest, exact_json
from app.application.use_cases.forecast_execution import _is_uncertain_commit
from app.infrastructure.database.planning_session import planning_session, secondary
from app.infrastructure.planning_process import current_process, liveness
from app.repositories.planning import PlanningRepository


def utc_now():
    return datetime.now(timezone.utc)


def decode_row(row):
    if row is None:
        raise PlanningPersistenceError('NOT_FOUND')
    try:
        if row.record_digest != digest('aggregate',row.record_json):
            raise ValueError('Aggregate digest mismatch')
        record = PlanningRunRecord.model_validate(row.record_json)
        for column,field in [('id','run_id'),('actor_id','actor_id'),('store_id','store_id'),
                             ('operation','operation'),('key_digest','key_digest'),
                             ('request_digest','request_digest'),('status','status'),('accepted_at','accepted_at')]:
            if getattr(row,column)!=getattr(record,field):
                raise ValueError('Aggregate relationship mismatch')
        if row.revision < 1 or canonical_bytes(record)!=canonical_bytes(row.record_json):
            raise ValueError('Noncanonical or incompatible aggregate')
        return record
    except (ValueError,TypeError,ValidationError) as error:
        raise PlanningPersistenceError('RESULT_INTEGRITY_UNAVAILABLE',row.id) from error


def _same_acceptance(a,b):
    fields = ('run_id','actor_id','store_id','operation','key_digest','request_digest',
              'request','resolution','accepted_at','storage_version','package_schema_version','public_acceptance')
    return all(canonical_bytes(getattr(a,k))==canonical_bytes(getattr(b,k)) for k in fields)


class PlanningRunUseCases:
    def __init__(self, engine: Engine, *,clock=utc_now,transition_fence=None):
        if not isinstance(engine,Engine):
            raise TypeError('PlanningRun requires an Engine, never a caller Connection/Session')
        self.engine = engine
        self.clock,self.transition_fence=clock,transition_fence

    def read(self, store_id: UUID, run_id: UUID) -> PlanningRead:
        start = perf_counter()
        record = None
        try:
            with planning_session(self.engine) as session:
                record = decode_row(PlanningRepository(session).get(store_id,run_id))
        except PlanningPersistenceError:
            raise
        except Exception as primary:
            raise PlanningPersistenceError('READ_EXECUTION_ERROR',run_id,
                                          record.status if record else 'unknown') from primary
        return PlanningRead(record=record,integrity_validation_seconds=perf_counter()-start)

    def _write(self, store_id, proposed_id, mutation, *, acceptance=False):
        expected = None
        commit_error = None
        try:
            with planning_session(self.engine) as session:
                session.begin()
                expected = mutation(PlanningRepository(session))
                session.flush()
                try:
                    session.commit()
                except Exception as error:
                    commit_error = error
                    raise
        except Exception as primary:
            if isinstance(primary,PlanningPersistenceError) and commit_error is None:
                raise
            actual = None
            try:
                actual = self.read(store_id,expected.run_id if expected else proposed_id).record
            except Exception as reconcile:
                secondary(primary,'fresh reconciliation',reconcile)
            genuine = commit_error is primary and _is_uncertain_commit(primary)
            if genuine and expected is not None and actual is not None and (
                _same_acceptance(expected,actual) if acceptance else canonical_bytes(expected)==canonical_bytes(actual)):
                return actual
            code = 'COMMIT_OUTCOME_UNKNOWN' if genuine else 'EXECUTION_ERROR'
            failure = PlanningPersistenceError(code,actual.run_id if actual else (expected.run_id if expected else proposed_id),
                                              actual.status if actual else 'unknown')
            raise failure from primary
        # Even acknowledged commits return only fresh-session verified aggregates.
        actual = self.read(store_id,expected.run_id).record
        if not (_same_acceptance(expected,actual) if acceptance else canonical_bytes(expected)==canonical_bytes(actual)):
            raise PlanningPersistenceError('DURABLE_VERIFICATION_CONFLICT',expected.run_id,actual.status)
        return actual

    def accept(self, actor_id: UUID, store_id: UUID, key: str, request: PlanningRequest | dict,
               resolution: ResolvedPlanningSetup | Callable[[Session], ResolvedPlanningSetup] | None = None,
               *,authority=None,public_metadata=None) -> PlanningRunRecord:
        """Retry lookup precedes resolution. Optional trusted provider runs in tx.

        A future DB configuration adapter can resolve under this transaction; this
        slice supplies typed config only, with no public consistency/auth promise.
        """
        request = PlanningRequest.model_validate(request)
        actor_id,store_id = UUID(str(actor_id)),UUID(str(store_id))
        if not isinstance(key,str) or not key.strip() or len(key)>256:
            raise ValueError('Internal idempotency key must be 1..256 nonblank characters')
        kd = digest('key',dict(actor_id=actor_id,store_id=store_id,operation='C02',key=key))
        rd = request_digest(request)
        existing = None
        try:
            with planning_session(self.engine) as session:
                if authority is not None:authority(session);session.flush()
                row = PlanningRepository(session).by_key(actor_id,store_id,kd)
                if row is not None:
                    existing = decode_row(row)
                    if existing.request_digest!=rd:
                        raise PlanningPersistenceError('IDEMPOTENCY_KEY_REUSED',existing.run_id,existing.status)
                    if authority is not None:session.commit()
                    return existing
        except PlanningPersistenceError:
            raise
        except Exception as primary:
            raise PlanningPersistenceError('ACCEPTANCE_LOOKUP_ERROR',existing.run_id if existing else None,
                                          existing.status if existing else 'unknown') from primary
        run_id = uuid4()
        def mutation(repo):
            if authority is not None:authority(repo.session);repo.session.flush()
            existing = repo.by_key(actor_id,store_id,kd)
            if existing is not None:
                record = decode_row(existing)
            else:
                owned_transaction = repo.session.get_transaction()
                supplied = resolution(repo.session) if callable(resolution) else resolution
                if repo.session.get_transaction() is not owned_transaction or not owned_transaction.is_active:
                    raise ValueError('Resolution provider changed acceptance transaction ownership')
                if repo.session.new or repo.session.dirty or repo.session.deleted:
                    raise ValueError('Resolution provider must not leave pending writes')
                if supplied is None:
                    raise PlanningPersistenceError('RESOLUTION_REQUIRED',run_id)
                supplied = ResolvedPlanningSetup.model_validate(supplied)
                accepted_at=self.clock()
                public=public_metadata(repo.session,supplied) if public_metadata is not None else None
                candidate = PlanningRunRecord(run_id=run_id,actor_id=actor_id,store_id=store_id,
                    key_digest=kd,request_digest=rd,request=request,resolution=supplied,
                    accepted_at=accepted_at,status='queued',public_acceptance=public,
                    public_audit=(PublicPlanningAudit(action='ACCEPTED',actor_id=actor_id,occurred_at=accepted_at),) if public else None)
                record = decode_row(repo.accept(candidate))
            if record.request_digest!=rd:
                raise PlanningPersistenceError('IDEMPOTENCY_KEY_REUSED',record.run_id,record.status)
            return record
        return self._write(store_id,run_id,mutation,acceptance=True)

    def _transition(self, store_id, run_id, build):
        def mutation(repo):
            if self.transition_fence is not None:self.transition_fence(repo.session)
            row = repo.get(store_id,run_id,lock=True)
            old = decode_row(row)
            new = build(old)
            new = PlanningRunRecord.model_validate(new)
            if canonical_bytes(old)!=canonical_bytes(new):
                repo._replace_locked(row,new)
            return new
        return self._write(store_id,run_id,mutation)

    def _audit(self,old,action,at,outcome=None):
        return (*old.public_audit,PublicPlanningAudit(action=action,actor_id=old.actor_id,occurred_at=at,outcome=outcome)) if old.public_audit is not None else None

    def claim(self, store_id: UUID, run_id: UUID) -> PlanningRunRecord:
        process = current_process()
        def build(old):
            if old.status!='queued':
                raise PlanningPersistenceError('NOT_QUEUED',run_id,old.status)
            now=self.clock()
            return {**old.model_dump(round_trip=True),'status':'running','started_at':now,
                    'claim':PlanningClaim(token=uuid4(),generation=1,process=process),
                    'public_audit':self._audit(old,'CLAIMED',now)}
        return self._transition(store_id,run_id,build)

    @staticmethod
    def _owner(old, claim):
        claim = PlanningClaim.model_validate(claim)
        if claim!=old.claim:
            raise PlanningPersistenceError('STALE_CLAIM',old.run_id,old.status)

    def retain(self, store_id: UUID, run_id: UUID, claim: PlanningClaim,
               declarations: PlanningPipelineDeclarations, capture: DecisionCaptureOutcomeV2,*,public_capture=None) -> PlanningRunRecord:
        capture = DecisionCaptureOutcomeV2.model_validate(capture)
        def build(old):
            self._owner(old,claim)
            if old.status!='running':
                raise PlanningPersistenceError('NOT_RUNNING',run_id,old.status)
            body = {**old.model_dump(round_trip=True),'declarations':declarations,'capture':capture,
                    'input_digest':digest('capture',capture),'public_capture':public_capture,
                    'public_audit':self._audit(old,'CAPTURE_RETAINED',self.clock())}
            if old.capture is not None:
                body['public_audit']=old.public_audit
            new = PlanningRunRecord.model_validate(body)
            if old.capture is not None and canonical_bytes(new)!=canonical_bytes(old):
                raise PlanningPersistenceError('INPUT_ALREADY_RETAINED',run_id,old.status)
            return new
        return self._transition(store_id,run_id,build)

    def finalize(self, store_id: UUID, run_id: UUID, claim: PlanningClaim,
                 result: OperationalPipelineResultV2,*,public_execution=None) -> PlanningRunRecord:
        result = OperationalPipelineResultV2.model_validate(result)
        status,outcome = outcome_mapping(result)
        def build(old):
            self._owner(old,claim)
            if old.status in {'completed','failed'}:
                if old.result is None or canonical_bytes(old.result)!=canonical_bytes(result):
                    raise PlanningPersistenceError('TERMINAL_CONFLICT',run_id,old.status)
                return old
            if old.status!='running':
                raise PlanningPersistenceError('NOT_RUNNING',run_id,old.status)
            now=self.clock()
            return {**old.model_dump(round_trip=True),'status':status,'outcome':outcome,'result':result,
                    'result_digest':digest('result',result),
                    'finished_at':now,'public_execution':public_execution,'public_audit':self._audit(old,'COMPLETED' if status=='completed' else 'FAILED',now,outcome),
                    'error_code':'PIPELINE_EXECUTION_ERROR' if status=='failed' else None,
                    'error_summary':'Internal pipeline execution failed.' if status=='failed' else None}
        return self._transition(store_id,run_id,build)

    def fail(self, store_id: UUID, run_id: UUID, claim: PlanningClaim, *, code: str = 'EXECUTION_ERROR',public_execution=None) -> PlanningRunRecord:
        if code not in {'EXECUTION_ERROR','PROCESS_INTERRUPTED','PERMISSION_DENIED','UNAUTHENTICATED',
                        'MODEL_CONFIGURATION_UNKNOWN','MODEL_ARTIFACT_INVALID','FORECAST_EXECUTION_FAILED',
                        'DATA_SOURCE_UNAVAILABLE','INPUT_CHANGED_DURING_CAPTURE','EXECUTION_DEADLINE_EXCEEDED',
                        'RESULT_INTEGRITY_UNAVAILABLE','SOURCE_FAILURE_SCOPE_UNKNOWN'}:
            raise ValueError('Unsupported sanitized technical error')
        def build(old):
            self._owner(old,claim)
            if old.status=='failed' and old.result is None and old.error_code==code:
                return old
            if old.status!='running':
                raise PlanningPersistenceError('TERMINAL_CONFLICT',run_id,old.status)
            now=self.clock()
            return {**old.model_dump(round_trip=True),'status':'failed','outcome':'execution_error',
                    'finished_at':now,'public_execution':public_execution,'public_audit':self._audit(old,'FAILED',now,code),
                    'error_code':code,'error_summary':'Internal execution interrupted.'
                    if code=='PROCESS_INTERRUPTED' else 'Internal execution failed.'}
        return self._transition(store_id,run_id,build)

    def recover_interrupted(self, store_id: UUID, run_id: UUID) -> PlanningRunRecord:
        def build(old):
            if old.status!='running':
                raise PlanningPersistenceError('NOT_RUNNING',run_id,old.status)
            state = liveness(old.claim.process)
            if state!='DEAD':
                raise PlanningPersistenceError('OWNER_'+state,run_id,old.status)
            now=self.clock()
            return {**old.model_dump(round_trip=True),'status':'failed','outcome':'execution_error',
                    'finished_at':now,'public_audit':self._audit(old,'RECOVERED',now,'PROCESS_INTERRUPTED'),
                    'error_code':'PROCESS_INTERRUPTED',
                    'error_summary':'Verified owner process interrupted.'}
        return self._transition(store_id,run_id,build)

    def execute(self, store_id: UUID, run_id: UUID, declarations: PlanningPipelineDeclarations,
                source: DecisionSnapshotSourceV2, search_factory: Callable[..., ProductCandidateSearch],
                clock: Callable[[],datetime] = utc_now) -> PlanningRunRecord:
        """Synchronous one-shot composition, not a worker or automatic retry."""
        from app.application.use_cases.planning_pipeline import prepare_planning_pipeline
        from app.application.use_cases.decision_capture_v2 import capture_decision_v2
        from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
        claimed = self.claim(store_id,run_id)
        try:
            capture_start = perf_counter()
            capture = capture_decision_v2(prepare_planning_pipeline(claimed.resolution,declarations),source,clock)
            capture_seconds = perf_counter()-capture_start
            retained = self.retain(store_id,run_id,claimed.claim,declarations,capture)
            result = execute_captured_pipeline_v2(retained.capture,search_factory,capture_seconds)
            return self.finalize(store_id,run_id,claimed.claim,result)
        except Exception as primary:
            try:
                actual = self.read(store_id,run_id).record
                if actual.status=='running':
                    self.fail(store_id,run_id,claimed.claim)
                actual = self.read(store_id,run_id).record
            except Exception as recording:
                secondary(primary,'failure recording',recording)
                try:
                    observed = self.read(store_id,run_id).record
                except Exception as verification:
                    secondary(primary,'failure outcome verification',verification)
                    raise PlanningPersistenceError('FAILURE_RECORDING_UNVERIFIED',run_id) from primary
                raise PlanningPersistenceError('FAILURE_RECORDING_ERROR',run_id,observed.status) from primary
            # Programming error after durable completion remains an error; do not
            # overwrite completed with failed or return verified completion as success.
            raise PlanningPersistenceError('EXECUTION_ERROR',run_id,actual.status) from primary
