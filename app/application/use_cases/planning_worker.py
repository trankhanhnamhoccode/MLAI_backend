"""One bounded local Run execution. Claim/publication use current auth fences."""
import threading
from time import perf_counter
from sqlalchemy.exc import SQLAlchemyError
from app.application.contracts.auth import AuthError
from app.application.contracts.planning_run import PlanningPersistenceError
from app.application.contracts.planning_public_evidence import PublicPlanningExecution
from app.application.decision_snapshot_source import OperationalDataError
from app.application.use_cases.forecast_execution import ForecastExecutionError
from app.application.forecast_serialization import RetainedInputError
from app.infrastructure.storage.forecast_artifacts import ArtifactError
from app.infrastructure.forecast_model import ModelBoundaryError
from app.application.use_cases.planning_run import PlanningRunUseCases,decode_row
from app.application.use_cases.planning_public import RUN_PERMISSIONS
from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.database.planning_capture import PostgresPlanningCapture
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from app.infrastructure.planning_process import liveness
from app.repositories.auth import AuthRepository
from app.repositories.planning import PlanningRepository


class PlanningExecution:
    def __init__(self,auth,forecast,*,search_factory=NativeProductSearch,capture=None):
        self.auth,self.engine,self.forecast=auth,auth.engine,forecast
        self.clock=auth.clock
        self.runs=PlanningRunUseCases(self.engine,clock=self.clock)
        self.capture=capture or PostgresPlanningCapture(self.engine,self.clock)
        self.search_factory=search_factory
        self._execution=threading.Lock()
        self._recovery_after=None

    def authority(self,s,record):
        repo=AuthRepository(s)
        user=repo.lock_user(record.actor_id)
        session=repo.lock_session(record.public_acceptance.session_digest)
        account=repo.account(record.actor_id)
        # A logout closes the browser session, not the accepted intent. Execution
        # rechecks the accepted actor's current account/membership/grants under
        # the commit fence. Credential reset/deactivation still blocks publication.
        if not user or not user.active or not session or session.user_id!=record.actor_id or not account or not account.credential_ready or session.credential_revision!=account.credential_revision or account.verified_email!=user.email:
            raise AuthError('UNAUTHENTICATED',401)
        store=repo.lock_store(record.store_id)
        member=repo.lock_membership(record.store_id,record.actor_id)
        if not store or not store.active or not member or not member.active:raise AuthError('PERMISSION_DENIED')
        _,permissions=self.auth._summary(s,store,member)
        if not set(RUN_PERMISSIONS)<=set(permissions):raise AuthError('PERMISSION_DENIED')

    def run_one(self):
        if not self._execution.acquire(False):return None
        try:
            with auth_session(self.engine) as s:
                row=PlanningRepository(s).next_public_queued()
                record=decode_row(row) if row else None
            if record is None:return None
            return self.execute(record)
        finally:self._execution.release()

    def execute(self,record):
        fenced=PlanningRunUseCases(self.engine,clock=self.clock,transition_fence=lambda s:self.authority(s,record))
        try:claimed=fenced.claim(record.store_id,record.run_id)
        except PlanningPersistenceError as error:
            if error.code=='NOT_QUEUED':return None
            # Denied queued jobs still get a durable attempt identity and sanitized
            # failure, without touching sources/forecast or publishing business facts.
            if isinstance(error.__cause__,AuthError):
                try:claimed=self.runs.claim(record.store_id,record.run_id)
                except PlanningPersistenceError as race:
                    if race.code=='NOT_QUEUED':return None
                    raise
                return self.runs.fail(record.store_id,record.run_id,claimed.claim,code=error.__cause__.code)
            raise
        started=perf_counter()
        result=None
        def metrics():
            elapsed=perf_counter()-started
            return PublicPlanningExecution(elapsed_seconds=elapsed,stage_overrun_seconds=max(0,elapsed-180),
                engine_seconds=result.timing.engine_seconds if result else None,
                engine_overrun_seconds=result.timing.engine_overrun_seconds if result else None)
        try:
            captured=None
            for attempt in range(3):
                self._deadline(started,record)
                # Short current authority transaction; never held during forecast.
                with auth_session(self.engine) as s:self.authority(s,claimed)
                try:
                    preparation=self.forecast.prepare(record.store_id,record.request.forecast_start_date,accepted_serving=record.public_acceptance.serving)
                except AuthError as error:
                    if error.code!='NO_COMPUTABLE_PRODUCTS':raise
                    preparation=served=None
                else:served=self.forecast.serve(preparation)
                captured=self.capture.read(claimed,served,preparation,perf_counter()-started)
                if captured.source_matches:break
            else:raise AuthError('INPUT_CHANGED_DURING_CAPTURE',409)
            self._deadline(started,record)
            if any(p.code in ('SOURCE_FAILURE_SCOPE_UNKNOWN','CROSS_STORE_SOURCE','TERM_SCOPE_UNKNOWN','PRODUCT_SCOPE_UNKNOWN','INGREDIENT_SCOPE_UNKNOWN','RECIPE_SCOPE_UNKNOWN') for p in captured.capture.problems):
                raise AuthError('SOURCE_FAILURE_SCOPE_UNKNOWN',503)
            retained=fenced.retain(record.store_id,record.run_id,claimed.claim,captured.declarations,captured.capture,public_capture=captured.evidence)
            # All source/authority/capture/retention Sessions are closed here.
            result=execute_captured_pipeline_v2(retained.capture,self.search_factory,perf_counter()-started)
            self._deadline(started,record)
            return fenced.finalize(record.store_id,record.run_id,claimed.claim,result,public_execution=metrics())
        except Exception as error:
            code=error.code if isinstance(error,AuthError) else 'EXECUTION_ERROR'
            if isinstance(error,SQLAlchemyError):code='DATA_SOURCE_UNAVAILABLE'
            elif isinstance(error,OperationalDataError):code='SOURCE_FAILURE_SCOPE_UNKNOWN'
            elif isinstance(error,ForecastExecutionError):code='FORECAST_EXECUTION_FAILED'
            elif isinstance(error,(ArtifactError,ModelBoundaryError)):code='MODEL_ARTIFACT_INVALID'
            elif isinstance(error,RetainedInputError):code='RESULT_INTEGRITY_UNAVAILABLE'
            if isinstance(error,PlanningPersistenceError) and isinstance(error.__cause__,AuthError):code=error.__cause__.code
            actual=self.runs.read(record.store_id,record.run_id).record
            if actual.status in ('completed','failed'):
                # Programming failures after acknowledged publication remain errors.
                raise
            return self.runs.fail(record.store_id,record.run_id,claimed.claim,code=code,public_execution=metrics())

    @staticmethod
    def _deadline(started,record):
        if perf_counter()-started>record.public_acceptance.overall_stage_seconds:
            raise AuthError('EXECUTION_DEADLINE_EXCEEDED',503)

    def recover(self):
        with auth_session(self.engine) as s:
            rows=PlanningRepository(s).public_running_page(self._recovery_after)
            self._recovery_after=(rows[-1].accepted_at,rows[-1].id) if rows else None
            candidates=tuple((row.store_id,row.id,decode_row(row).claim.process) for row in rows)
        recovered=[]
        for store,run,process in candidates:
            if liveness(process)=='DEAD':
                try:recovered.append(self.runs.recover_interrupted(store,run))
                except PlanningPersistenceError as race:
                    if race.code!='NOT_RUNNING':raise
        return tuple(recovered)
