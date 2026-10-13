"""S4.8 internal prepare/reuse seam; never a public Run or solver entrypoint."""
from dataclasses import dataclass
from datetime import date
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from app.application.contracts.auth import AuthError
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastEngineResult,validate_engine_result,PreparedForecastInput
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.model_serving import ForecastIdentity,ServingRecord
from app.application.forecast_serialization import serialize_prepared,RetainedInputError
from app.application.forecast_preparation import prepare_observations
from app.application.import_identity import content_digest
from app.application.use_cases.forecast_trained_execution import TrainedForecastExecutionUseCases,ExecutionChoice
from app.application.use_cases.forecast import ForecastUseCases
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.storage.forecast_artifacts import ArtifactError
from app.infrastructure.forecast_model import ModelBoundaryError,training_rows
from app.repositories.readiness import load_readiness
from app.repositories.model_serving import reuse_candidates
from app.models.model_serving import ForecastServingIdentity
from app.domain.forecasting.baseline import BASELINE_MODEL_TYPE,BASELINE_MODEL_VERSION
from app.application.contracts.forecast import ForecastRunResult
from app.repositories.readiness import ReadinessFacts


@dataclass(frozen=True)
class ForecastPreparation:
    prepared: PreparedForecastInput
    serving: ServingRecord
    source_digest: str


@dataclass(frozen=True)
class ServedForecast:
    run: ForecastRunResult
    identity: ForecastIdentity
    reused: bool


@dataclass(frozen=True)
class CapturedOperationalPreparation:
    facts: ReadinessFacts
    prepared_digest: str
    source_digest: str
    serving_version: str | None


def source_digest(facts,prepared):
    ids=set(map(str,prepared.request.product_ids))
    # Only forecast-bearing fields; retail price, recipe, stock, budget and supplier
    # changes must never invalidate a forecast. Sales row revisions cover ABA.
    return content_digest(dict(products=sorted((r['id'],r['selling_unit']) for r in facts.snapshot['products'] if r['active']),
        sales=[r for r in facts.snapshot['sales_daily'] if r['product_id'] in ids and r['sales_date']<=str(prepared.request.cutoff_date)],
        timezone=prepared.timezone))


