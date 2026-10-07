"""Synthetic S2.3 manual verification; writes only guarded shelfcash_test, no reset."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases
from app.models import Store, Product, SalesDaily, ForecastRun, ForecastRunInput, ForecastPrediction
from scripts.dev import validate_reset_target, inspect_database, require_head


def main() -> None:
    current = Settings()
    settings = Settings(_env_file=None, environment='test', database_url=current.test_database_url)
    validate_reset_target(settings)
    if make_url(settings.database_url).database != 'shelfcash_test':
        raise ValueError('Manual verification owns only shelfcash_test')
    require_head(inspect_database(settings))
    engine = create_database_engine(settings)
    try:
        store_id, product_id = uuid4(), uuid4()
        with Session(engine) as session, session.begin():
            session.add(Store(id=store_id, name='S2.3 verification fixture'))
            session.flush()
            session.add(Product(id=product_id, store_id=store_id, name='Fixture', selling_unit='cup'))
            session.flush()
            session.add_all([SalesDaily(store_id=store_id, product_id=product_id,
                sales_date=day, quantity=Decimal(q)) for day,q in [(date(2026,9,7),'10'),(date(2026,9,9),'0')]])
        cases = ForecastExecutionUseCases(engine)
        result = cases.execute(ForecastExecutionInput(store_id=store_id, product_ids=(product_id,),
            history_start_date=date(2026,9,7), cutoff_date=date(2026,9,11)))
        replayed = cases.replay_persisted(RunReferenceInput(store_id=store_id, run_id=result.id))
        assert replayed.id != result.id and replayed.input_fingerprint == result.input_fingerprint
        with Session(engine) as fresh:
            for run_id in (result.id, replayed.id):
                run = fresh.get(ForecastRun, run_id)
                retained = fresh.get(ForecastRunInput, run_id)
                assert run.status == 'COMPLETED' and run.input_fingerprint == retained.digest
                predictions = fresh.scalars(select(ForecastPrediction).where(ForecastPrediction.forecast_run_id==run_id)).all()
                assert len(predictions)==7 and all(p.p50==Decimal('5') for p in predictions)
        print('Verified fresh-session COMPLETED, seven 2.5/5/7.5 predictions, retained input and new-UUID replay.')
        print(f'store_id={store_id}; run_id={result.id}; replay_run_id={replayed.id}')
        # Leave fixtures visible for manual SQL inspection; isolated tests own cleanup.
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
