"""Forecast persistence and guarded lifecycle writes; no forecast computation."""
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ForecastPrediction, ForecastRun
from app.repositories._guards import require_new, require_store
from app.repositories.errors import InvalidLifecycleTransition


class ForecastRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_forecast_run(self, store_id: UUID, run: ForecastRun, predictions: Sequence[ForecastPrediction] = ()) -> None:
        """Stage a new aggregate. Flush parent before children or to generate its ID.

        All preconditions are checked before staging; caller owns rollback of any
        flush failure and business horizon validation.
        """
        require_store(store_id, run.store_id)
        require_new(run)
        for prediction in predictions:
            require_store(store_id, prediction.store_id)
            require_new(prediction)
            if prediction.forecast_run_id is not None and prediction.forecast_run_id != run.id:
                raise ValueError("Prediction does not belong to the new ForecastRun")
        self._session.add(run)
        if run.id is None or predictions:
            self._session.flush()
        for prediction in predictions:
            prediction.forecast_run_id = run.id
            self._session.add(prediction)

    def get_forecast_run(self, store_id: UUID, run_id: UUID) -> ForecastRun | None:
        return self._session.scalar(select(ForecastRun).where(ForecastRun.store_id == store_id, ForecastRun.id == run_id))

    def _running_run(self, store_id: UUID, run_id: UUID) -> ForecastRun | None:
        """Serialize writers and refresh cached state; caller owns the lock lifetime."""
        run = self._session.scalar(select(ForecastRun).where(
            ForecastRun.store_id == store_id, ForecastRun.id == run_id,
        ).with_for_update().execution_options(populate_existing=True))
        if run is not None and run.status != "RUNNING":
            raise InvalidLifecycleTransition("Forecast write requires a RUNNING run")
        return run

    def get_running_for_update(self, store_id: UUID, run_id: UUID) -> ForecastRun | None:
        """Load current RUNNING metadata for application validation under the lock."""
        return self._running_run(store_id, run_id)

    def add_predictions(self, store_id: UUID, run_id: UUID,
                        predictions: Sequence[ForecastPrediction]) -> ForecastRun | None:
        """Stage predictions only for a locked RUNNING run; no computation/upsert."""
        for prediction in predictions:
            require_store(store_id, prediction.store_id)
            require_new(prediction)
            if prediction.forecast_run_id is not None and prediction.forecast_run_id != run_id:
                raise ValueError("Prediction does not belong to the ForecastRun")
        run = self._running_run(store_id, run_id)
        if run is None:
            return None
        for prediction in predictions:
            prediction.forecast_run_id = run_id
            self._session.add(prediction)
        return run

    def mark_completed(self, store_id: UUID, run_id: UUID, *, completed_at: datetime,
                       input_fingerprint: str,
                       metrics_json: dict[str, Any] | None = None) -> ForecastRun | None:
        run = self._running_run(store_id, run_id)
        if run is None:
            return None
        run.input_fingerprint = input_fingerprint
        run.metrics_json = deepcopy(metrics_json)
        run.completed_at = completed_at
        run.status = "COMPLETED"
        return run

    def mark_failed(self, store_id: UUID, run_id: UUID, *, completed_at: datetime,
                    error_code: str, error_summary: str) -> ForecastRun | None:
        """Persist caller-sanitized errors; failed runs require a new run to retry."""
        run = self._running_run(store_id, run_id)
        if run is None:
            return None
        run.error_code, run.error_summary = error_code, error_summary
        run.completed_at = completed_at
        run.status = "FAILED"
        return run

    def list_forecast_runs(self, store_id: UUID) -> list[ForecastRun]:
        return list(self._session.scalars(select(ForecastRun).where(ForecastRun.store_id == store_id).order_by(ForecastRun.created_at.desc(), ForecastRun.id)))

    def get_prediction(self, store_id: UUID, prediction_id: UUID) -> ForecastPrediction | None:
        return self._session.scalar(select(ForecastPrediction).where(ForecastPrediction.store_id == store_id, ForecastPrediction.id == prediction_id))

    def list_predictions(self, store_id: UUID, run_id: UUID) -> list[ForecastPrediction]:
        return list(self._session.scalars(select(ForecastPrediction).where(ForecastPrediction.store_id == store_id, ForecastPrediction.forecast_run_id == run_id).order_by(ForecastPrediction.forecast_date, ForecastPrediction.product_id, ForecastPrediction.id)))
