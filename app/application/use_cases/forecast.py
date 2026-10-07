"""Persist supplied Forecast fixtures; no model execution."""
from copy import deepcopy
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.application._validation import require_idle_session, require_product, require_store, require_terminal_time
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast import CompleteForecastRunInput, FailRunInput, ForecastRunResult, PredictionResult, StartForecastRunInput
from app.application.errors import ApplicationError, ErrorCategory, known_conflict
from app.models import ForecastPrediction, ForecastRun
from app.repositories.forecast import ForecastRepository
from app.repositories.errors import InvalidLifecycleTransition


class ForecastUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.forecasts = ForecastRepository(session)

    def _result(self, row: ForecastRun) -> ForecastRunResult:
        # Local mapping only; the caller sees the explicit typed result.
        fields = {name: deepcopy(getattr(row, name)) for name in ForecastRunResult.model_fields if name != 'predictions'}
        return ForecastRunResult(**fields, predictions=tuple(PredictionResult.model_validate(p)
            for p in self.forecasts.list_predictions(row.store_id, row.id)))

    def get(self, data: RunReferenceInput) -> ForecastRunResult:
        data = RunReferenceInput.model_validate(data)
        with self.session.no_autoflush:
            row = self.forecasts.get_forecast_run(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
            return self._result(row)

    def start(self, data: StartForecastRunInput) -> ForecastRunResult:
        data = StartForecastRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_store(self.session, data.store_id)
            row = ForecastRun(**data.model_dump(), status='RUNNING')
            self.forecasts.add_forecast_run(data.store_id, row)
            self.session.flush()
            result = self._result(row)
            self.session.commit()
            return result
        except InvalidLifecycleTransition as error:
            self.session.rollback()
            raise ApplicationError(ErrorCategory.INVALID_LIFECYCLE, str(error)) from error
        except Exception:
            self.session.rollback()
            raise

    def complete(self, data: CompleteForecastRunInput) -> ForecastRunResult:
        data = CompleteForecastRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            row = self.forecasts.get_running_for_update(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
            require_terminal_time(row.started_at, data.completed_at)
            for prediction in data.predictions:
                require_product(self.session, data.store_id, prediction.product_id)
                if not row.forecast_start_date <= prediction.forecast_date <= row.forecast_end_date:
                    raise ApplicationError(ErrorCategory.VALIDATION_ERROR, 'Prediction date outside forecast horizon')
            predictions = [ForecastPrediction(**p.model_dump(), store_id=data.store_id, forecast_run_id=data.run_id)
                           for p in data.predictions]
            self.forecasts.add_predictions(data.store_id, data.run_id, predictions)
            self.forecasts.mark_completed(data.store_id, data.run_id, completed_at=data.completed_at,
                input_fingerprint=data.input_fingerprint,
                metrics_json=data.metrics_json.model_dump() if data.metrics_json is not None else None)
            self.session.flush()
            result = self._result(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            mapped = known_conflict(error, 'uq_forecast_predictions_run_product_date')
            if mapped is not None:
                raise mapped from error
            raise
        except InvalidLifecycleTransition as error:
            self.session.rollback()
            raise ApplicationError(ErrorCategory.INVALID_LIFECYCLE, str(error)) from error
        except Exception:
            self.session.rollback()
            raise

    def fail(self, data: FailRunInput) -> ForecastRunResult:
        data = FailRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            row = self.forecasts.get_running_for_update(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
            require_terminal_time(row.started_at, data.completed_at)
            self.forecasts.mark_failed(data.store_id, data.run_id, completed_at=data.completed_at,
                error_code=data.error_code, error_summary=data.error_summary)
            self.session.flush()
            result = self._result(row)
            self.session.commit()
            return result
        except InvalidLifecycleTransition as error:
            self.session.rollback()
            raise ApplicationError(ErrorCategory.INVALID_LIFECYCLE, str(error)) from error
        except Exception:
            self.session.rollback()
            raise
