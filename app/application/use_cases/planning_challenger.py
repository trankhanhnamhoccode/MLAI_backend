"""Explicit test composition over real serving, ForecastRun and worker boundaries.

Never installed by application startup. No production/research admission, fallback,
training, endpoint calibration or changes to the host strategy/selector.
"""
from dataclasses import dataclass
from app.application.contracts.auth import AuthError
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_challenger import ChallengerInput, ChallengerError, ChallengerEvidence
from app.application.contracts.planning_challenger import ChallengerTestPin,canonical_matches as raw_matches
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.forecast_execution import ForecastEngineResult
from app.application.contracts.model_serving import ForecastIdentity
from app.application.forecast_preparation import prepare_observations
from app.application.forecast_serialization import restore_prepared, serialize_prepared, RetainedInputError
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.forecast_challenger_validation import validate_output
from app.application.import_identity import content_digest
from app.application.use_cases.forecast_serving import ForecastServing, ForecastPreparation, source_digest
from app.application.use_cases.forecast_trained_execution import TrainedForecastExecutionUseCases, ExpectedCompletion
from app.application.use_cases.forecast_execution import _commit, _now
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.database.forecast_execution_session import _execution_session
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.models import ForecastRun, ForecastRunInput, ForecastExecutionMetadata
from app.repositories.forecast import ForecastRepository
from app.repositories.forecast_input import ForecastInputRepository
from app.repositories.forecast_execution_metadata import ForecastExecutionMetadataRepository
from app.repositories.readiness import load_readiness
from app.infrastructure.planning_challenger_identity import integration_digest
from app.application._validation import require_store, require_product


def safe_failure(error):
    if error.code=='PINNED_ARTIFACT_MISSING':return AuthError('CHALLENGER_ARTIFACT_MISSING',503)
    codes={'UNSUPPORTED':'CHALLENGER_DATA_BLOCKED','DATA_BLOCKED':'CHALLENGER_DATA_BLOCKED',
        'DEPENDENCY_MISMATCH':'CHALLENGER_RUNTIME_UNAVAILABLE',
        'ARTIFACT_CORRUPTION':'CHALLENGER_ARTIFACT_CORRUPT','TECHNICAL_FAILURE':'CHALLENGER_TECHNICAL_FAILURE'}
    return AuthError(codes[error.category.value],503)


@dataclass(frozen=True)
class TestPreparation(ForecastPreparation):
    pin: ChallengerTestPin


@dataclass(frozen=True)
class TestChoice:
    pin: ChallengerTestPin
    details: ExecutionDetails


