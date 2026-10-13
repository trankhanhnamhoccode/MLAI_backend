"""Real guarded shelfcash_test persistence/lifecycle, synthetic business values."""
from sqlalchemy.engine import make_url
from tests.planning_process_cases import child_claim
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import multiprocessing
from threading import Barrier
from uuid import uuid4
import pytest
import psycopg
from alembic import command
from sqlalchemy import select, func, inspect, text, Table, MetaData
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.models import (PlanningRun,User,Store,Product,Ingredient,Supplier,SupplierTerm,Recipe,RecipeLine,
    InventoryLot,ForecastRun,ForecastPrediction,ForecastRunInput,DecisionRun)
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.database.decision_capture_v2 import PostgresDecisionSnapshotSourceV2
from app.application.forecast_serialization import serialize_prepared
from app.application.contracts.planning_run import PlanningPersistenceError
from app.application.planning_serialization import canonical_bytes,digest
from app.application.use_cases.planning_run import PlanningRunUseCases
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.infrastructure.planning_process import current_process
from scripts.dev import migration_config
from tests.planning_persistence_cases import case,computation


@pytest.fixture
def db(database_settings):
    engine=create_database_engine(database_settings)
    with engine.connect() as c:assert c.scalar(text('select current_database()')) == make_url(database_settings.database_url).database
    request,resolution,_,_,_=case()
    actor=uuid4();store=resolution.configuration.store_id
    with Session(engine) as s,s.begin():
        s.add_all([Store(id=store,name='S364 SYNTHETIC',timezone='UTC',currency='VND'),
            User(id=actor,email='planning@example.test',password_hash='test-only',display_name='Planner')])
    try:yield engine,PlanningRunUseCases(engine),actor,store
    finally:engine.dispose()


def accept(db,key='key',kind='stock'):
    engine,service,actor,store=db
    request,resolution,decl,source,factory=case(kind)
    record=service.accept(actor,store,key,request,resolution)
    return record,decl,source,factory


def seed_facts(engine,source,*,historical_recipe_schema=False):
    f=source.facts.facts;catalog={p.product_id:p for p in source.facts.catalog}
    with Session(engine) as s,s.begin():
        s.add_all([Product(id=p.product_id,store_id=p.store_id,name=catalog[p.product_id].name,
            selling_unit=p.selling_unit,sku=p.sku) for p in f.products])
        s.add_all([Ingredient(id=i.ingredient_id,store_id=i.store_id,name='Synthetic ingredient',
            base_unit=i.unit,expiry_tracking=i.expiry_tracking) for i in f.ingredients])
        s.add_all([Supplier(id=i,store_id=f.store.id,name='Synthetic supplier') for i in {t.supplier_id for t in f.supplier_terms}])
        s.flush()
        if historical_recipe_schema:
            # Migration0008 predates assigned (0015). Use its reflected table,
            # never the current ORM's INSERT/RETURNING shape against old schema.
            recipe_table=Table('recipes',MetaData(),autoload_with=s.connection())
            assert 'assigned' not in recipe_table.c
        for r in f.recipes:
            if historical_recipe_schema:
                s.execute(recipe_table.insert().values(**r.model_dump(exclude={'lines'})))
            else:
                s.add(Recipe(**r.model_dump(exclude={'lines'})));s.flush()
            s.add_all([RecipeLine(id=uuid4(),store_id=f.store.id,recipe_id=r.id,**l.model_dump()) for l in r.lines])
        s.add_all([SupplierTerm(**t.model_dump()) for t in f.supplier_terms])
        s.add_all([InventoryLot(**l.model_dump()) for l in f.lots])
        fc=f.forecast
        s.add(ForecastRun(id=fc.id,store_id=fc.store_id,status=fc.status,training_start_date=fc.training_start_date,
            training_end_date=fc.training_end_date,forecast_start_date=fc.forecast_start_date,forecast_end_date=fc.forecast_end_date,
            model_type=fc.model_type,model_version=fc.model_version,started_at=fc.completed_at-timedelta(hours=1),
            completed_at=fc.completed_at,input_fingerprint=fc.input_fingerprint));s.flush()
        import json
        encoded=serialize_prepared(fc.retained)
        s.add(ForecastRunInput(forecast_run_id=fc.id,store_id=fc.store_id,prepared_json=json.loads(encoded.canonical_json),
            serialization_version=encoded.serialization_version,digest=encoded.digest))
        s.add_all([ForecastPrediction(**p.model_dump()) for p in fc.predictions])


