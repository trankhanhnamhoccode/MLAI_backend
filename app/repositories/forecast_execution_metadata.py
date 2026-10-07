from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecast_execution_metadata import ForecastExecutionMetadata
from app.repositories._guards import require_new, require_store
from app.repositories.forecast import ForecastRepository


class ForecastExecutionMetadataRepository:
    def __init__(self, session: Session):
        self._session = session

    def get(self, store_id: UUID, run_id: UUID) -> ForecastExecutionMetadata | None:
        return self._session.scalar(select(ForecastExecutionMetadata).where(
            ForecastExecutionMetadata.store_id == store_id, ForecastExecutionMetadata.forecast_run_id == run_id))

    def add(self, store_id: UUID, row: ForecastExecutionMetadata) -> None:
        require_store(store_id,row.store_id)
        require_new(row)
        if ForecastRepository(self._session).get_running_for_update(store_id,row.forecast_run_id) is None:
            raise ValueError('Execution metadata requires scoped RUNNING run')
        self._session.add(row)

    def complete_details(self, store_id: UUID, run_id: UUID, details: dict) -> None:
        if ForecastRepository(self._session).get_running_for_update(store_id,run_id) is None:
            raise ValueError('Execution metadata requires scoped RUNNING run')
        row = self.get(store_id,run_id)
        if row is None:
            raise ValueError('Execution metadata unavailable')
        for key in ('schema_version','selection_reason','candidate_artifact_identity','postprocessing_version'):
            if row.details_json.get(key) != details.get(key):
                raise ValueError('Execution selection identity cannot change at completion')
        row.details_json = deepcopy(details)
