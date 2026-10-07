"""S2 must not tighten S1's low-level lifecycle. This is not execution E2E."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast import CompleteForecastRunInput, FailRunInput, StartForecastRunInput
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.forecast import ForecastUseCases
from app.infrastructure.database.engine import create_database_engine
from app.models import ForecastRun, Store
from app.repositories.forecast import ForecastRepository
from app.repositories.identity import StoreRepository


def test_s1_empty_completion_fresh_session_and_terminal_guard(database_settings):
    engine = create_database_engine(database_settings)
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    try:
        with Session(engine) as session, session.begin():
            store = Store(name='S1 fixture')
            StoreRepository(session).add_store(store)
            session.flush()
            store_id = store.id
        with Session(engine) as session:
            cases = ForecastUseCases(session)
            started = cases.start(StartForecastRunInput(
                store_id=store_id, training_start_date=date(2026, 9, 1),
                training_end_date=date(2026, 9, 11), forecast_start_date=date(2026, 10, 1),
                forecast_end_date=date(2026, 10, 2), model_type='supplied-fixture',
                model_version='v1', artifact_key='supplied-artifact', started_at=now))
            completed = cases.complete(CompleteForecastRunInput(
                store_id=store_id, run_id=started.id, completed_at=now + timedelta(hours=1),
                input_fingerprint='empty-fixture', predictions=()))
            assert completed.status == 'COMPLETED' and completed.predictions == ()
            assert not session.in_transaction()
        with Session(engine) as fresh:
            stored = fresh.get(ForecastRun, started.id)
            assert stored.status == 'COMPLETED' and stored.input_fingerprint == 'empty-fixture'
            assert stored.model_type == 'supplied-fixture' and stored.artifact_key == 'supplied-artifact'
            assert ForecastRepository(fresh).list_predictions(store_id, started.id) == []
            result = ForecastUseCases(fresh).get(RunReferenceInput(store_id=store_id, run_id=started.id))
            assert result.predictions == () and fresh.in_transaction()  # Read autobegin is unchanged.
            fresh.rollback()
            with pytest.raises(ApplicationError) as caught:
                ForecastUseCases(fresh).fail(FailRunInput(
                    store_id=store_id, run_id=started.id, completed_at=now + timedelta(hours=2),
                    error_code='FIXTURE', error_summary='Terminal fixture cannot fail again'))
            assert caught.value.category == ErrorCategory.INVALID_LIFECYCLE
        with Session(engine) as fresh:
            assert fresh.get(ForecastRun, started.id).status == 'COMPLETED'
    finally:
        engine.dispose()