@pytest.mark.parametrize('kind,status,outcome',[
    ('stock','completed','recommendation_available'),('purchase','completed','recommendation_available'),
    ('infeasible','completed','no_eligible_candidate'),('partial','failed','execution_error')])
def test_pg_actual_capture_pipeline_retained_roundtrip_without_live_read(db,monkeypatch,record_property,kind,status,outcome):
    engine,service,actor,store=db
    record,decl,source,factory=accept(db,kind=kind);seed_facts(engine,source)
    checks=[]
    def search(*args):
        assert engine.pool.checkedout()==0
        # Capture has durably committed BEFORE solver is entered.
        saved=service.read(store,record.run_id).record
        assert saved.status=='running' and saved.capture is not None
        assert engine.pool.checkedout()==0
        checks.append(True);return factory(*args)
    final=service.execute(store,record.run_id,decl,PostgresDecisionSnapshotSourceV2(engine),search,
                          lambda:source.facts.facts.captured_at)
    assert (final.status,final.outcome)==(status,outcome)
    assert final.capture.source is not None and final.result.capture==final.capture
    assert final.result.timing.capture_preparation_seconds>0
    if kind=='stock':
        option=next(o for o in final.result.comparison.options if o.token==final.result.selection.winner_token)
        assert option.outlay.total.numerator=='0'
    if kind=='purchase':assert checks and final.result.selection.winner_token
    if kind=='partial':assert checks and final.result.selection.winner_token
    assert engine.pool.checkedout()==0
    # Change current operational facts; fresh read must stay identical.
    with Session(engine) as s,s.begin():
        s.get(InventoryLot,source.facts.facts.lots[0].id).on_hand_quantity=999
    from app.application.use_cases import decision_pipeline_v2
    monkeypatch.setattr(decision_pipeline_v2,'execute_captured_pipeline_v2',lambda *a:pytest.fail('read cannot solve'))
    statements=[]
    from sqlalchemy import event
    def watch(c,cursor,statement,params,context,many):statements.append(statement)
    event.listen(engine,'before_cursor_execute',watch)
    try:fresh=service.read(store,record.run_id)
    finally:event.remove(engine,'before_cursor_execute',watch)
    assert canonical_bytes(fresh.record)==canonical_bytes(final)
    assert fresh.integrity_validation_seconds>=0
    record_property('fresh_read_seconds',fresh.integrity_validation_seconds)
    assert len(statements)==1 and 'planning_runs' in statements[0]
    with Session(engine) as s:
        assert s.get(PlanningRun,record.run_id).status==status
        assert not s.scalars(select(DecisionRun)).all()


def test_pg_retry_before_new_config_and_key_conflict_new_uuid(db):
    engine,service,actor,store=db;record,_,_,_=accept(db)
    def never(session):pytest.fail('Retry must not resolve')
    original=record.request
    retried=service.accept(actor,store,'key',original,never)
    assert retried==record and retried.accepted_at==record.accepted_at
    modified=original.model_dump();modified['forecast_start_date']='2026-10-09'
    with pytest.raises(PlanningPersistenceError,match='IDEMPOTENCY_KEY_REUSED'):
        service.accept(actor,store,'key',modified,never)
    second=service.accept(actor,store,'second',original,record.resolution)
    assert second.run_id!=record.run_id
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(PlanningRun))==2


def test_pg_retry_cleanup_reports_existing_run_identity(db,monkeypatch):
    engine,service,actor,store=db;record,_,_,_=accept(db)
    original=Session.close;primary=ValueError('INJECTED retry close')
    def close(s):
        original(s)
        raise primary
    monkeypatch.setattr(Session,'close',close)
    with pytest.raises(PlanningPersistenceError) as error:service.accept(actor,store,'key',record.request)
    assert error.value.code=='ACCEPTANCE_LOOKUP_ERROR'
    assert error.value.run_id==record.run_id and error.value.state=='queued' and error.value.__cause__ is primary
    assert engine.pool.checkedout()==0


