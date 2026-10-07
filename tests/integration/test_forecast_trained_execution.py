"""Real PostgreSQL + trusted local artifacts; fresh-session persistence assertions."""
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastEngineResult
from app.application.use_cases.forecast_evaluation import backtest
from app.application.use_cases.forecast_trained_execution import TrainedForecastExecutionUseCases
from app.application.use_cases.forecast_execution import ForecastExecutionError
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.forecast_model import train_quantiles, ModelBoundaryError
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore, ArtifactError, ArtifactMissingError
from app.models import Store, Product, SalesDaily, ForecastRun, ForecastRunInput, ForecastPrediction, ForecastExecutionMetadata
from app.repositories.forecast_execution_metadata import ForecastExecutionMetadataRepository
from scripts.forecast_demo import synthetic_input


@pytest.fixture
def setup(database_settings,tmp_path):
    engine = create_database_engine(database_settings)
    prepared = synthetic_input(80,2)
    with Session(engine) as writer, writer.begin():
        writer.add(Store(id=prepared.request.store_id,name='SYNTHETIC trained integration',timezone=prepared.timezone))
        writer.flush()
        writer.add_all([Product(id=p.product_id,store_id=prepared.request.store_id,
            name=f'SYNTHETIC {p.product_id}',selling_unit=p.selling_unit) for p in prepared.products])
        writer.flush()
        writer.add_all([SalesDaily(store_id=o.store_id,product_id=o.product_id,
            sales_date=o.sales_date,quantity=o.quantity) for o in prepared.observations])
    artifacts = ForecastArtifactStore(tmp_path/'artifacts')
    cases = TrainedForecastExecutionUseCases(engine,artifacts)
    report = backtest(prepared,'SYNTHETIC')
    assert report.selected_family == 'lightgbm_quantile'  # Fixture mechanics, not real superiority.
    identity = artifacts.publish(train_quantiles(prepared),report)
    try:
        yield engine,prepared,cases,identity
    finally:
        engine.dispose()


def reference(prepared,run_id):
    return RunReferenceInput(store_id=prepared.request.store_id,run_id=run_id)


def counts(engine):
    with Session(engine) as fresh:
        return tuple(fresh.scalar(select(func.count()).select_from(model)) for model in (
            ForecastRun,ForecastRunInput,ForecastExecutionMetadata,ForecastPrediction))


def test_fresh_session_actual_model_metadata_predictions_and_replay_after_live_changes(setup,monkeypatch):
    engine,prepared,cases,identity = setup
    real_load = cases.artifacts.load
    def load_outside_transactions(key):
        assert engine.pool.checkedout() == 0
        return real_load(key)
    monkeypatch.setattr(cases.artifacts,'load',load_outside_transactions)
    real_compute = cases._compute
    def compute_outside_transactions(*args):
        assert engine.pool.checkedout() == 0
        return real_compute(*args)
    monkeypatch.setattr(cases,'_compute',compute_outside_transactions)
    result = cases.execute(prepared.request,identity)
    ref = reference(prepared,result.id)
    before = cases.replay(ref)
    with Session(engine) as fresh:
        run = fresh.get(ForecastRun,result.id)
        retained = fresh.get(ForecastRunInput,result.id)
        meta = fresh.get(ForecastExecutionMetadata,result.id)
        assert run.status == 'COMPLETED' and run.artifact_key == identity and run.model_type == 'lightgbm_quantile'
        assert run.input_fingerprint == retained.digest and run.metrics_json is None
        assert meta.details_json['selection_reason'] == 'TRAINED_SELECTED'
        assert len(fresh.scalars(select(ForecastPrediction)).all()) == 14
    with Session(engine) as writer, writer.begin():
        writer.execute(SalesDaily.__table__.update().values(quantity=Decimal('999')))
        writer.execute(Product.__table__.update().values(selling_unit='changed',active=False))
    assert cases.replay(ref) == before
    second = cases.replay_persisted(ref)
    assert second.id != result.id and second.artifact_key == identity
    assert second.input_fingerprint == result.input_fingerprint
    assert counts(engine) == (2,2,2,28)
    assert cases.get_with_metadata(reference(prepared,second.id)).execution == cases.get_with_metadata(ref).execution


