"""SYNTHETIC retained trained execution, writes only shelfcash_test; no reset/migrate."""
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.application.use_cases.forecast_evaluation import backtest
from app.application.use_cases.forecast_trained_execution import TrainedForecastExecutionUseCases
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.forecast_model import train_quantiles
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
from app.models import Store, Product, SalesDaily, ForecastRun, ForecastRunInput, ForecastPrediction, ForecastExecutionMetadata
from scripts.dev import validate_reset_target, inspect_database, require_head
from scripts.forecast_demo import synthetic_input


def main():
    current = Settings()
    settings = Settings(_env_file=None,environment='test',database_url=current.test_database_url)
    validate_reset_target(settings)
    if make_url(settings.database_url).database != 'shelfcash_test':
        raise ValueError('Manual verification owns only shelfcash_test')
    require_head(inspect_database(settings))
    engine = create_database_engine(settings)
    try:
        fixture = synthetic_input(120,2)
        store = uuid4()
        mapping = {p:uuid4() for p in fixture.request.product_ids}
        with Session(engine) as writer,writer.begin():
            writer.add(Store(id=store,name='SYNTHETIC trained verification',timezone=fixture.timezone))
            writer.flush()
            writer.add_all([Product(id=new,store_id=store,name='SYNTHETIC',selling_unit='cup') for new in mapping.values()])
            writer.flush()
            writer.add_all([SalesDaily(store_id=store,product_id=mapping[o.product_id],
                sales_date=o.sales_date,quantity=o.quantity) for o in fixture.observations])
        artifacts = ForecastArtifactStore(Path('runtime/model_artifacts'))
        cases = TrainedForecastExecutionUseCases(engine,artifacts)
        request = ForecastExecutionInput(store_id=store,product_ids=tuple(mapping.values()),
            history_start_date=fixture.request.history_start_date,cutoff_date=fixture.request.cutoff_date)
        prepared = cases.capture(request)
        assert engine.pool.checkedout()==0
        evaluation = backtest(prepared,'SYNTHETIC')
        identity = artifacts.publish(train_quantiles(prepared),evaluation)
        assert evaluation.selected_family=='lightgbm_quantile'
        result = cases.execute(request,identity)
        reference = RunReferenceInput(store_id=store,run_id=result.id)
        before = cases.replay(reference)
        with Session(engine) as writer,writer.begin():
            writer.execute(SalesDaily.__table__.update().where(SalesDaily.store_id==store).values(quantity=Decimal('999')))
            writer.execute(Product.__table__.update().where(Product.store_id==store).values(selling_unit='changed'))
        assert cases.replay(reference)==before
        second = cases.replay_persisted(reference)
        assert second.id!=result.id and second.input_fingerprint==result.input_fingerprint
        with Session(engine) as fresh:
            for identifier in (result.id,second.id):
                run=fresh.get(ForecastRun,identifier)
                retained=fresh.get(ForecastRunInput,identifier)
                meta=fresh.get(ForecastExecutionMetadata,identifier)
                predictions=fresh.scalars(select(ForecastPrediction).where(ForecastPrediction.forecast_run_id==identifier)).all()
                assert run.status=='COMPLETED' and run.artifact_key==identity and run.input_fingerprint==retained.digest
                assert meta.details_json['selection_reason']=='TRAINED_SELECTED' and len(predictions)==14
                assert all((p.p25,p.p50,p.p75)==(q.p25,q.p50,q.p75) for p,q in zip(
                    sorted(predictions,key=lambda p:(p.forecast_date,p.product_id)),before.predictions))
        print('SYNTHETIC mechanics verified: fresh-session completed 14 predictions + metadata; retained exact-artifact replay after live corrections.')
        print(f'store_id={store}; run_id={result.id}; replay_run_id={second.id}; artifact={identity}')
        print('Real-data quality NOT EVALUATED; fixtures retained in shelfcash_test for inspection.')
    finally:
        engine.dispose()


if __name__=='__main__':
    main()