class ForecastServing:
    def __init__(self,engine,artifacts):
        self.engine=engine
        self.execution=TrainedForecastExecutionUseCases(engine,artifacts)

    def prepare(self,store,start,product_ids=None,*,accepted_serving=None):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                facts=load_readiness(s,store)
                serving=accepted_serving or facts.serving
                if serving is None:raise AuthError('MODEL_CONFIGURATION_UNKNOWN',409)
                prepared=prepare_observations(facts,store,start,product_ids)
                return ForecastPreparation(prepared,serving,source_digest(facts,prepared))

    def choice(self,prepared,serving):
        policy=serving.policy
        if policy.mode=='BASELINE':
            import platform
            if dict(policy.dependency_versions)!={'baseline':'1','serialization':'1','python':platform.python_version()}:
                raise ModelBoundaryError('SERVING_DEPENDENCY_INCOMPATIBLE')
            return ExecutionChoice(None,ExecutionDetails(selection_reason='BASELINE_SELECTED'))
        choice=self.execution._choose(prepared,policy.artifact_identity)
        if choice.artifact is not None and any(r.status!='READY' for r in training_rows(prepared).readiness):
            from app.application.use_cases.forecast_trained_execution import _fallback_details
            return ExecutionChoice(None,_fallback_details('NOT_READY_HISTORY',policy.artifact_identity))
        return choice

    def assess(self,prepared,serving):
        try:self.choice(prepared,serving)
        except (ArtifactError,ModelBoundaryError):return 'MODEL_ARTIFACT_INVALID'
        return None

    @staticmethod
    def identity(preparation,choice):
        import platform
        p=preparation.serving.policy
        actual_dependencies=(('lightgbm',choice.artifact.manifest.lightgbm_version),('numpy',choice.artifact.manifest.numpy_version),
            ('scipy',choice.artifact.manifest.scipy_version),('python',platform.python_version())) if choice.artifact else (
            ('baseline','1'),('serialization','1'),('python',platform.python_version()))
        training=choice.artifact.manifest.training_input.request if choice.artifact else preparation.prepared.request
        return ForecastIdentity(prepared_digest=serialize_prepared(preparation.prepared).digest,source_digest=preparation.source_digest,
            serving_version=preparation.serving.version,model_type=choice.artifact.manifest.model_type if choice.artifact else BASELINE_MODEL_TYPE,
            model_version=choice.artifact.manifest.model_version if choice.artifact else BASELINE_MODEL_VERSION,
            artifact_identity=choice.artifact.identity if choice.artifact else None,
            candidate_artifact_identity=p.artifact_identity,selection_reason=choice.details.selection_reason,
            features_version=p.features_version,postprocessing_version=p.postprocessing_version,dependency_versions=actual_dependencies,
            configuration_dependency_versions=p.dependency_versions,training_start_date=training.history_start_date,training_end_date=training.cutoff_date)

    def _reuse(self,preparation,identity):
        digest=content_digest(identity.model_dump(mode='json'))
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                for row in reuse_candidates(s,preparation.prepared.request.store_id,digest):
                    if row.identity_json!=identity.model_dump(mode='json'):
                        raise RetainedInputError('FORECAST_SERVING_IDENTITY_CORRUPT')
                    reference=RunReferenceInput(store_id=row.store_id,run_id=row.forecast_run_id)
                    prepared=self.execution._retained(s,reference)
                    run=ForecastUseCases(s).get(reference)
                    details=self.execution._details(s,reference)
                    if run.status!='COMPLETED':continue
                    if serialize_prepared(prepared).digest!=identity.prepared_digest or (run.model_type,run.model_version,run.artifact_key)!=(identity.model_type,identity.model_version,identity.artifact_identity) or details.selection_reason!=identity.selection_reason or details.candidate_artifact_identity!=identity.candidate_artifact_identity:
                        raise RetainedInputError('FORECAST_SERVING_IDENTITY_CORRUPT')
                    result=ForecastEngineResult(model_type=run.model_type,model_version=run.model_version,artifact_identity=run.artifact_key,
                        warnings=details.warnings,predictions=tuple(p.model_dump(include={'product_id','forecast_date','p25','p50','p75'}) for p in run.predictions))
                    validate_engine_result(prepared,result)
                    return run
        return None

    def serve(self,preparation):
        # preparation transaction is already closed; artifact work/forecast execution
        # never keeps it open. Existing S2 owned lifecycle handles actual execution.
        choice=self.choice(preparation.prepared,preparation.serving)
        identity=self.identity(preparation,choice)
        old=self._reuse(preparation,identity)
        if old is not None:return ServedForecast(old,identity,True)
        run=self.execution._run(preparation.prepared,choice)
        with auth_session(self.engine) as s:
            s.add(ForecastServingIdentity(forecast_run_id=run.id,store_id=run.store_id,
                identity_digest=content_digest(identity.model_dump(mode='json')),identity_json=identity.model_dump(mode='json')))
            s.flush();s.commit()
        return ServedForecast(run,identity,False)

    def prepare_serve_capture(self,store,start,capture,product_ids=None):
        """capture callback must return detached operational facts and forecast pins.

        S4.9 owns the actual operational adapter. Three attempts = initial plus
        at most two re-preparations; no solver/public PlanningRun here.
        """
        for attempt in range(3):
            prepared=self.prepare(store,start,product_ids)
            served=self.serve(prepared)
            captured=capture(served,prepared)
            if captured.prepared_digest==served.identity.prepared_digest and captured.source_digest==served.identity.source_digest and captured.serving_version==prepared.serving.version:
                return served,captured
        raise AuthError('INPUT_CHANGED_DURING_CAPTURE',409)

    def capture_operational_preparation(self,served,preparation):
        """Real PG snapshot seam for S4.9's operational adapter, without solve.

        Operational rows and current forecast-source/config pins are loaded in
        the same snapshot. Returns after resources close; never uses a later DB
        query to manufacture provenance for previously captured operational rows.
        """
        store=preparation.prepared.request.store_id
        start=preparation.prepared.forecast_dates[0]
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ',postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                facts=load_readiness(s,store)
                try:prepared=prepare_observations(facts,store,start,preparation.prepared.request.product_ids)
                except AuthError as error:
                    if error.code not in ('NO_COMPUTABLE_PRODUCTS','PRODUCT_HISTORY_MISSING'):raise
                    return CapturedOperationalPreparation(facts,'SOURCE_CHANGED','SOURCE_CHANGED',facts.serving.version if facts.serving else None)
                return CapturedOperationalPreparation(facts,serialize_prepared(prepared).digest,source_digest(facts,prepared),facts.serving.version if facts.serving else None)
