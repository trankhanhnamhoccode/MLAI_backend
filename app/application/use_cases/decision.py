"""Persist supplied Decision fixtures; no recommendation computation."""
from copy import deepcopy
from uuid import UUID
from sqlalchemy.orm import Session
from app.application._validation import require_idle_session, require_terminal_time
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast import FailRunInput
from app.application.contracts.decision import CompleteDecisionRunInput, DecisionRunResult, StartDecisionRunInput
from app.application.errors import ApplicationError, ErrorCategory
from app.models import DecisionRun
from app.repositories.decision import DecisionRepository
from app.repositories.forecast import ForecastRepository
from app.repositories.errors import InvalidLifecycleTransition


class DecisionUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.decisions = DecisionRepository(session)
        self.forecasts = ForecastRepository(session)

    def _require_completed_forecast(self, store_id: UUID, run_id: UUID) -> None:
        row = self.forecasts.get_forecast_run(store_id, run_id)
        if row is None:
            raise ApplicationError(ErrorCategory.NOT_FOUND, 'ForecastRun not found in Store')
        if row.status != 'COMPLETED':
            raise ApplicationError(ErrorCategory.INVALID_LIFECYCLE, 'Decision requires a COMPLETED ForecastRun')

    def _result(self, row: DecisionRun) -> DecisionRunResult:
        return DecisionRunResult.model_validate({name: deepcopy(getattr(row, name))
            for name in DecisionRunResult.model_fields})

    def get(self, data: RunReferenceInput) -> DecisionRunResult:
        data = RunReferenceInput.model_validate(data)
        with self.session.no_autoflush:
            row = self.decisions.get_decision_run(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'DecisionRun not found in Store')
            return self._result(row)

    def start(self, data: StartDecisionRunInput) -> DecisionRunResult:
        data = StartDecisionRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            self._require_completed_forecast(data.store_id, data.forecast_run_id)
            row = DecisionRun(**data.model_dump(), status='RUNNING')
            self.decisions.add_decision_run(data.store_id, row)
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

    def complete(self, data: CompleteDecisionRunInput) -> DecisionRunResult:
        data = CompleteDecisionRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            row = self.decisions.get_running_for_update(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'DecisionRun not found in Store')
            require_terminal_time(row.started_at, data.completed_at)
            self._require_completed_forecast(data.store_id, row.forecast_run_id)
            self.decisions.complete_run(data.store_id, data.run_id, completed_at=data.completed_at,
                input_fingerprint=data.input_fingerprint, package_schema_version=data.package_schema_version,
                input_snapshot_json=data.input_snapshot_json.model_dump(),
                decision_package_json=data.decision_package_json.model_dump(),
                recommended_strategy=data.recommended_strategy)
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

    def fail(self, data: FailRunInput) -> DecisionRunResult:
        data = FailRunInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            row = self.decisions.get_running_for_update(data.store_id, data.run_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'DecisionRun not found in Store')
            require_terminal_time(row.started_at, data.completed_at)
            self.decisions.fail_run(data.store_id, data.run_id, completed_at=data.completed_at,
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