@pytest.mark.parametrize('component',['capture','result'])
def test_pg_retained_input_result_semantic_corruption_rejects_after_rehash(db,component):
    engine,service,actor,store=db;record,decl,source,factory=accept(db)
    service.execute(store,record.run_id,decl,source,factory,lambda:source.facts.facts.captured_at)
    with Session(engine) as s,s.begin():
        row=s.get(PlanningRun,record.run_id);body=deepcopy(row.record_json)
        if component=='capture':
            body['capture']['computed_product_ids']=[]
            body['input_digest']=digest('capture',body['capture'])
        else:
            body['result']['outcome']='NO_ELIGIBLE_CANDIDATE'
            body['result_digest']=digest('result',body['result'])
        row.record_json=body;row.record_digest=digest('aggregate',body)
    with pytest.raises(PlanningPersistenceError,match='RESULT_INTEGRITY_UNAVAILABLE'):service.read(store,record.run_id)


def test_pg_actor_store_scope_and_read_isolation(db):
    engine,service,actor,store=db;record,_,_,_=accept(db)
    other_actor=uuid4();other_store=uuid4()
    with Session(engine) as s,s.begin():
        s.add_all([User(id=other_actor,email='other@example.test',password_hash='fixture',display_name='Other'),
                   Store(id=other_store,name='Other')])
    second=service.accept(other_actor,store,'key',record.request,record.resolution)
    assert second.run_id!=record.run_id
    with pytest.raises(PlanningPersistenceError,match='NOT_FOUND'):service.read(other_store,record.run_id)
    with pytest.raises(PlanningPersistenceError):service.accept(actor,other_store,'key',record.request,record.resolution)
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(PlanningRun))==2
    config=record.resolution.configuration.model_dump()
    config['store_id']=other_store
    for product in config['products']:product['store_id']=other_store
    other_resolution=resolve_planning_setup(record.request,config).resolution
    third=service.accept(actor,other_store,'key',record.request,other_resolution)
    assert third.run_id not in {record.run_id,second.run_id}
    assert third.store_id==other_store and third.actor_id==actor


def test_pg_own_sessions_preserve_caller_transaction_and_indefinite_retry(db,monkeypatch):
    engine,service,actor,store=db
    with Session(engine) as caller:
        caller.begin();caller.get(Store,store).name='Caller unflushed WIP'
        with pytest.raises(TypeError,match='requires an Engine'):PlanningRunUseCases(caller)
        with pytest.raises(TypeError,match='requires an Engine'):PlanningRunUseCases(caller.connection())
        assert caller.in_transaction() and caller.dirty
        record,_,_,_=accept(db)
        assert caller.in_transaction() and caller.dirty
        from app.application.use_cases import planning_run as module
        from datetime import datetime,timezone
        monkeypatch.setattr(module,'utc_now',lambda:datetime(2100,1,1,tzinfo=timezone.utc))
        retried=service.accept(actor,store,'key',record.request,lambda s:pytest.fail('no TTL/config reread'))
        assert retried.run_id==record.run_id and retried.accepted_at==record.accepted_at
        caller.rollback()
    with Session(engine) as fresh:assert fresh.get(Store,store).name=='S364 SYNTHETIC'


def test_pg_concurrent_acceptance_one_atomic_aggregate(db):
    engine,service,actor,store=db;r,res,_,_,_=case();barrier=Barrier(2)
    def provider(s):barrier.wait(timeout=20);return res
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(service.accept,actor,store,'race',r,provider) for _ in range(2)]
        runs=[f.result(timeout=40) for f in futures]
    assert runs[0].run_id==runs[1].run_id and runs[0].accepted_at==runs[1].accepted_at
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(PlanningRun))==1


@pytest.mark.parametrize('action',['commit','rollback','dirty'])
def test_pg_resolution_provider_cannot_take_transaction_ownership(db,action):
    engine,service,actor,store=db;r,res,_,_,_=case()
    def provider(s):
        if action=='dirty':s.get(Store,store).name='Unapproved provider write'
        else:getattr(s,action)()
        return res
    with pytest.raises(PlanningPersistenceError) as error:service.accept(actor,store,'provider',r,provider)
    assert error.value.code=='EXECUTION_ERROR' and error.value.run_id
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PlanningRun))==0
        assert fresh.get(Store,store).name=='S364 SYNTHETIC'