class ChallengerTestExecution(TrainedForecastExecutionUseCases):
    def __init__(self,engine,service):
        super().__init__(engine,None)
        self.service=service

    def _retained(self,session,reference):
        run=ForecastRepository(session).get_forecast_run(reference.store_id,reference.run_id)
        row=ForecastInputRepository(session).get_input(reference.store_id,reference.run_id)
        if run is None or row is None:raise RetainedInputError('RETAINED_INPUT_UNAVAILABLE')
        prepared=restore_prepared(row.prepared_json,row.serialization_version,row.digest)
        details=self._details(session,reference)
        if (prepared.schema_version!=3 or run.model_type!='forecast_engine_challenger'
            or details.selection_reason!='CHALLENGER_TEST_SELECTED' or run.artifact_key!=details.candidate_artifact_identity
            or run.training_start_date!=prepared.request.history_start_date or run.training_end_date!=prepared.request.cutoff_date
            or run.forecast_start_date!=prepared.forecast_dates[0] or run.forecast_end_date!=prepared.forecast_dates[-1]
            or (run.status=='COMPLETED' and run.input_fingerprint!=row.digest)):
            raise RetainedInputError('RETAINED_RUN_MISMATCH')
        if run.status=='COMPLETED':
            evidence=details.challenger_evidence
            if evidence is None or not raw_matches(prepared,evidence.input):raise RetainedInputError('CHALLENGER_EVIDENCE_MISMATCH')
            validate_output(evidence.input,evidence.output)
            output=evidence.output
            if (output.input_digest!=challenger_digest('input',evidence.input)
                or output.runtime!=output.artifact.runtime
                or challenger_digest('artifact',output.artifact)!=evidence.input.artifact_identity
                or evidence.cache_identity!=challenger_digest('cache',{'input':evidence.input,'runtime':output.runtime})):
                raise RetainedInputError('CHALLENGER_EVIDENCE_MISMATCH')
            if (output.forecast.model_version!=run.model_version or output.forecast.artifact_identity!=run.artifact_key):
                raise RetainedInputError('CHALLENGER_EVIDENCE_MISMATCH')
            from app.application.use_cases.forecast import ForecastUseCases
            actual=ForecastUseCases(session).get(reference)
            projected=ForecastEngineResult(model_type=actual.model_type,model_version=actual.model_version,
                artifact_identity=actual.artifact_key,warnings=details.warnings,predictions=tuple(
                    p.model_dump(include={'product_id','forecast_date','p25','p50','p75'}) for p in actual.predictions))
            if projected!=output.forecast or actual.metrics_json is not None:
                raise RetainedInputError('CHALLENGER_CANONICAL_OUTPUT_MISMATCH')
        return prepared

    def _start_selected(self,reference,prepared,encoded,choice):
        r=prepared.request;manifest=choice.pin.artifact
        with _execution_session(self.engine) as session:
            session.begin();require_store(session,r.store_id)
            for pid in r.product_ids:require_product(session,r.store_id,pid)
            ForecastRepository(session).add_forecast_run(r.store_id,ForecastRun(id=reference.run_id,store_id=r.store_id,
                status='RUNNING',started_at=_now(),training_start_date=r.history_start_date,training_end_date=r.cutoff_date,
                forecast_start_date=prepared.forecast_dates[0],forecast_end_date=prepared.forecast_dates[-1],
                model_type=manifest.model_type,model_version=manifest.model_version,artifact_key=choice.pin.input.artifact_identity))
            session.flush()
            import json
            ForecastInputRepository(session).add_input(r.store_id,ForecastRunInput(forecast_run_id=reference.run_id,
                store_id=r.store_id,prepared_json=json.loads(encoded.canonical_json),serialization_version=encoded.serialization_version,digest=encoded.digest))
            ForecastExecutionMetadataRepository(session).add(r.store_id,ForecastExecutionMetadata(forecast_run_id=reference.run_id,
                store_id=r.store_id,details_json=choice.details.model_dump(mode='json')))
            session.flush();_commit(session)

    def _compute(self,prepared,choice):
        if not raw_matches(prepared,choice.pin.input):raise RetainedInputError('CHALLENGER_CAPTURE_CHANGED')
        if choice.pin.integration_code_digest!=integration_digest():raise RetainedInputError('CHALLENGER_INTEGRATION_CHANGED')
        value,runtime,bundle,key=self.service._admit(choice.pin.input)
        if bundle.manifest!=choice.pin.artifact or runtime!=choice.pin.runtime:
            raise RetainedInputError('CHALLENGER_ACCEPTANCE_PIN_CHANGED')
        output=self.service._compute(value,bundle,runtime)
        evidence=ChallengerEvidence(cache_identity=challenger_digest('cache',{'input':value,'runtime':runtime}),input=value,output=output)
        details=ExecutionDetails(**(choice.details.model_dump()|dict(challenger_evidence=evidence,warnings=output.forecast.warnings)))
        return ExpectedCompletion(output.forecast,details)

    def replay(self,reference):
        # F4 replay is a retained read: no artifact/native/solver/live-source access.
        with _execution_session(self.engine) as session:
            self._retained(session,reference)
            evidence=self._details(session,reference).challenger_evidence
            if evidence is None:raise RetainedInputError('CHALLENGER_REPLAY_NOT_COMPLETED')
            return evidence.output.forecast

    def replay_persisted(self,reference):
        raise RetainedInputError('F4_REPLAY_IS_READ_ONLY')


