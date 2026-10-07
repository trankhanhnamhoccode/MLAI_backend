"""Concrete trained/fallback execution path; reuses S2.3 capture and error recovery.

The one concrete subclass shares the tested owned-Session/commit-outcome lifecycle;
it is not an engine registry or a change to the fixed-baseline entrypoint.
"""
from dataclasses import dataclass
import json
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application._validation import require_store, require_product, require_terminal_time
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast import ForecastRunResult, PredictionInput
from app.application.contracts.forecast_execution import (
    ForecastExecutionInput, PreparedForecastInput, ForecastEngineResult, ForecastWarning, validate_engine_result,
)
from app.application.contracts.forecast_model import ExecutionDetails, ModelForecastRunResult, MODEL_TYPE, MODEL_VERSION
from app.application.forecast_serialization import serialize_prepared, restore_prepared, RetainedInputError
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.forecast import ForecastUseCases
from app.application.use_cases.forecast_baseline import assess_baseline_readiness, run_historical_quantile_baseline
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases, ForecastExecutionError, _commit, _now
from app.domain.forecasting.baseline import BASELINE_MODEL_TYPE, BASELINE_MODEL_VERSION, BaselineNotReadyError
from app.infrastructure.database.forecast_execution_session import _execution_session, _note_secondary
from app.infrastructure.forecast_model import predict_quantiles, inference_readiness, require_compatible
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore, LoadedArtifact, ArtifactMissingError
from app.models import ForecastRun, ForecastRunInput, ForecastPrediction, ForecastExecutionMetadata
from app.repositories.forecast import ForecastRepository
from app.repositories.forecast_input import ForecastInputRepository
from app.repositories.forecast_execution_metadata import ForecastExecutionMetadataRepository


@dataclass(frozen=True)
class ExecutionChoice:
    artifact: LoadedArtifact | None
    details: ExecutionDetails


@dataclass(frozen=True)
class ExpectedCompletion:
    result: ForecastEngineResult
    details: ExecutionDetails


def _fallback_details(reason: str, candidate: str | None) -> ExecutionDetails:
    return ExecutionDetails(selection_reason=reason, candidate_artifact_identity=candidate,
        warnings=(ForecastWarning(code='BASELINE_FALLBACK', severity='WARNING', field='model_type',
            entity='ForecastRun', impact=f'Historical baseline used for whole scope: {reason}; quality not established.'),))