@pytest.mark.parametrize('kind',['queued_terminal','start_change'])
def test_pg_repo_transition_guard_rejects_bypassing_claim_or_rewriting_start(db,kind):
    from app.application.contracts.planning_run import PlanningRunRecord,PlanningClaim
    from app.application.use_cases.planning_run import utc_now
    from app.repositories.planning import PlanningRepository
    engine,service,actor,store=db;record,_,_,_=accept(db)
    if kind=='queued_terminal':
        now=utc_now()
        modified={**record.model_dump(round_trip=True),'status':'failed','outcome':'execution_error',
            'started_at':now,'finished_at':now,'error_code':'EXECUTION_ERROR','error_summary':'Synthetic error',
            'claim':PlanningClaim(token=uuid4(),generation=1,process=current_process())}
    else:
        record=service.claim(store,record.run_id)
        modified={**record.model_dump(round_trip=True),'started_at':record.started_at+timedelta(seconds=1)}
    valid=PlanningRunRecord.model_validate(modified)
    with Session(engine) as s,s.begin():
        repo=PlanningRepository(s);row=repo.get(store,record.run_id,lock=True)
        with pytest.raises(PlanningPersistenceError,match='INVALID_TRANSITION|START_IMMUTABLE'):
            repo._replace_locked(row,valid)
    assert service.read(store,record.run_id).record==record


def test_pg_concurrent_claim_and_fenced_terminal_idempotency(db):
    engine,service,actor,store=db;record,decl,source,factory=accept(db);barrier=Barrier(2)
    def claim():
        barrier.wait()
        try:return service.claim(store,record.run_id)
        except PlanningPersistenceError as e:return e
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
    winners=[x for x in results if not isinstance(x,Exception)]
    assert len(winners)==1 and next(x for x in results if isinstance(x,Exception)).code=='NOT_QUEUED'
    owner=winners[0];_,_,decl,capture,result=computation()
    service.retain(store,record.run_id,owner.claim,decl,capture)
    bad=owner.claim.model_copy(update={'token':uuid4()})
    with pytest.raises(PlanningPersistenceError,match='STALE_CLAIM'):service.finalize(store,record.run_id,bad,result)
    final=service.finalize(store,record.run_id,owner.claim,result)
    assert service.finalize(store,record.run_id,owner.claim,result)==final
    # Different diagnostic timing is a different terminal payload, even same winner.
    data=result.model_dump();data['timing']['total_seconds']+=1
    with pytest.raises(PlanningPersistenceError,match='TERMINAL_CONFLICT'):
        service.finalize(store,record.run_id,owner.claim,data)
    with pytest.raises(PlanningPersistenceError,match='TERMINAL_CONFLICT'):service.fail(store,record.run_id,owner.claim)
    assert service.read(store,record.run_id).record==final


@pytest.mark.parametrize('phase',['flush','commit'])
def test_pg_atomic_acceptance_rollback(db,monkeypatch,phase):
    engine,service,actor,store=db;r,res,_,_,_=case();original=getattr(Session,phase)
    def fault(s,*args,**kwargs):
        if phase=='commit' or s.info.get('accepted_insert'):
            raise ValueError('INJECTED acceptance write failure')
        return original(s,*args,**kwargs)
    if phase=='flush':
        from app.repositories.planning import PlanningRepository
        insert=PlanningRepository.accept
        def mark(repo,record):
            row=insert(repo,record);repo.session.info['accepted_insert']=True;return row
        monkeypatch.setattr(PlanningRepository,'accept',mark)
    monkeypatch.setattr(Session,phase,fault)
    with pytest.raises(PlanningPersistenceError) as error:service.accept(actor,store,'key',r,res)
    assert error.value.run_id is not None
    monkeypatch.setattr(Session,phase,original)
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(PlanningRun))==0