class ChallengerPlanningServing(ForecastServing):
    def __init__(self,engine,artifacts,*,settings,storage: ChallengerStorage,declaration: ChallengerInput,enabled=False):
        super().__init__(engine,artifacts)
        self.declaration=ChallengerInput.model_validate(declaration)
        self.service=ForecastChallenger(storage,enabled=enabled)
        if not enabled:raise ValueError('Explicit test opt-in required')
        from scripts.dev import validate_reset_target
        from sqlalchemy.engine import make_url
        validate_reset_target(settings)
        url=make_url(settings.database_url)
        if (settings.environment!='test' or url.database!='shelfcash_challenger_test'
                or engine.url!=url):raise ValueError('F4 restricted to the dedicated challenger test target')
        from sqlalchemy import text
        with engine.connect() as connection:
            if connection.execute(text('SELECT current_database(),current_user')).one()!=('shelfcash_challenger_test','shelfcash_challenger_tester'):
                raise ValueError('Connected challenger identity mismatch')
            if connection.scalar(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user')):
                raise ValueError('Challenger runtime role must be limited')
        self.execution=ChallengerTestExecution(engine,self.service)

    def acceptance_pin(self,facts,store,start):
        prepared=prepare_observations(facts,store,start,native_challenger=True)
        if not raw_matches(prepared,self.declaration):raise AuthError('CHALLENGER_DATA_BLOCKED',409)
        try:
            value,runtime,bundle,key=self.service._admit(self.declaration)
            from app.application.forecast_challenger_validation import require
            from app.application.contracts.forecast_challenger import ChallengerFailure
            require(bundle.manifest.purpose=='synthetic_correctness' and bundle.manifest.holdout_status=='SYNTHETIC_ONLY'
                and bundle.manifest.promotion_status=='trained_candidate' and bundle.manifest.production_available_at is None,
                'TEST_ONLY_SYNTHETIC_ARTIFACT_REQUIRED',ChallengerFailure.DATA_BLOCKED)
            return ChallengerTestPin(input=value,artifact=bundle.manifest,runtime=runtime,integration_code_digest=integration_digest())
        except ChallengerError as error:raise safe_failure(error) from error

    def prepare(self,store,start,product_ids=None,*,accepted_serving=None,challenger_test=None):
        if challenger_test is None:raise AuthError('CHALLENGER_ACCEPTANCE_PIN_MISSING',409)
        pin=ChallengerTestPin.model_validate(challenger_test)
        if pin.integration_code_digest!=integration_digest():raise RetainedInputError('CHALLENGER_INTEGRATION_CHANGED')
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as session:
                facts=load_readiness(session,store)
                prepared=prepare_observations(facts,store,start,product_ids,native_challenger=True)
                if not raw_matches(prepared,pin.input):raise AuthError('CHALLENGER_DATA_BLOCKED',409)
                return TestPreparation(prepared,accepted_serving,source_digest(facts,prepared),pin)

    def choice(self,prepared,serving):
        raise RuntimeError('Use accepted F4 pin, never live serving policy')

    def identity(self,preparation,choice):
        pin=choice.pin;m=pin.artifact
        return ForecastIdentity(prepared_digest=serialize_prepared(preparation.prepared).digest,
            source_digest=preparation.source_digest,serving_version=content_digest(pin.model_dump(mode='json')),
            model_type=m.model_type,model_version=m.model_version,artifact_identity=pin.input.artifact_identity,
            candidate_artifact_identity=pin.input.artifact_identity,selection_reason=choice.details.selection_reason,
            features_version=1,postprocessing_version=1,
            dependency_versions=tuple((p.name,p.version) for p in pin.runtime.dependencies)+(('python',pin.runtime.python),),
            configuration_dependency_versions=preparation.serving.policy.dependency_versions,
            training_start_date=m.training.start,training_end_date=m.training.end)

    def serve(self,preparation):
        from app.application.use_cases.forecast_serving import ServedForecast
        from app.models.model_serving import ForecastServingIdentity
        pin=preparation.pin
        try:
            _,runtime,bundle,key=self.service._admit(pin.input)
            if bundle.manifest!=pin.artifact or runtime!=pin.runtime:raise RetainedInputError('CHALLENGER_ACCEPTANCE_PIN_CHANGED')
            choice=TestChoice(pin,ExecutionDetails(schema_version=2,selection_reason='CHALLENGER_TEST_SELECTED',
                candidate_artifact_identity=pin.input.artifact_identity))
            identity=self.identity(preparation,choice)
            old=self._reuse(preparation,identity)
            if old is not None:return ServedForecast(old,identity,True)
            run=self.execution._run(preparation.prepared,choice)
            with auth_session(self.engine) as session:
                session.add(ForecastServingIdentity(forecast_run_id=run.id,store_id=run.store_id,
                    identity_digest=content_digest(identity.model_dump(mode='json')),identity_json=identity.model_dump(mode='json')))
                session.flush();session.commit()
            return ServedForecast(run,identity,False)
        except ChallengerError as error:raise safe_failure(error) from error