@pytest.mark.parametrize('candidate,reason',[(None,'NO_ARTIFACT'),('0'*64,'ARTIFACT_MISSING')])
def test_fallback_metadata_is_persisted_and_readable(setup,candidate,reason):
    engine,prepared,cases,_ = setup
    result = cases.execute(prepared.request,candidate)
    details = cases.get_with_metadata(reference(prepared,result.id)).execution
    assert result.model_type == 'historical_quantile_baseline' and result.artifact_key is None
    assert details.selection_reason == reason and details.warnings[0].code == 'BASELINE_FALLBACK'
    with Session(engine) as fresh:
        stored = fresh.get(ForecastExecutionMetadata,result.id)
        assert stored.details_json['warnings'][0]['impact'] == details.warnings[0].impact
    assert cases.replay(reference(prepared,result.id)).warnings == details.warnings


def test_readiness_fallback_and_baseline_selection_are_distinct(setup):
    engine,prepared,cases,identity = setup
    request = type(prepared.request)(**(prepared.request.model_dump() | {
        'history_start_date':prepared.request.cutoff_date}))
    result = cases.execute(request,identity)
    assert cases.get_with_metadata(reference(prepared,result.id)).execution.selection_reason == 'NOT_READY_HISTORY'
    report = backtest(prepared,'SYNTHETIC')
    # Typed test injection of a baseline tie selection; no claim it is measured.
    baseline_report = type(report).model_validate(report.model_dump() | dict(
        selected_family='historical_quantile_baseline',selection_reason='BASELINE_TIE_OR_BETTER'))
    baseline_id = cases.artifacts.publish(train_quantiles(prepared),baseline_report)
    result = cases.execute(prepared.request,baseline_id)
    assert cases.get_with_metadata(reference(prepared,result.id)).execution.selection_reason == 'BASELINE_SELECTED'


@pytest.mark.parametrize('kind',['corrupt','incompatible'])
def test_bad_artifact_never_falls_back_or_starts_run(setup,kind):
    engine,prepared,cases,identity = setup
    if kind == 'corrupt':
        (cases.artifacts.root/identity/'p25.txt').write_text('corrupt')
    else:
        with Session(engine) as writer,writer.begin():
            writer.execute(Product.__table__.update().values(selling_unit='changed'))
    with pytest.raises((ArtifactError,ModelBoundaryError)):
        cases.execute(prepared.request,identity)
    assert counts(engine) == (0,0,0,0)


def test_replay_missing_artifact_is_error_not_retrain_or_fallback(setup):
    engine,prepared,cases,identity = setup
    result = cases.execute(prepared.request,identity)
    (cases.artifacts.root/identity).rename(cases.artifacts.root/'offline')
    with pytest.raises(ArtifactMissingError):
        cases.replay(reference(prepared,result.id))
    with pytest.raises(ArtifactMissingError):
        cases.replay_persisted(reference(prepared,result.id))
    assert counts(engine) == (1,1,1,14)


def test_atomic_start_metadata_failure_keeps_all_three_absent(setup,monkeypatch):
    engine,prepared,cases,identity = setup
    def reject(*args):
        raise ValueError('injected metadata insert bug')
    monkeypatch.setattr(ForecastExecutionMetadataRepository,'add',reject)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.outcome == 'NOT_STARTED'
    assert isinstance(error.value.__cause__,ValueError)
    assert counts(engine) == (0,0,0,0)