@pytest.mark.parametrize('kind',['transport','cleanup'])
def test_pg_completion_reconciliation_or_primary_cleanup_error(db,monkeypatch,kind):
    engine,service,actor,store=db;record,_,_,_=accept(db)
    claimed=service.claim(store,record.run_id);_,_,decl,capture,result=computation()
    service.retain(store,record.run_id,claimed.claim,decl,capture)
    commit=Session.commit;rollback=Session.rollback;close=Session.close;target=[]
    primary=ValueError('INJECTED primary completion error')
    def fault(s):
        target.append(s)
        if kind=='cleanup':raise primary
        commit(s)
        raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED transport'),connection_invalidated=True)
    def rb(s):
        if kind=='cleanup' and s in target:raise RuntimeError('INJECTED rollback')
        return rollback(s)
    def cl(s):
        if kind=='cleanup' and s in target:raise RuntimeError('INJECTED close')
        return close(s)
    monkeypatch.setattr(Session,'commit',fault);monkeypatch.setattr(Session,'rollback',rb);monkeypatch.setattr(Session,'close',cl)
    if kind=='transport':
        assert service.finalize(store,record.run_id,claimed.claim,result).status=='completed'
    else:
        with pytest.raises(PlanningPersistenceError) as error:service.finalize(store,record.run_id,claimed.claim,result)
        assert error.value.__cause__ is primary and error.value.state=='running'
        assert any('rollback' in n for n in primary.__notes__) and any('close' in n for n in primary.__notes__)
    assert engine.pool.checkedout()==0
    assert service.read(store,record.run_id).record.status==('completed' if kind=='transport' else 'running')


@pytest.mark.parametrize('kind',['transport','programming','known_transaction'])
def test_pg_commit_classifier_fresh_aggregate_verification(db,monkeypatch,kind):
    engine,service,actor,store=db;r,res,_,_,_=case();original=Session.commit;fired=[]
    def fault(s):
        if fired:return original(s)
        fired.append(s)
        if kind=='known_transaction':
            s.execute(text("DO $$ BEGIN RAISE EXCEPTION USING ERRCODE = '40001'; END $$"))
        original(s)
        if kind=='programming':raise ValueError('INJECTED after durable commit')
        raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED transport'),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',fault)
    if kind=='transport':
        saved=service.accept(actor,store,'key',r,res)
        assert saved.status=='queued'
    else:
        with pytest.raises(PlanningPersistenceError) as error:service.accept(actor,store,'key',r,res)
        assert error.value.code=='EXECUTION_ERROR' and error.value.run_id
        assert error.value.state==('queued' if kind=='programming' else 'unknown')
    monkeypatch.setattr(Session,'commit',original)
    with Session(engine) as s:
        rows=s.scalars(select(PlanningRun)).all()
        assert len(rows)==(0 if kind=='known_transaction' else 1)
        if rows:assert service.read(store,rows[0].id).record.status=='queued'


def test_pg_primary_commit_error_survives_rollback_and_close(db,monkeypatch):
    engine,service,actor,store=db;r,res,_,_,_=case()
    target=[];primary=ValueError('INJECTED primary');commit=Session.commit;rollback=Session.rollback;close=Session.close
    def broken_commit(s):target.append(s);raise primary
    def broken_rollback(s):
        if s in target:raise RuntimeError('INJECTED rollback')
        return rollback(s)
    def broken_close(s):
        if s in target:raise RuntimeError('INJECTED close')
        return close(s)
    monkeypatch.setattr(Session,'commit',broken_commit);monkeypatch.setattr(Session,'rollback',broken_rollback);monkeypatch.setattr(Session,'close',broken_close)
    with pytest.raises(PlanningPersistenceError) as error:service.accept(actor,store,'key',r,res)
    assert error.value.__cause__ is primary
    assert any('rollback' in n for n in primary.__notes__) and any('close' in n for n in primary.__notes__)
    assert engine.pool.checkedout()==0


def test_pg_programming_after_durable_completion_never_failed_or_success(db,monkeypatch):
    engine,service,actor,store=db;record,decl,source,factory=accept(db);original=Session.commit
    def fault(s):
        terminal=s.scalar(select(PlanningRun.status).where(PlanningRun.id==record.run_id))=='completed'
        original(s)
        if terminal:raise ValueError('INJECTED post completion bug')
    monkeypatch.setattr(Session,'commit',fault)
    with pytest.raises(PlanningPersistenceError) as error:
        service.execute(store,record.run_id,decl,source,factory,lambda:source.facts.facts.captured_at)
    assert error.value.run_id==record.run_id and error.value.state=='completed'
    assert service.read(store,record.run_id).record.status=='completed'


def test_pg_failure_recording_failure_keeps_primary_and_running(db,monkeypatch):
    engine,service,actor,store=db;record,decl,source,factory=accept(db)
    primary=ValueError('INJECTED capture bug')
    def read(*args):raise primary
    monkeypatch.setattr(source,'read',read)
    monkeypatch.setattr(service,'fail',lambda *a:(_ for _ in ()).throw(RuntimeError('INJECTED failure recording')))
    with pytest.raises(PlanningPersistenceError) as error:service.execute(store,record.run_id,decl,source,factory)
    assert error.value.code=='FAILURE_RECORDING_ERROR' and error.value.state=='running'
    assert error.value.__cause__ is primary
    assert service.read(store,record.run_id).record.status=='running'


