"""Trusted internal baseline execution. Own Sessions; never accepts a caller Session."""
from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

import psycopg
from sqlalchemy import Engine
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.application._validation import require_product, require_store, require_terminal_time
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast import ForecastRunResult, PredictionInput
from app.application.contracts.forecast_execution import (
    ForecastExecutionInput, PreparedForecastInput, ForecastEngineResult, validate_engine_result,
)
from app.application.errors import ApplicationError, ErrorCategory
from app.application.forecast_serialization import (
    SerializedForecastInput, RetainedInputError, serialize_prepared, restore_prepared,
)
from app.application.use_cases.forecast import ForecastUseCases
from app.application.use_cases.forecast_baseline import assess_baseline_readiness, run_historical_quantile_baseline
from app.domain.forecasting.baseline import BASELINE_MODEL_TYPE, BASELINE_MODEL_VERSION, BaselineNotReadyError
from app.domain.forecasting.validation import forecast_dates
from app.infrastructure.database.forecast_execution_session import _execution_session, _note_secondary
from app.models import ForecastRun, ForecastRunInput, ForecastPrediction
from app.repositories.catalog import CatalogRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.forecast_input import ForecastInputRepository
from app.repositories.identity import StoreRepository
from app.repositories.sales import SalesRepository


class ForecastExecutionError(Exception):
    """Safe caller-facing execution outcome; original exception remains chained."""
    def __init__(self, code: str, run_id: UUID, outcome: str) -> None:
        self.code, self.run_id, self.outcome = code, run_id, outcome
        super().__init__(f'{code}; run_id={run_id}; outcome={outcome}')


class _CommitUncertain(Exception):
    """Recognized transport/unknown-resolution error during commit, not any error."""


def _is_uncertain_commit(error: Exception) -> bool:
    """Conservative classifier for the supported SQLAlchemy/psycopg stack only.

    A server SQLSTATE takes precedence over connection invalidation: e.g. 40001
    is a known transaction rollback even if the connection subsequently breaks.
    No-SQLSTATE transport errors require dialect disconnect evidence. Unknown
    error families remain errors; they never qualify for reconciled success.
    """
    if not isinstance(error, (OperationalError, InterfaceError)):
        return False
    if not isinstance(error.orig, (psycopg.OperationalError, psycopg.InterfaceError)):
        return False
    state = error.orig.sqlstate
    if state is not None:
        return state in {'08000', '08003', '08006', '08007', '40003'}
    return error.connection_invalidated