@pytest.mark.parametrize('kind',['compute','coverage','metadata'])
def test_failure_no_partial_predictions_retains_start_metadata_input(setup,monkeypatch,kind):
    engine,prepared,cases,identity = setup
    compute = cases._compute
    def bad(*args):
        if kind == 'compute':
            raise ValueError('injected programming error')
        expected = compute(*args)
        result = expected.result
        if kind == 'coverage':
            result = ForecastEngineResult(**(result.model_dump() | {'predictions':result.predictions[:-1]}))
        else:
            result = ForecastEngineResult(**(result.model_dump() | {'model_version':'incorrect'}))
        return replace(expected,result=result)
    monkeypatch.setattr(cases,'_compute',bad)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.outcome == 'FAILED'
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,error.value.run_id).status == 'FAILED'
    assert counts(engine) == (1,1,1,0)


@pytest.mark.parametrize('fault',['uncertain','programming','known_failed'])
def test_commit_classifier_preserved_and_no_fake_outcome(setup,monkeypatch,fault):
    import app.application.use_cases.forecast_trained_execution as module
    engine,prepared,cases,identity = setup
    real_commit = module._commit
    calls = 0
    def inject(session):
        nonlocal calls
        calls += 1
        if calls != 2:
            return real_commit(session)
        if fault == 'known_failed':
            raise OperationalError(None,None,psycopg.errors.SerializationFailure('injected 40001'))
        if fault == 'programming':
            def reject(*args):
                raise ValueError('after durable commit')
            event.listen(session,'after_commit',reject,once=True)
            return real_commit(session)
        original = session.commit
        def lost_ack():
            original()
            raise OperationalError(None,None,psycopg.OperationalError('typed lost ack injection'),
                                   connection_invalidated=True)
        monkeypatch.setattr(session,'commit',lost_ack)
        return real_commit(session)
    monkeypatch.setattr(module,'_commit',inject)
    if fault == 'uncertain':
        result = cases.execute(prepared.request,identity)
        assert result.status == 'COMPLETED' and counts(engine)==(1,1,1,14)
    else:
        with pytest.raises(ForecastExecutionError) as error:
            cases.execute(prepared.request,identity)
        expected = 'COMPLETED' if fault=='programming' else 'FAILED'
        assert error.value.outcome == expected
        with Session(engine) as fresh:
            assert fresh.get(ForecastRun,error.value.run_id).status == expected
        assert counts(engine)==(1,1,1,14 if expected=='COMPLETED' else 0)


def test_store_scoped_metadata_read_and_terminal_update_rejected(setup):
    engine,prepared,cases,identity = setup
    result = cases.execute(prepared.request,identity)
    with Session(engine) as fresh:
        assert ForecastExecutionMetadataRepository(fresh).get(uuid4(),result.id) is None
    with Session(engine) as writer,writer.begin():
        with pytest.raises(ValueError):
            ForecastExecutionMetadataRepository(writer).complete_details(prepared.request.store_id,result.id,{})


def test_postprocessing_warnings_and_counts_are_durable(setup,monkeypatch):
    import lightgbm as lgb
    import numpy as np
    engine,prepared,cases,identity = setup
    calls = 0
    def predict(self,matrix,**kwargs):
        nonlocal calls
        value = (-1.,3.,1.)[calls % 3]
        calls += 1
        return np.full(len(matrix),value)
    monkeypatch.setattr(lgb.Booster,'predict',predict)
    result = cases.execute(prepared.request,identity)
    assert all((p.p25,p.p50,p.p75)==(Decimal(0),Decimal(1),Decimal(3)) for p in result.predictions)
    details = cases.get_with_metadata(reference(prepared,result.id)).execution
    assert details.raw_crossings == 14 and details.negative_values == 14
    assert details.warnings[0].code == 'QUANTILE_POSTPROCESSING'
    with Session(engine) as fresh:
        row = fresh.get(ForecastExecutionMetadata,result.id)
        assert row.details_json['raw_crossings'] == 14 and row.details_json['negative_values'] == 14
        assert row.details_json['warnings'][0]['impact'] == details.warnings[0].impact


