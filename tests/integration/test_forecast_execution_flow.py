"""Frozen S2.3 real PostgreSQL capture/retention/execution acceptance."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases, ForecastExecutionError
from app.application.forecast_serialization import RetainedInputError, serialize_prepared
from app.infrastructure.database.engine import create_database_engine
from app.models import Store, Product, SalesDaily, ForecastRun, ForecastPrediction, ForecastRunInput
from app.domain.forecasting.baseline import BaselineNotReadyError
from app.repositories.forecast_input import ForecastInputRepository
from app.repositories.sales import SalesRepository
from app.repositories.forecast import ForecastRepository
from app.application.use_cases.forecast import ForecastUseCases
from app.application.contracts.forecast import StartForecastRunInput
from datetime import datetime, timezone
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy import event
import psycopg
from scripts.dev import migration_config
from app.infrastructure.database.base import Base


def lost_ack():
    # Typed fault injection, not a real network interruption. SQLAlchemy's
    # psycopg dialect sets connection_invalidated on a broken/closed connection.
    return OperationalError(None, None, psycopg.OperationalError('injected transport failure'),
                            connection_invalidated=True)


@pytest.fixture
def setup(database_settings):
    engine = create_database_engine(database_settings)
    store, a, b, other = (uuid4() for _ in range(4))
    with Session(engine) as session, session.begin():
        session.add_all([Store(id=store, name='S2.3'), Store(id=other, name='Other')])
        session.flush()
        session.add_all([Product(id=a, store_id=store, name='A', selling_unit='cup', active=False),
                         Product(id=b, store_id=store, name='B', selling_unit='piece')])
        session.flush()
        session.add_all([SalesDaily(store_id=store, product_id=p, sales_date=day, quantity=q)
                         for p in (a,b) for day,q in [(date(2026,9,7),Decimal('10.00')),
                          (date(2026,9,9),Decimal('0')), (date(2026,8,1),Decimal('999'))]])
    request = ForecastExecutionInput(store_id=store, product_ids=(b,a),
        cutoff_date=date(2026,9,11), history_start_date=date(2026,9,7))
    try: yield engine, request, other
    finally: engine.dispose()


def ref(request, run_id):
    return RunReferenceInput(store_id=request.store_id, run_id=run_id)


def counts(engine):
    with Session(engine) as fresh:
        return tuple(fresh.scalar(select(func.count()).select_from(m))
                     for m in (ForecastRun, ForecastRunInput, ForecastPrediction))


def test_capture_execute_fresh_session_and_no_transaction_during_math(setup, monkeypatch):
    engine, request, _ = setup
    cases = ForecastExecutionUseCases(engine)
    prepared = cases.capture(request)
    assert len(prepared.observations) == 4 and all(r.quantity in (Decimal('0'),Decimal('10')) for r in prepared.observations)
    import app.application.use_cases.forecast_execution as execution
    real = execution.run_historical_quantile_baseline
    def probe(data):
        assert engine.pool.checkedout() == 0
        with Session(engine) as observer:
            observer.execute(text("SET LOCAL lock_timeout='100ms'"))
            observer.execute(select(ForecastRun).with_for_update()).all()
        return real(data)
    monkeypatch.setattr(execution, 'run_historical_quantile_baseline', probe)
    result = cases.execute(request)
    assert result.status == 'COMPLETED' and len(result.predictions) == 14
    assert result.model_type == 'historical_quantile_baseline' and result.model_version == '1'
    assert result.artifact_key is None and result.metrics_json is None
    assert all((p.p25,p.p50,p.p75)==(Decimal('2.5'),Decimal('5'),Decimal('7.5')) for p in result.predictions)
    with Session(engine) as fresh:
        row = fresh.get(ForecastRun, result.id)
        stored = fresh.get(ForecastRunInput, result.id)
        assert row.status == 'COMPLETED' and row.input_fingerprint == stored.digest
        assert len(fresh.scalars(select(ForecastPrediction)).all()) == 14
        assert stored.prepared_json['observations'][0]['quantity'] in ('0','10')
    assert cases.load_retained(ref(request,result.id)) == prepared


def test_read_only_repeatable_snapshot_between_selects(setup, monkeypatch):
    engine, request, _ = setup
    original = SalesRepository.get_sales_history
    changed = []
    def interleave(repo, *args):
        assert repo._session.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
        assert repo._session.scalar(text('SHOW transaction_read_only')) == 'on'
        if not changed:
            changed.append(True)
            with Session(engine) as writer, writer.begin():
                writer.get(Store,request.store_id).timezone = 'UTC'
                for p in request.product_ids: writer.get(Product,p).selling_unit = 'changed'
                for row in writer.scalars(select(SalesDaily)): row.quantity = Decimal('777')
                writer.add(SalesDaily(store_id=request.store_id,product_id=request.product_ids[0],
                                     sales_date=date(2026,9,8),quantity=Decimal('3')))
        return original(repo,*args)
    monkeypatch.setattr(SalesRepository,'get_sales_history',interleave)
    data = ForecastExecutionUseCases(engine).capture(request)
    assert data.timezone == 'Asia/Ho_Chi_Minh' and len(data.observations)==4
    assert all(p.selling_unit != 'changed' for p in data.products)
    assert {r.quantity for r in data.observations} == {Decimal('0'),Decimal('10')}


@pytest.mark.parametrize('kind',['wrong_store','missing'])
def test_capture_scope_rejected_without_run(setup, kind):
    engine, request, other = setup
    invalid = request.model_copy(update={'store_id':other} if kind=='wrong_store' else {'product_ids':(uuid4(),)})
    with pytest.raises(ApplicationError) as caught: ForecastExecutionUseCases(engine).execute(invalid)
    assert caught.value.category == ErrorCategory.NOT_FOUND and counts(engine)==(0,0,0)


def test_no_history_preflight_no_durable_start(setup):
    engine, request, _ = setup
    with Session(engine) as writer, writer.begin(): writer.execute(SalesDaily.__table__.delete())
    with pytest.raises(BaselineNotReadyError): ForecastExecutionUseCases(engine).execute(request)
    assert counts(engine)==(0,0,0)


def test_replay_retained_not_operational_and_new_uuid(setup):
    engine, request, other = setup
    cases = ForecastExecutionUseCases(engine)
    first = cases.execute(request)
    with Session(engine) as writer, writer.begin():
        writer.get(Store,request.store_id).timezone='UTC'
        for p in request.product_ids: writer.get(Product,p).selling_unit='changed'
        for sale in writer.scalars(select(SalesDaily)): sale.quantity=Decimal('100')
    replay = cases.replay(ref(request,first.id))
    assert all(p.p50 == Decimal('5') for p in replay.predictions)
    second = cases.replay_persisted(ref(request,first.id))
    assert second.id != first.id and second.input_fingerprint == first.input_fingerprint
    assert cases.get(ref(request,first.id)) == first
    current = cases.execute(request)
    assert current.input_fingerprint != first.input_fingerprint and current.predictions[0].p50==Decimal('100')
    with pytest.raises(ApplicationError): cases.load_retained(RunReferenceInput(store_id=other,run_id=first.id))


@pytest.mark.parametrize('kind',['digest','version','payload'])
def test_retained_integrity_rejected(setup, kind):
    engine, request, _ = setup
    cases = ForecastExecutionUseCases(engine); result=cases.execute(request)
    with Session(engine) as writer, writer.begin():
        row=writer.get(ForecastRunInput,result.id)
        if kind=='digest': row.digest='0'*64
        elif kind=='version': row.serialization_version=2
        else: row.prepared_json={'invalid':'payload'}
    with pytest.raises(RetainedInputError): cases.replay(ref(request,result.id))


def test_start_after_flush_failure_atomic(setup, monkeypatch):
    engine, request, _ = setup
    def broken(repo, store_id, row):
        repo._session.add(row); repo._session.flush()
        raise RuntimeError('secret injected start failure')
    monkeypatch.setattr(ForecastInputRepository,'add_input',broken)
    with pytest.raises(ForecastExecutionError) as caught: ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.outcome == 'NOT_STARTED' and isinstance(caught.value.__cause__, RuntimeError)
    assert counts(engine)==(0,0,0)


@pytest.mark.parametrize('kind',['coverage','metadata','compute'])
def test_failure_after_start_no_predictions_retains_input(setup, monkeypatch, kind):
    engine, request, _ = setup
    import app.application.use_cases.forecast_execution as execution
    real=execution.run_historical_quantile_baseline
    def broken(prepared):
        if kind=='compute': raise RuntimeError('secret raw exception')
        result=real(prepared)
        return result.model_copy(update={'predictions':result.predictions[:-1]} if kind=='coverage' else {'model_type':'fake'})
    monkeypatch.setattr(execution,'run_historical_quantile_baseline',broken)
    with pytest.raises(ForecastExecutionError) as caught: ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.run_id is not None and caught.value.outcome=='FAILED'
    with Session(engine) as fresh:
        run=fresh.get(ForecastRun,caught.value.run_id)
        assert run.status=='FAILED' and 'secret' not in run.error_summary
        assert fresh.get(ForecastRunInput,run.id) is not None
    assert counts(engine)==(1,1,0)


def test_completion_downstream_failure_after_real_prediction_flush(setup, monkeypatch):
    engine, request, _ = setup
    real = ForecastRepository.mark_completed
    def broken(repo, *args, **kwargs):
        repo._session.flush()
        assert repo._session.scalar(select(func.count()).select_from(ForecastPrediction)) == 14
        result = real(repo,*args,**kwargs)
        result.model_type = ''
        return result
    monkeypatch.setattr(ForecastRepository,'mark_completed',broken)
    with pytest.raises(ForecastExecutionError) as caught: ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.outcome=='FAILED' and counts(engine)==(1,1,0)


@pytest.mark.parametrize('phase',['start','completion'])
@pytest.mark.parametrize('committed',[False,True])
def test_commit_failure_reconciled_real_state(setup, monkeypatch, phase, committed):
    engine, request, _ = setup
    real = Session.commit
    calls=[]
    def faulty(session):
        calls.append(True)
        if len(calls)==(1 if phase=='start' else 2):
            if committed: real(session)
            raise lost_ack()
        return real(session)
    monkeypatch.setattr(Session,'commit',faulty)
    cases=ForecastExecutionUseCases(engine)
    if phase=='completion' and committed:
        result=cases.execute(request)
        assert result.status=='COMPLETED' and counts(engine)==(1,1,14)
    else:
        with pytest.raises(ForecastExecutionError) as caught: cases.execute(request)
        if phase=='start' and not committed:
            assert caught.value.outcome=='NOT_STARTED' and counts(engine)==(0,0,0)
        else:
            assert caught.value.outcome=='FAILED' and counts(engine)==(1,1,0)


@pytest.mark.parametrize('kind',['failure_recording','unknown','programming_after_commit'])
def test_no_false_success_or_status(setup, monkeypatch, kind):
    engine, request, _ = setup
    cases=ForecastExecutionUseCases(engine)
    if kind=='programming_after_commit':
        real=cases._complete
        def broken(*args):
            real(*args)
            raise RuntimeError('programming error after commit')
        monkeypatch.setattr(cases,'_complete',broken)
    else:
        def broken(*args): raise RuntimeError('injected computation/validation error')
        monkeypatch.setattr(cases,'_complete',broken)
        if kind=='unknown': monkeypatch.setattr(cases,'get',broken)
        else: monkeypatch.setattr(cases,'_record_failure',broken)
    with pytest.raises(ForecastExecutionError) as caught: cases.execute(request)
    assert caught.value.run_id is not None
    assert caught.value.outcome == {'failure_recording':'RUNNING','unknown':'UNKNOWN','programming_after_commit':'COMPLETED'}[kind]
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,caught.value.run_id).status == ('COMPLETED' if kind=='programming_after_commit' else 'RUNNING')


def test_committed_completion_unknown_when_reconciliation_unavailable(setup, monkeypatch):
    engine, request, _ = setup
    cases=ForecastExecutionUseCases(engine)
    real=Session.commit
    calls=[]
    def faulty(session):
        calls.append(True); real(session)
        if len(calls)==2: raise lost_ack()
    def unavailable(*args): raise RuntimeError('read unavailable')
    monkeypatch.setattr(Session,'commit',faulty)
    monkeypatch.setattr(cases,'get',unavailable)
    with pytest.raises(ForecastExecutionError) as caught: cases.execute(request)
    assert caught.value.outcome=='UNKNOWN'
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,caught.value.run_id).status=='COMPLETED'
    assert counts(engine)==(1,1,14)


def test_failure_recording_commit_ack_loss_reports_actual_failed(setup, monkeypatch):
    engine, request, _ = setup
    cases=ForecastExecutionUseCases(engine)
    real=Session.commit
    calls=[]
    def faulty(session):
        calls.append(True); real(session)
        if len(calls)==2: raise lost_ack()
    def broken(*args): raise RuntimeError('computation error')
    monkeypatch.setattr(Session,'commit',faulty)
    monkeypatch.setattr(cases,'_complete',broken)
    with pytest.raises(ForecastExecutionError) as caught: cases.execute(request)
    assert caught.value.outcome=='FAILED' and caught.value.code=='FAILURE_RECORDING_FAILED'
    with Session(engine) as fresh: assert fresh.get(ForecastRun,caught.value.run_id).status=='FAILED'
    assert counts(engine)==(1,1,0)


def test_s1_missing_retention_and_persisted_replay_missing_product(setup):
    engine, request, _ = setup
    cases=ForecastExecutionUseCases(engine)
    with Session(engine) as session:
        legacy=ForecastUseCases(session).start(StartForecastRunInput(store_id=request.store_id,
            training_start_date=request.history_start_date,training_end_date=request.cutoff_date,
            forecast_start_date=date(2026,9,12),forecast_end_date=date(2026,9,18),
            model_type='fixture',model_version='1',started_at=datetime.now(timezone.utc)))
    with pytest.raises(RetainedInputError) as caught: cases.replay(ref(request,legacy.id))
    assert caught.value.code=='RETAINED_INPUT_UNAVAILABLE'
    prepared=cases.capture(request)
    encoded=serialize_prepared(prepared)
    identifier=uuid4()
    cases._start(identifier,prepared,encoded)
    with Session(engine) as writer, writer.begin():
        writer.execute(SalesDaily.__table__.delete())
        writer.execute(Product.__table__.delete())
    assert len(cases.replay(ref(request,identifier)).predictions)==14
    with pytest.raises(ApplicationError): cases.replay_persisted(ref(request,identifier))
    assert counts(engine)==(2,1,0)


def test_migration_roundtrip_retention_loss_only_and_metadata(setup):
    engine,request,_=setup
    result=ForecastExecutionUseCases(engine).execute(request)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection,opts={'compare_server_default':True}),Base.metadata)==[]
    command.downgrade(migration_config(),'0006_forecast_decision_persist')
    assert 'forecast_run_inputs' not in inspect(engine).get_table_names()
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun,result.id).status=='COMPLETED'
        assert fresh.scalar(select(func.count()).select_from(ForecastPrediction))==14
    command.upgrade(migration_config(),'head')
    assert counts(engine)==(1,0,14)
    with pytest.raises(RetainedInputError): ForecastExecutionUseCases(engine).load_retained(ref(request,result.id))


@pytest.mark.parametrize('kind',['store_fk','object','version','digest','duplicate'])
def test_retention_database_constraints_and_no_partial_changes(setup,kind):
    engine,request,other=setup
    cases=ForecastExecutionUseCases(engine); result=cases.execute(request)
    with Session(engine) as writer:
        existing=writer.get(ForecastRunInput,result.id)
        if kind=='duplicate':
            writer.expunge(existing)
            writer.add(ForecastRunInput(forecast_run_id=result.id,store_id=request.store_id,
                prepared_json={},serialization_version=1,digest='a'*64))
        elif kind=='store_fk': existing.store_id=other
        elif kind=='object': existing.prepared_json=[]
        elif kind=='version': existing.serialization_version=0
        else: existing.digest='invalid'
        with pytest.raises(IntegrityError): writer.commit()
        writer.rollback()
    assert cases.load_retained(ref(request,result.id))==cases.capture(request)


@pytest.mark.parametrize('phase', ['start', 'completion'])
@pytest.mark.parametrize('committed', [False, True])
def test_commit_primary_survives_rollback_and_close_errors(setup, monkeypatch, caplog, phase, committed):
    engine, request, _ = setup
    real_commit, real_rollback, real_close = Session.commit, Session.rollback, Session.close
    primary = lost_ack()
    target = []
    calls = []
    def commit(session):
        calls.append(session)
        if len(calls) == (1 if phase == 'start' else 2):
            target.append(session)
            if committed:
                real_commit(session)
            raise primary
        return real_commit(session)
    def rollback(session):
        if target and session is target[0]:
            raise ValueError('secondary rollback bug')
        return real_rollback(session)
    def close(session):
        if target and session is target[0]:
            raise ValueError('secondary close bug')
        return real_close(session)
    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(Session, 'rollback', rollback)
    monkeypatch.setattr(Session, 'close', close)
    cases = ForecastExecutionUseCases(engine)
    if phase == 'completion' and committed:
        result = cases.execute(request)
        assert result.status == 'COMPLETED' and counts(engine) == (1, 1, 14)
    else:
        with pytest.raises(ForecastExecutionError) as caught:
            cases.execute(request)
        expected = 'NOT_STARTED' if phase == 'start' and not committed else 'FAILED'
        assert caught.value.outcome == expected and caught.value.run_id is not None
        assert caught.value.__cause__.__cause__ is primary
        assert any('rollback' in n for n in caught.value.__cause__.__notes__)
        assert any('close' in n for n in caught.value.__cause__.__notes__)
        assert counts(engine) == ((0, 0, 0) if expected == 'NOT_STARTED' else (1, 1, 0))
    assert 'rollback' in caplog.text and 'close' in caplog.text
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize('phase', ['start', 'completion'])
@pytest.mark.parametrize('cleanup', [False, True])
def test_programming_inside_commit_never_success(setup, monkeypatch, phase, cleanup):
    engine, request, _ = setup
    real_commit, real_close = Session.commit, Session.close
    primary = ValueError('post-commit instrumentation bug')
    calls, target = [], []
    def commit(session):
        calls.append(session)
        real_commit(session)
        if len(calls) == (1 if phase == 'start' else 2):
            target.append(session)
            raise primary
    def close(session):
        real_close(session)
        if cleanup and target and session is target[0]:
            raise RuntimeError('secondary close bug')
    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(Session, 'close', close)
    with pytest.raises(ForecastExecutionError) as caught:
        ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.__cause__ is primary
    assert caught.value.run_id is not None
    expected = 'FAILED' if phase == 'start' else 'COMPLETED'
    assert caught.value.outcome == expected
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, caught.value.run_id).status == expected
        assert fresh.get(ForecastRunInput, caught.value.run_id) is not None
    assert counts(engine) == (1, 1, 0 if phase == 'start' else 14)


@pytest.mark.parametrize('phase', ['start', 'completion'])
def test_close_failure_after_acknowledged_commit_reports_run(setup, monkeypatch, phase):
    engine, request, _ = setup
    real_commit, real_close = Session.commit, Session.close
    primary = ValueError('close instrumentation bug')
    calls, target = [], []
    def commit(session):
        calls.append(session)
        real_commit(session)
        if len(calls) == (1 if phase == 'start' else 2):
            target.append(session)
    def close(session):
        real_close(session)
        if target and session is target[0]:
            raise primary
    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(Session, 'close', close)
    with pytest.raises(ForecastExecutionError) as caught:
        ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.__cause__ is primary and caught.value.run_id is not None
    assert caught.value.outcome == ('FAILED' if phase == 'start' else 'COMPLETED')
    assert counts(engine) == (1, 1, 0 if phase == 'start' else 14)


def test_known_transaction_failure_is_not_uncertain_even_with_disconnect_flag(setup, monkeypatch):
    engine, request, _ = setup
    real_commit = Session.commit
    calls = []
    primary = OperationalError(None, None, psycopg.errors.SerializationFailure(), connection_invalidated=True)
    def commit(session):
        calls.append(session)
        if len(calls) == 2:
            raise primary
        return real_commit(session)
    monkeypatch.setattr(Session, 'commit', commit)
    with pytest.raises(ForecastExecutionError) as caught:
        ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.__cause__ is primary and caught.value.outcome == 'FAILED'
    assert counts(engine) == (1, 1, 0)


@pytest.mark.parametrize('committed', [False, True])
def test_failure_recording_and_cleanup_keep_execution_cause_and_actual_state(setup, monkeypatch, committed):
    engine, request, _ = setup
    cases = ForecastExecutionUseCases(engine)
    primary = ValueError('original computation bug')
    recording = lost_ack()
    real_commit, real_rollback, real_close = Session.commit, Session.rollback, Session.close
    calls, target = [], []
    def broken(*_args):
        raise primary
    def commit(session):
        calls.append(session)
        if len(calls) == 2:
            target.append(session)
            if committed:
                real_commit(session)
            raise recording
        return real_commit(session)
    def rollback(session):
        if target and session is target[0]:
            raise RuntimeError('rollback bug')
        return real_rollback(session)
    def close(session):
        if target and session is target[0]:
            raise RuntimeError('close bug')
        return real_close(session)
    monkeypatch.setattr(cases, '_complete', broken)
    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(Session, 'rollback', rollback)
    monkeypatch.setattr(Session, 'close', close)
    with pytest.raises(ForecastExecutionError) as caught:
        cases.execute(request)
    assert caught.value.__cause__ is primary
    assert any('failure recording' in n for n in primary.__notes__)
    expected = 'FAILED' if committed else 'RUNNING'
    assert caught.value.outcome == expected and caught.value.code == 'FAILURE_RECORDING_FAILED'
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, caught.value.run_id).status == expected
        assert fresh.get(ForecastRunInput, caught.value.run_id) is not None
    assert counts(engine) == (1, 1, 0) and engine.pool.checkedout() == 0


@pytest.mark.parametrize('phase', ['start', 'completion'])
def test_postgresql_after_commit_callback_error_keeps_durable_state(setup, monkeypatch, phase):
    engine, request, _ = setup
    real_commit = Session.commit
    calls = []
    primary = ValueError('actual after_commit callback bug')
    def broken(_session):
        raise primary
    def commit(session):
        calls.append(session)
        if len(calls) == (1 if phase == 'start' else 2):
            event.listen(session, 'after_commit', broken)
        return real_commit(session)
    monkeypatch.setattr(Session, 'commit', commit)
    with pytest.raises(ForecastExecutionError) as caught:
        ForecastExecutionUseCases(engine).execute(request)
    assert caught.value.__cause__ is primary
    assert any('rollback' in n and 'InvalidRequestError' in n for n in primary.__notes__)
    expected = 'FAILED' if phase == 'start' else 'COMPLETED'
    assert caught.value.outcome == expected and caught.value.run_id is not None
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, caught.value.run_id).status == expected
    assert counts(engine) == (1, 1, 0 if phase == 'start' else 14)
    assert engine.pool.checkedout() == 0


def test_server_reported_transaction_rollback_is_not_lost_ack(setup, monkeypatch):
    engine, request, _ = setup
    real_commit = Session.commit
    calls = []
    def commit(session):
        calls.append(session)
        if len(calls) == 2:
            # Real PostgreSQL error/driver wrapping, deterministic injection of a
            # server rollback condition; not a concurrent serialization conflict.
            session.execute(text("DO $$ BEGIN RAISE EXCEPTION USING ERRCODE = '40001'; END $$"))
        return real_commit(session)
    monkeypatch.setattr(Session, 'commit', commit)
    with pytest.raises(ForecastExecutionError) as caught:
        ForecastExecutionUseCases(engine).execute(request)
    assert isinstance(caught.value.__cause__, OperationalError)
    assert isinstance(caught.value.__cause__.orig, psycopg.errors.SerializationFailure)
    assert caught.value.outcome == 'FAILED' and counts(engine) == (1, 1, 0)


def test_uncertain_completion_requires_full_aggregate_verification(setup, monkeypatch):
    engine, request, _ = setup
    cases = ForecastExecutionUseCases(engine)
    real_commit, real_verify = Session.commit, cases._verify_completed
    calls = []
    primary = lost_ack()
    def commit(session):
        calls.append(session)
        real_commit(session)
        if len(calls) == 2:
            raise primary
    def corrupted(*args):
        # Privileged DB corruption to exercise the verification guard only.
        with Session(engine) as writer, writer.begin():
            row = writer.scalars(select(ForecastPrediction)).first()
            row.p25 = row.p50 = row.p75 = Decimal('99')
        return real_verify(*args)
    monkeypatch.setattr(Session, 'commit', commit)
    monkeypatch.setattr(cases, '_verify_completed', corrupted)
    with pytest.raises(ForecastExecutionError) as caught:
        cases.execute(request)
    assert caught.value.code == 'COMPLETED_VERIFICATION_FAILED' and caught.value.outcome == 'COMPLETED'
    assert caught.value.__cause__.__cause__ is primary
    with Session(engine) as fresh:
        assert fresh.get(ForecastRun, caught.value.run_id).status == 'COMPLETED'
    assert counts(engine) == (1, 1, 14)