def _commit(session: Session) -> None:
    try:
        session.commit()
    except Exception as error:
        if _is_uncertain_commit(error):
            raise _CommitUncertain() from error
        raise


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ForecastExecutionUseCases:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def capture(self, request: ForecastExecutionInput) -> PreparedForecastInput:
        request = ForecastExecutionInput.model_validate(request)
        # Options precede begin/first SELECT; isolation is local to this connection.
        with self.engine.connect().execution_options(
                isolation_level='REPEATABLE READ', postgresql_readonly=True) as connection:
            with _execution_session(connection) as session:
                session.begin()
                store = StoreRepository(session).get_store_by_id(request.store_id)
                if store is None:
                    raise ApplicationError(ErrorCategory.NOT_FOUND, 'Store not found')
                products = []
                for identifier in request.product_ids:
                    product = CatalogRepository(session).get_product(request.store_id, identifier)
                    if product is None:
                        raise ApplicationError(ErrorCategory.NOT_FOUND, 'Product not found in Store')
                    products.append({'product_id': product.id, 'selling_unit': product.selling_unit})
                observations = []
                for product in products:
                    for row in SalesRepository(session).get_sales_history(
                            request.store_id, product['product_id'], request.history_start_date, request.cutoff_date):
                        observations.append({'store_id': row.store_id, 'product_id': row.product_id,
                            'sales_date': row.sales_date, 'quantity': row.quantity,
                            'selling_unit': product['selling_unit']})
                return PreparedForecastInput(request=request, timezone=store.timezone,
                    products=products, observations=observations, forecast_dates=forecast_dates(request.cutoff_date))

    def get(self, reference: RunReferenceInput) -> ForecastRunResult:
        reference = RunReferenceInput.model_validate(reference)
        with _execution_session(self.engine) as session:
            return ForecastUseCases(session).get(reference)

    def _retained(self, session: Session, reference: RunReferenceInput) -> PreparedForecastInput:
        run = ForecastRepository(session).get_forecast_run(reference.store_id, reference.run_id)
        if run is None:
            raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
        row = ForecastInputRepository(session).get_input(reference.store_id, reference.run_id)
        if row is None:
            raise RetainedInputError('RETAINED_INPUT_UNAVAILABLE')
        prepared = restore_prepared(row.prepared_json, row.serialization_version, row.digest)
        r = prepared.request
        if (r.store_id != reference.store_id or run.training_start_date != r.history_start_date
                or run.training_end_date != r.cutoff_date or run.forecast_start_date != prepared.forecast_dates[0]
                or run.forecast_end_date != prepared.forecast_dates[-1]
                or run.model_type != BASELINE_MODEL_TYPE or run.model_version != BASELINE_MODEL_VERSION
                or run.artifact_key is not None
                or (run.status == 'COMPLETED' and run.input_fingerprint != row.digest)):
            raise RetainedInputError('RETAINED_RUN_MISMATCH')
        return prepared

    def load_retained(self, reference: RunReferenceInput) -> PreparedForecastInput:
        reference = RunReferenceInput.model_validate(reference)
        with _execution_session(self.engine) as session:
            return self._retained(session, reference)

    def replay(self, reference: RunReferenceInput) -> ForecastEngineResult:
        return run_historical_quantile_baseline(self.load_retained(reference))

    def replay_persisted(self, reference: RunReferenceInput) -> ForecastRunResult:
        return self._execute_prepared(self.load_retained(reference))

    def execute(self, request: ForecastExecutionInput) -> ForecastRunResult:
        return self._execute_prepared(self.capture(request))

    def _start(self, run_id: UUID, prepared: PreparedForecastInput, encoded: SerializedForecastInput) -> None:
        r = prepared.request
        with _execution_session(self.engine) as session:
            session.begin()
            require_store(session, r.store_id)
            # Identity/FK checks only, never reconstruct capture from current rows.
            for p in r.product_ids:
                require_product(session, r.store_id, p)
            ForecastRepository(session).add_forecast_run(r.store_id, ForecastRun(
                id=run_id, store_id=r.store_id, status='RUNNING', started_at=_now(),
                training_start_date=r.history_start_date, training_end_date=r.cutoff_date,
                forecast_start_date=prepared.forecast_dates[0], forecast_end_date=prepared.forecast_dates[-1],
                model_type=BASELINE_MODEL_TYPE, model_version=BASELINE_MODEL_VERSION, artifact_key=None))
            session.flush()
            ForecastInputRepository(session).add_input(r.store_id, ForecastRunInput(
                forecast_run_id=run_id, store_id=r.store_id, prepared_json=json.loads(encoded.canonical_json),
                serialization_version=encoded.serialization_version, digest=encoded.digest))
            session.flush()
            _commit(session)

    def _complete(self, reference: RunReferenceInput, prepared: PreparedForecastInput,
                  result: ForecastEngineResult, encoded: SerializedForecastInput) -> None:
        result = validate_engine_result(prepared, result)
        if (result.model_type != BASELINE_MODEL_TYPE or result.model_version != BASELINE_MODEL_VERSION
                or result.artifact_identity is not None or result.warnings):
            raise RetainedInputError('BASELINE_IDENTITY_MISMATCH')
        with _execution_session(self.engine) as session:
            session.begin()
            repo = ForecastRepository(session)
            run = repo.get_running_for_update(reference.store_id, reference.run_id)
            if run is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
            retained = self._retained(session, reference)
            if serialize_prepared(retained).digest != encoded.digest:
                raise RetainedInputError('INPUT_DIGEST_MISMATCH')
            completed_at = _now()
            require_terminal_time(run.started_at, completed_at)
            for p in prepared.request.product_ids:
                require_product(session, reference.store_id, p)
            repo.add_predictions(reference.store_id, reference.run_id, [ForecastPrediction(
                **PredictionInput.model_validate(p.model_dump()).model_dump(),
                store_id=reference.store_id, forecast_run_id=reference.run_id) for p in result.predictions])
            repo.mark_completed(reference.store_id, reference.run_id, completed_at=completed_at,
                                input_fingerprint=encoded.digest, metrics_json=None)
            session.flush()
            _commit(session)

    def _verify_completed(self, reference: RunReferenceInput, expected: ForecastEngineResult,
                          encoded: SerializedForecastInput) -> ForecastRunResult:
        # One fresh read transaction for retained content and completed aggregate.
        with _execution_session(self.engine) as session:
            prepared = self._retained(session, reference)
            actual = ForecastUseCases(session).get(reference)
            if actual.status != 'COMPLETED' or actual.input_fingerprint != encoded.digest or actual.metrics_json is not None:
                raise RetainedInputError('COMPLETED_AGGREGATE_MISMATCH')
            projected = ForecastEngineResult(model_type=actual.model_type, model_version=actual.model_version,
                artifact_identity=actual.artifact_key, predictions=[p.model_dump(include={
                    'product_id','forecast_date','p25','p50','p75'}) for p in actual.predictions])
            if validate_engine_result(prepared, projected) != expected:
                raise RetainedInputError('COMPLETED_AGGREGATE_MISMATCH')
            return actual

    def _record_failure(self, reference: RunReferenceInput, code: str) -> None:
        with _execution_session(self.engine) as session:
            # Keep S1 lifecycle semantics, with S2.3's protected rollback/close.
            session.begin()
            repo = ForecastRepository(session)
            run = repo.get_running_for_update(reference.store_id, reference.run_id)
            if run is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
            completed_at = _now()
            require_terminal_time(run.started_at, completed_at)
            repo.mark_failed(reference.store_id, reference.run_id, completed_at=completed_at,
                error_code=code,
                error_summary='Internal baseline execution failed; inspect trusted application diagnostics.')
            session.flush()
            _commit(session)

    def _recover(self, reference: RunReferenceInput, error: Exception, code: str,
                 encoded: SerializedForecastInput, expected: ForecastEngineResult | None = None) -> ForecastRunResult:
        try:
            actual = self.get(reference)
        except Exception as read_error:
            _note_secondary(error, 'reconciliation read', read_error)
            raise ForecastExecutionError('OUTCOME_UNKNOWN', reference.run_id, 'UNKNOWN') from error
        if actual.status == 'COMPLETED':
            if isinstance(error, _CommitUncertain) and expected is not None:
                try:
                    return self._verify_completed(reference, expected, encoded)
                except Exception as verification_error:
                    _note_secondary(error, 'completed verification', verification_error)
                    raise ForecastExecutionError('COMPLETED_VERIFICATION_FAILED', reference.run_id, 'COMPLETED') from error
            raise ForecastExecutionError(code, reference.run_id, 'COMPLETED') from error
        if actual.status == 'FAILED':
            raise ForecastExecutionError(code, reference.run_id, 'FAILED') from error
        try:
            self._record_failure(reference, code)
        except Exception as recording_error:
            _note_secondary(error, 'failure recording', recording_error)
            try:
                final = self.get(reference)
            except Exception as read_error:
                _note_secondary(error, 'read after failed recording', read_error)
                raise ForecastExecutionError('OUTCOME_UNKNOWN', reference.run_id, 'UNKNOWN') from error
            raise ForecastExecutionError('FAILURE_RECORDING_FAILED', reference.run_id, final.status) from error
        raise ForecastExecutionError(code, reference.run_id, 'FAILED') from error

    def _execute_prepared(self, prepared: PreparedForecastInput) -> ForecastRunResult:
        prepared = PreparedForecastInput.model_validate(prepared)
        readiness = assess_baseline_readiness(prepared)
        if any(r.status == 'NOT_READY_NO_HISTORY' for r in readiness):
            raise BaselineNotReadyError(readiness)
        encoded = serialize_prepared(prepared)
        reference = RunReferenceInput(store_id=prepared.request.store_id, run_id=uuid4())
        try:
            self._start(reference.run_id, prepared, encoded)
        except Exception as error:
            # Includes post-commit programming/close errors: caller still needs run ID.
            try:
                self.get(reference)
            except ApplicationError as missing:
                if missing.category == ErrorCategory.NOT_FOUND:
                    if isinstance(error, ApplicationError):
                        raise error
                    raise ForecastExecutionError('START_FAILED', reference.run_id, 'NOT_STARTED') from error
                raise ForecastExecutionError('OUTCOME_UNKNOWN', reference.run_id, 'UNKNOWN') from error
            except Exception as read_error:
                _note_secondary(error, 'start reconciliation read', read_error)
                raise ForecastExecutionError('OUTCOME_UNKNOWN', reference.run_id, 'UNKNOWN') from error
            return self._recover(reference, error, 'START_FAILED', encoded)
        expected = None
        try:
            expected = validate_engine_result(prepared, run_historical_quantile_baseline(prepared))
            self._complete(reference, prepared, expected, encoded)
        except Exception as error:
            return self._recover(reference, error, 'BASELINE_EXECUTION_FAILED', encoded, expected)
        try:
            return self._verify_completed(reference, expected, encoded)
        except Exception as error:
            # Commit already acknowledged: never mark FAILED because read/verification failed.
            raise ForecastExecutionError('COMPLETED_READ_FAILED', reference.run_id, 'COMPLETED') from error
