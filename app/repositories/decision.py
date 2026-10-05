"""New historical decision records and scoped reads; no recommendation engine."""
from uuid import UUID
from copy import deepcopy
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DecisionRun
from app.repositories._guards import require_new, require_store
from app.repositories.errors import InvalidLifecycleTransition


class DecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_decision_run(self, store_id: UUID, run: DecisionRun) -> None:
        require_store(store_id, run.store_id)
        require_new(run)
        self._session.add(run)

    def get_decision_run(self, store_id: UUID, run_id: UUID) -> DecisionRun | None:
        return self._session.scalar(select(DecisionRun).where(DecisionRun.store_id == store_id, DecisionRun.id == run_id))

    def _running_run(self, store_id: UUID, run_id: UUID) -> DecisionRun | None:
        """Serialize writers and refresh cached state; caller owns the lock lifetime."""
        run = self._session.scalar(select(DecisionRun).where(
            DecisionRun.store_id == store_id, DecisionRun.id == run_id,
        ).with_for_update().execution_options(populate_existing=True))
        if run is not None and run.status != "RUNNING":
            raise InvalidLifecycleTransition("Decision write requires a RUNNING run")
        return run

    def complete_run(self, store_id: UUID, run_id: UUID, *, completed_at: datetime,
                     input_fingerprint: str, package_schema_version: int,
                     input_snapshot_json: dict[str, Any],
                     decision_package_json: dict[str, Any],
                     recommended_strategy: Literal["LEAN", "BALANCED", "PROTECTED"]) -> DecisionRun | None:
        """Persist supplied values once; package business validation belongs to caller."""
        run = self._running_run(store_id, run_id)
        if run is None:
            return None
        run.input_fingerprint = input_fingerprint
        run.package_schema_version = package_schema_version
        run.input_snapshot_json = deepcopy(input_snapshot_json)
        run.decision_package_json = deepcopy(decision_package_json)
        run.recommended_strategy = recommended_strategy
        run.completed_at = completed_at
        run.status = "COMPLETED"
        return run

    def fail_run(self, store_id: UUID, run_id: UUID, *, completed_at: datetime,
                 error_code: str, error_summary: str) -> DecisionRun | None:
        """Persist caller-sanitized errors; never replace completed output."""
        run = self._running_run(store_id, run_id)
        if run is None:
            return None
        run.error_code, run.error_summary = error_code, error_summary
        run.completed_at = completed_at
        run.status = "FAILED"
        return run

    def list_decision_runs(self, store_id: UUID) -> list[DecisionRun]:
        return list(self._session.scalars(select(DecisionRun).where(DecisionRun.store_id == store_id).order_by(DecisionRun.created_at.desc(), DecisionRun.id)))

    def list_for_forecast(self, store_id: UUID, forecast_run_id: UUID) -> list[DecisionRun]:
        return list(self._session.scalars(select(DecisionRun).where(DecisionRun.store_id == store_id, DecisionRun.forecast_run_id == forecast_run_id).order_by(DecisionRun.created_at.desc(), DecisionRun.id)))