class TrainedForecastExecutionUseCases(ForecastExecutionUseCases):
    def __init__(self, engine: Engine, artifacts: ForecastArtifactStore):
        super().__init__(engine)
        self.artifacts = artifacts

    def _details(self, session: Session, reference: RunReferenceInput) -> ExecutionDetails:
        row = ForecastExecutionMetadataRepository(session).get(reference.store_id,reference.run_id)
        if row is None:
            # S2.3 baseline runs have no metadata; retain their original warning-free behavior.
            run = ForecastRepository(session).get_forecast_run(reference.store_id,reference.run_id)
            if run is not None and run.model_type == BASELINE_MODEL_TYPE:
                return ExecutionDetails(selection_reason='LEGACY_BASELINE')
            raise RetainedInputError('EXECUTION_METADATA_UNAVAILABLE')
        return ExecutionDetails.model_validate(row.details_json)

    def get_with_metadata(self, reference: RunReferenceInput) -> ModelForecastRunResult:
        reference = RunReferenceInput.model_validate(reference)
        with _execution_session(self.engine) as session:
            run = ForecastUseCases(session).get(reference)
            return ModelForecastRunResult(run=run,execution=self._details(session,reference))

    def _retained(self, session: Session, reference: RunReferenceInput) -> PreparedForecastInput:
        run = ForecastRepository(session).get_forecast_run(reference.store_id,reference.run_id)
        if run is None:
            raise ApplicationError(ErrorCategory.NOT_FOUND,'ForecastRun not found in Store')
        row = ForecastInputRepository(session).get_input(reference.store_id,reference.run_id)
        if row is None:
            raise RetainedInputError('RETAINED_INPUT_UNAVAILABLE')
        prepared = restore_prepared(row.prepared_json,row.serialization_version,row.digest)
        details = self._details(session,reference)
        r = prepared.request
        trained = run.model_type == MODEL_TYPE and run.model_version == MODEL_VERSION
        baseline = run.model_type == BASELINE_MODEL_TYPE and run.model_version == BASELINE_MODEL_VERSION
        if (r.store_id != reference.store_id or run.training_start_date != r.history_start_date
                or run.training_end_date != r.cutoff_date or run.forecast_start_date != prepared.forecast_dates[0]
                or run.forecast_end_date != prepared.forecast_dates[-1]
                or not (trained or baseline)
                or (trained and (details.selection_reason != 'TRAINED_SELECTED'
                     or run.artifact_key is None or run.artifact_key != details.candidate_artifact_identity))
                or (baseline and (run.artifact_key is not None or details.selection_reason == 'TRAINED_SELECTED'))
                or (run.status == 'COMPLETED' and run.input_fingerprint != row.digest)):
            raise RetainedInputError('RETAINED_RUN_MISMATCH')
        return prepared

    def _choose(self, prepared: PreparedForecastInput, candidate: str | None) -> ExecutionChoice:
        readiness = assess_baseline_readiness(prepared)
        if any(r.status == 'NOT_READY_NO_HISTORY' for r in readiness):
            raise BaselineNotReadyError(readiness)
        if candidate is None:
            return ExecutionChoice(None,_fallback_details('NO_ARTIFACT',None))
        try:
            artifact = self.artifacts.load(candidate)
        except ArtifactMissingError:
            return ExecutionChoice(None,_fallback_details('ARTIFACT_MISSING',candidate))
        # Even a baseline-selected artifact must be valid/compatible; never hide corruption.
        require_compatible(artifact.model,prepared)
        if any(r.status != 'READY' for r in inference_readiness(prepared)):
            return ExecutionChoice(None,_fallback_details('NOT_READY_HISTORY',candidate))
        if artifact.manifest.evaluation.selected_family != MODEL_TYPE:
            return ExecutionChoice(None,_fallback_details('BASELINE_SELECTED',candidate))
        return ExecutionChoice(artifact,ExecutionDetails(selection_reason='TRAINED_SELECTED',
                                                        candidate_artifact_identity=candidate))

    def _compute(self, prepared: PreparedForecastInput, choice: ExecutionChoice) -> ExpectedCompletion:
        if choice.artifact is None:
            result = run_historical_quantile_baseline(prepared)
            result = ForecastEngineResult(**(result.model_dump() | {'warnings':choice.details.warnings}))
            return ExpectedCompletion(validate_engine_result(prepared,result),choice.details)
        result,crossings,negatives = predict_quantiles(choice.artifact.model,prepared,choice.artifact.identity)
        details = ExecutionDetails(**(choice.details.model_dump() | dict(raw_crossings=len(crossings),
            negative_values=negatives,warnings=result.warnings)))
        return ExpectedCompletion(result,details)

    def _start_selected(self, reference, prepared, encoded, choice):
        r = prepared.request
        with _execution_session(self.engine) as session:
            session.begin()
            require_store(session,r.store_id)
            for p in r.product_ids:
                require_product(session,r.store_id,p)
            ForecastRepository(session).add_forecast_run(r.store_id,ForecastRun(id=reference.run_id,
                store_id=r.store_id,status='RUNNING',started_at=_now(),
                training_start_date=r.history_start_date,training_end_date=r.cutoff_date,
                forecast_start_date=prepared.forecast_dates[0],forecast_end_date=prepared.forecast_dates[-1],
                model_type=MODEL_TYPE if choice.artifact else BASELINE_MODEL_TYPE,
                model_version=MODEL_VERSION if choice.artifact else BASELINE_MODEL_VERSION,
                artifact_key=choice.artifact.identity if choice.artifact else None))
            session.flush()
            ForecastInputRepository(session).add_input(r.store_id,ForecastRunInput(
                forecast_run_id=reference.run_id,store_id=r.store_id,prepared_json=json.loads(encoded.canonical_json),
                serialization_version=encoded.serialization_version,digest=encoded.digest))
            ForecastExecutionMetadataRepository(session).add(r.store_id,ForecastExecutionMetadata(
                forecast_run_id=reference.run_id,store_id=r.store_id,details_json=choice.details.model_dump(mode='json')))
            session.flush()
            _commit(session)

    def _complete_selected(self, reference, prepared, expected, encoded):
        result = validate_engine_result(prepared,expected.result)
        with _execution_session(self.engine) as session:
            session.begin()
            repo = ForecastRepository(session)
            run = repo.get_running_for_update(reference.store_id,reference.run_id)
            if run is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND,'ForecastRun not found in Store')
            retained = self._retained(session,reference)
            if (serialize_prepared(retained).digest != encoded.digest
                    or (run.model_type,run.model_version,run.artifact_key) != (
                        result.model_type,result.model_version,result.artifact_identity)
                    or expected.details.warnings != result.warnings):
                raise RetainedInputError('COMPLETION_IDENTITY_MISMATCH')
            completed_at = _now()
            require_terminal_time(run.started_at,completed_at)
            for p in prepared.request.product_ids:
                require_product(session,reference.store_id,p)
            ForecastExecutionMetadataRepository(session).complete_details(reference.store_id,reference.run_id,
                expected.details.model_dump(mode='json'))
            repo.add_predictions(reference.store_id,reference.run_id,[ForecastPrediction(
                **PredictionInput.model_validate(p.model_dump()).model_dump(),store_id=reference.store_id,
                forecast_run_id=reference.run_id) for p in result.predictions])
            repo.mark_completed(reference.store_id,reference.run_id,completed_at=completed_at,
                input_fingerprint=encoded.digest,metrics_json=None)
            session.flush()
            _commit(session)

    def _verify_completed(self, reference, expected: ExpectedCompletion, encoded) -> ForecastRunResult:
        with _execution_session(self.engine) as session:
            prepared = self._retained(session,reference)
            actual = ForecastUseCases(session).get(reference)
            details = self._details(session,reference)
            projected = ForecastEngineResult(model_type=actual.model_type,model_version=actual.model_version,
                artifact_identity=actual.artifact_key,warnings=details.warnings,predictions=[
                    p.model_dump(include={'product_id','forecast_date','p25','p50','p75'}) for p in actual.predictions])
            if (actual.status != 'COMPLETED' or actual.input_fingerprint != encoded.digest
                    or actual.metrics_json is not None or details != expected.details
                    or validate_engine_result(prepared,projected) != expected.result):
                raise RetainedInputError('COMPLETED_AGGREGATE_MISMATCH')
            return actual

    def _record_failure(self, reference: RunReferenceInput, code: str) -> None:
        with _execution_session(self.engine) as session:
            session.begin()
            repo = ForecastRepository(session)
            run = repo.get_running_for_update(reference.store_id,reference.run_id)
            if run is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND,'ForecastRun not found in Store')
            completed_at = _now()
            require_terminal_time(run.started_at,completed_at)
            repo.mark_failed(reference.store_id,reference.run_id,completed_at=completed_at,error_code=code,
                error_summary='Internal forecast execution failed; inspect trusted application diagnostics.')
            session.flush()
            _commit(session)

    def _run(self, prepared, choice) -> ForecastRunResult:
        prepared = PreparedForecastInput.model_validate(prepared)
        encoded = serialize_prepared(prepared)
        reference = RunReferenceInput(store_id=prepared.request.store_id,run_id=uuid4())
        try:
            self._start_selected(reference,prepared,encoded,choice)
        except Exception as error:
            try:
                self.get(reference)
            except ApplicationError as missing:
                if missing.category == ErrorCategory.NOT_FOUND:
                    raise ForecastExecutionError('START_FAILED',reference.run_id,'NOT_STARTED') from error
                raise ForecastExecutionError('OUTCOME_UNKNOWN',reference.run_id,'UNKNOWN') from error
            except Exception as secondary:
                _note_secondary(error,'start reconciliation read',secondary)
                raise ForecastExecutionError('OUTCOME_UNKNOWN',reference.run_id,'UNKNOWN') from error
            return self._recover(reference,error,'START_FAILED',encoded)
        expected = None
        try:
            expected = self._compute(prepared,choice)
            self._complete_selected(reference,prepared,expected,encoded)
        except Exception as error:
            return self._recover(reference,error,'MODEL_EXECUTION_FAILED',encoded,expected)
        try:
            return self._verify_completed(reference,expected,encoded)
        except Exception as error:
            raise ForecastExecutionError('COMPLETED_READ_FAILED',reference.run_id,'COMPLETED') from error

    def execute(self, request: ForecastExecutionInput, artifact_identity: str | None = None) -> ForecastRunResult:
        prepared = self.capture(request)  # Snapshot Session closed before artifact I/O/preflight.
        return self._run(prepared,self._choose(prepared,artifact_identity))

    def _replay_choice(self, reference):
        reference = RunReferenceInput.model_validate(reference)
        with _execution_session(self.engine) as session:
            prepared = self._retained(session,reference)
            run = ForecastUseCases(session).get(reference)
            details = self._details(session,reference)
        # Exact artifact, no latest/retrain/fallback; all DB Sessions are already closed.
        artifact = self.artifacts.load(run.artifact_key) if run.model_type == MODEL_TYPE else None
        if artifact is not None:
            require_compatible(artifact.model,prepared)
        initial = ExecutionDetails(**(details.model_dump() | dict(raw_crossings=0,negative_values=0,
            warnings=() if artifact else details.warnings)))
        return prepared,ExecutionChoice(artifact,initial)

    def replay(self, reference: RunReferenceInput) -> ForecastEngineResult:
        prepared,choice = self._replay_choice(reference)
        return self._compute(prepared,choice).result

    def replay_persisted(self, reference: RunReferenceInput) -> ForecastRunResult:
        prepared,choice = self._replay_choice(reference)
        return self._run(prepared,choice)