@pytest.mark.parametrize('corruption',['digest','version','relationship','semantic'])
def test_pg_corruption_rejected_even_with_rehashed_payload(db,corruption):
    engine,service,actor,store=db;record,_,_,_=accept(db)
    with Session(engine) as s,s.begin():
        row=s.get(PlanningRun,record.run_id);body=deepcopy(row.record_json)
        if corruption=='digest':row.record_digest='f'*64
        else:
            if corruption=='version':body['resolution']['semantics_version']='planning_resolution/2'
            if corruption=='relationship':body['actor_id']=str(uuid4())
            if corruption=='semantic':body['resolution']['budget']['amount']='1e0'
            row.record_json=body;row.record_digest=digest('aggregate',body)
    # Unsupported version also violates the DB constraint, tested below instead.
    with pytest.raises(PlanningPersistenceError,match='RESULT_INTEGRITY_UNAVAILABLE'):service.read(store,record.run_id)




def test_pg_durable_queued_real_process_death_recovery_and_alive_guard(db):
    engine,service,actor,store=db;queued,_,_,_=accept(db)
    restarted=PlanningRunUseCases(engine)
    assert restarted.read(store,queued.run_id).record.status=='queued'
    claimed=restarted.claim(store,queued.run_id)
    with pytest.raises(PlanningPersistenceError,match='OWNER_ALIVE'):restarted.recover_interrupted(store,queued.run_id)
    interrupted,_,_,_=accept(db,key='interrupted')
    context=multiprocessing.get_context('spawn');queue=context.Queue()
    child=context.Process(target=child_claim,args=(engine.url.render_as_string(hide_password=False),store,interrupted.run_id,queue))
    child.start();identity=queue.get(timeout=20);child.join(20);assert not child.is_alive() and child.exitcode==0
    child_record=restarted.read(store,interrupted.run_id).record
    assert child_record.status=='running' and child_record.claim.process.pid==child.pid
    assert child_record.claim.token==__import__('uuid').UUID(identity['token'])
    final=restarted.recover_interrupted(store,interrupted.run_id)
    assert final.status=='failed' and final.error_code=='PROCESS_INTERRUPTED'
    assert restarted.read(store,queued.run_id).record.status=='running'
    with pytest.raises(PlanningPersistenceError,match='STALE_CLAIM'):service.fail(store,interrupted.run_id,claimed.claim)
    assert not any('expiry' in c['name'] or 'ttl' in c['name'] for c in inspect(engine).get_columns('planning_runs'))


def test_pg_additive_migration_preserves_historical_s1_data(db):
    engine,service,actor,store=db
    command.downgrade(migration_config(),'0008_forecast_execution_meta')
    _,_,_,source,_=case();seed_facts(engine,source,historical_recipe_schema=True);fc=source.facts.facts.forecast
    run=uuid4()
    with Session(engine) as s,s.begin():
        s.add(DecisionRun(id=run,store_id=store,forecast_run_id=fc.id,status='COMPLETED',
            planning_start_date=fc.forecast_start_date,planning_end_date=fc.forecast_end_date,package_schema_version=1,
            input_fingerprint='S1 historical fixture',input_snapshot_json={'old':'input'},decision_package_json={'old':'package'},
            recommended_strategy='BALANCED',started_at=fc.completed_at,completed_at=fc.completed_at))
    command.upgrade(migration_config(),'head')
    from app.application.use_cases.decision import DecisionUseCases
    from app.application.contracts.common import RunReferenceInput
    with Session(engine) as fresh:
        old=DecisionUseCases(fresh).get(RunReferenceInput(store_id=store,run_id=run))
        assert old.status=='COMPLETED' and old.recommended_strategy=='BALANCED'
        assert fresh.get(ForecastRun,fc.id).status=='COMPLETED'
        assert fresh.scalar(select(func.count()).select_from(PlanningRun))==0
        for original in source.facts.facts.recipes:
            recipe=fresh.get(Recipe,original.id)
            assert recipe.assigned is True
            assert all(getattr(recipe,key)==value for key,value in original.model_dump(exclude={'lines'}).items())
