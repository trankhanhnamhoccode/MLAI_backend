"""Store-scoped insert/read only; caller owns transaction, no dedup or updates."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecast_run_input import ForecastRunInput
from app.repositories._guards import require_new, require_store
from app.repositories.forecast import ForecastRepository


class ForecastInputRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_input(self, store_id: UUID, row: ForecastRunInput) -> None:
        require_store(store_id, row.store_id)
        require_new(row)
        if ForecastRepository(self._session).get_running_for_update(store_id, row.forecast_run_id) is None:
            raise ValueError('Retained input requires an existing scoped RUNNING run')
        self._session.add(row)

    def get_input(self, store_id: UUID, run_id: UUID) -> ForecastRunInput | None:
        return self._session.scalar(select(ForecastRunInput).where(
            ForecastRunInput.store_id == store_id, ForecastRunInput.forecast_run_id == run_id))