def test_completion_failure_after_actual_prediction_flush_rolls_back_metadata_and_predictions(setup,monkeypatch):
    from app.repositories.forecast import ForecastRepository
    engine,prepared,cases,identity = setup
    def reject(repo,*args,**kwargs):
        repo._session.flush()
        assert repo._session.scalar(select(func.count()).select_from(ForecastPrediction)) == 14
        raise ValueError('injected failure after actual DB inserts')
    monkeypatch.setattr(ForecastRepository,'mark_completed',reject)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.outcome == 'FAILED' and isinstance(error.value.__cause__,ValueError)
    assert counts(engine) == (1,1,1,0)
    with Session(engine) as fresh:
        assert fresh.get(ForecastExecutionMetadata,error.value.run_id).details_json['raw_crossings'] == 0


def test_no_history_rejects_before_durable_start(setup):
    from app.domain.forecasting.baseline import BaselineNotReadyError
    engine,prepared,cases,identity = setup
    with Session(engine) as writer,writer.begin():
        writer.execute(SalesDaily.__table__.delete())
    with pytest.raises(BaselineNotReadyError):
        cases.execute(prepared.request,identity)
    assert counts(engine) == (0,0,0,0)


def test_start_lost_ack_reports_durable_run_id_and_records_failure(setup,monkeypatch):
    import app.application.use_cases.forecast_trained_execution as module
    engine,prepared,cases,identity = setup
    real_commit = module._commit
    calls = 0
    def inject(session):
        nonlocal calls
        calls += 1
        if calls == 1:
            original = session.commit
            def lost_ack():
                original()
                raise OperationalError(None,None,psycopg.OperationalError('typed injection'),connection_invalidated=True)
            monkeypatch.setattr(session,'commit',lost_ack)
        return real_commit(session)
    monkeypatch.setattr(module,'_commit',inject)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.outcome == 'FAILED'
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,error.value.run_id).status == 'FAILED'
    assert counts(engine) == (1,1,1,0)


def test_failure_recording_error_reports_actual_running_outcome_and_primary(setup,monkeypatch):
    engine,prepared,cases,identity = setup
    primary = ValueError('compute failed')
    def reject(*args):
        raise primary
    def reject_record(*args):
        raise OSError('recording failed')
    monkeypatch.setattr(cases,'_compute',reject)
    monkeypatch.setattr(cases,'_record_failure',reject_record)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.outcome == 'RUNNING' and error.value.__cause__ is primary
    assert any('failure recording' in note for note in primary.__notes__)
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,error.value.run_id).status == 'RUNNING'


def test_unrecognized_artifact_loader_bug_never_falls_back(setup,monkeypatch):
    engine,prepared,cases,identity = setup
    def reject(*args):
        raise ValueError('loader programming bug')
    monkeypatch.setattr(cases.artifacts,'load',reject)
    with pytest.raises(ValueError,match='loader programming bug'):
        cases.execute(prepared.request,identity)
    assert counts(engine)==(0,0,0,0)


def test_uncertain_commit_requires_exact_metadata_as_well_as_predictions(setup,monkeypatch):
    import app.application.use_cases.forecast_trained_execution as module
    engine,prepared,cases,identity = setup
    real_commit = module._commit
    calls = 0
    def inject(session):
        nonlocal calls
        calls += 1
        if calls != 2:
            return real_commit(session)
        original = session.commit
        def lost_ack_with_corruption():
            original()
            with Session(engine) as writer,writer.begin():
                row = writer.scalar(select(ForecastExecutionMetadata))
                row.details_json = row.details_json | {'negative_values':999}
            raise OperationalError(None,None,psycopg.OperationalError('typed injection'),connection_invalidated=True)
        monkeypatch.setattr(session,'commit',lost_ack_with_corruption)
        return real_commit(session)
    monkeypatch.setattr(module,'_commit',inject)
    with pytest.raises(ForecastExecutionError) as error:
        cases.execute(prepared.request,identity)
    assert error.value.code=='COMPLETED_VERIFICATION_FAILED' and error.value.outcome=='COMPLETED'
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,error.value.run_id).status=='COMPLETED'
    assert counts(engine)==(1,1,1,14)
