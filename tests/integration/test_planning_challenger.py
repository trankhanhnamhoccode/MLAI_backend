"""F4 actual pinned native + public session/CSRF + real worker + PostgreSQL."""
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID,uuid4
import json
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from tests.integration.test_planning_configuration_public import config,env,base
from tests.integration.test_auth_public import login
from tests.integration.test_readiness_context import known_facts,declaration
from app.application.contracts import import_domains as d
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.planning_worker import PlanningExecution
from app.application.use_cases.planning_challenger import ChallengerPlanningServing
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from tests.fixtures.forecast_engine.planning_f4_setup import rebind_fixture
from app.models import SalesDaily,InventoryLot,ForecastRun,PlanningRun


@pytest.fixture
def f4(config,tmp_path,monkeypatch):
    c=config
    # Refuse any shared test DB before creating facts/native artifacts.
    with c[0][1].connect() as conn:
        assert conn.scalar(text('SELECT current_database()'))=='shelfcash_challenger_test'
        assert conn.scalar(text('SELECT current_user'))=='shelfcash_challenger_tester'
        assert not conn.scalar(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user'))
    c[0][4][0]=datetime.now(timezone.utc)
    wire=login(c[0]).json()['data']
    c=(c[0],c[1],c[2],{'Origin':'https://fe.example.test','X-CSRF-Token':wire['session']['csrf_token']})
    ingredient,recipe=known_facts(c)
    storage=ChallengerStorage(tmp_path/'native')
    value=rebind_fixture(storage,c[1].store_id,c[2],'cup',c[0][4][0])
    with Session(c[0][1]) as session:
        session.query(SalesDaily).delete()
        for o in value.observations:
            session.add(SalesDaily(id=uuid4(),store_id=o.store_id,product_id=o.product_id,sales_date=o.sales_date,
                quantity=o.quantity,is_stockout=o.is_stockout))
        lot=uuid4()
        session.add(InventoryLot(id=lot,store_id=c[1].store_id,ingredient_id=ingredient,received_date=value.request.cutoff_date,
            expiry_date=None,on_hand_quantity=1000,unit='ml',unit_cost=1));session.flush()
        declaration(session,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,
            state='COMPLETE_CURRENT_LOTS',observed_at=c[0][4][0],covered_lot_ids=(lot,),evidence_reference='F4 synthetic observed1000'),'inventory')
        declaration(session,c[1].store_id,d.SalesDeclaration(kind='SALES_COVERAGE',product_ids=(c[2],),
            from_date=value.request.history_start_date,to_date=value.request.cutoff_date,state='COMPLETE',
            evidence_reference='F4 explicit synthetic complete history'),'sales')
        session.commit()
    from app.application.use_cases import forecast_trained_execution
    from app.application.use_cases import planning_challenger
    monkeypatch.setattr(forecast_trained_execution,'_now',lambda:c[0][4][0])
    monkeypatch.setattr(planning_challenger,'_now',lambda:c[0][4][0])
    def no_train(*a,**k):raise AssertionError('F4 cannot train')
    import lightgbm
    monkeypatch.setattr(lightgbm,'train',no_train)
    serving=ChallengerPlanningServing(c[0][1],None,settings=c[0][0],storage=storage,declaration=value,enabled=True)
    c[0][5].app.state.planning_public=PublicPlanning(c[0][2],serving)
    worker=PlanningExecution(c[0][2],serving)
    return c,serving,worker,value,storage,lot


def submit(f4,key=None,headers=None):
    c,_,_,value,_,_=f4
    return c[0][5].post(base(c)+'/procurement-plans',headers=headers or {**c[3],'Idempotency-Key':key or str(uuid4())},
        json=dict(requirements_mode='default',default_requirements_version='default-1',forecast_start_date=str(value.forecast_dates[0])))


def test_native_public_worker_retained_exact_winner(f4,monkeypatch):
    c,serving,worker,value,storage,lot=f4
    failures=[]
    run=serving.execution._run
    def diagnostic(*args):
        import traceback
        try:return run(*args)
        except Exception as error:
            cause=error
            while cause is not None:
                failures.append((type(cause).__name__,getattr(cause,'code',None),
                    [(Path(f.filename).name,f.lineno,f.name) for f in traceback.extract_tb(cause.__traceback__)]))
                cause=cause.__cause__
            raise
    monkeypatch.setattr(serving.execution,'_run',diagnostic)
    fail=worker.runs.fail
    def failed(*args,**kwargs):
        import sys,traceback
        error=sys.exception()
        if error:
            failures.append((type(error).__name__,str(error)[:900] if isinstance(error,ValueError) else getattr(error,'code',None),
                [(Path(f.filename).name,f.lineno,f.name) for f in traceback.extract_tb(error.__traceback__)]))
        return fail(*args,**kwargs)
    monkeypatch.setattr(worker.runs,'fail',failed)
    key=str(uuid4());response=submit(f4,key)
    assert response.status_code==202,response.text
    assert submit(f4,key).json()==response.json()
    record=worker.run_one()
    assert record.status=='completed',(record.error_code,failures)
    assert record.outcome=='recommendation_available',[p.code for p in record.capture.problems]
    assert record.public_acceptance.schema_version=='planning_public_acceptance/2'
    assert record.public_acceptance.challenger_test.input==value
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    body=read.json()['data']
    assert body['forecast']['model_type']=='forecast_engine_challenger'
    assert body['forecast']['artifact_identity']==value.artifact_identity
    assert body['result']['winner_option_id']
    assert all(o['costs']['total']['numerator']=='0' for o in body['result']['options'])
    for option in body['result']['options']:
        services={r['path']:r for r in option['product_services']}
        assert {path:r['requested']['numerator'] for path,r in services.items()}=={'LOW':'54','BASE':'66','HIGH':'78'}
        assert all(r['service']['numerator']==r['service']['denominator']=='1' and r['lost_sales']['numerator']=='0' for r in services.values())
    with Session(c[0][1]) as session:
        forecast=session.query(ForecastRun).one()
        assert session.query(PlanningRun).count()==1
        assert session.get(InventoryLot,lot).on_hand_quantity==1000
        from app.models import ForecastExecutionMetadata
        metadata=session.get(ForecastExecutionMetadata,forecast.id).details_json
        evidence=metadata['challenger_evidence']
        assert metadata['selection_reason']=='CHALLENGER_TEST_SELECTED'
        assert evidence['output']['runtime']==record.public_acceptance.challenger_test.runtime.model_dump(mode='json')
        assert evidence['output']['artifact']['purpose']=='synthetic_correctness'
        assert evidence['output']['cqr'][0]['lower']!=evidence['output']['forecast']['predictions'][0]['p25']
        assert len(evidence['output']['reconstruction'])==60
        forecast_id=forecast.id
    def forbidden(*a,**k):raise AssertionError('Retained read must not compute or load live facts/artifacts')
    monkeypatch.setattr(serving.service,'_admit',forbidden)
    monkeypatch.setattr(serving.service,'_compute',forbidden)
    monkeypatch.setattr(serving,'prepare',forbidden)
    with Session(c[0][1]) as session:
        session.query(SalesDaily).first().quantity=999;session.commit()
    (storage.load_artifact(value.artifact_identity).directory/'adapter_manifest.json').write_bytes(b'eligibility/config changed after completion')
    retry=submit(f4,key)
    assert retry.status_code==200 and retry.json()['data']['run_id']==response.json()['data']['run_id']
    assert retry.json()['data']['status']=='completed'
    assert c[0][5].get(response.headers['Location']).json()==read.json()
    explanation=c[0][5].get(response.headers['Location']+'/explanation')
    assert explanation.status_code==200,explanation.text
    from app.application.contracts.common import RunReferenceInput
    retained=serving.execution.replay(RunReferenceInput(store_id=c[1].store_id,run_id=forecast_id))
    assert retained.model_type=='forecast_engine_challenger'
    import multiprocessing
    from tests.planning_challenger_process import retained_read
    context=multiprocessing.get_context('spawn');queue=context.Queue()
    child=context.Process(target=retained_read,args=(c[0][0].database_url,c[1].store_id,record.run_id,queue))
    child.start();fresh=queue.get(timeout=30);child.join(30)
    assert child.exitcode==0 and fresh==dict(status='completed',result_digest=record.result_digest,
        input_digest=record.input_digest,model='forecast_engine_challenger')
    out=Path('runtime/challenger/f4/acceptance');out.mkdir(parents=True,exist_ok=True)
    # Sanitized retained trace excludes sessions, credentials and private paths.
    (out/'native-trace.json').write_text(json.dumps(dict(acceptance_pin=record.public_acceptance.challenger_test.model_dump(mode='json'),
        input=value.model_dump(mode='json'),output=evidence['output'],
        public_result=body),ensure_ascii=False,indent=2),encoding='utf-8')
    from app.models import ForecastPrediction
    from app.application.forecast_serialization import RetainedInputError
    with Session(c[0][1]) as session:
        session.query(ForecastPrediction).filter(ForecastPrediction.forecast_run_id==forecast_id).first().p25+=1
        session.commit()
    with pytest.raises(RetainedInputError,match='CHALLENGER_CANONICAL_OUTPUT_MISMATCH'):
        serving.execution.replay(RunReferenceInput(store_id=c[1].store_id,run_id=forecast_id))
    assert c[0][5].get(response.headers['Location']).json()==read.json()


def test_concurrent_c02_claim_actual_native_once(f4):
    from concurrent.futures import ThreadPoolExecutor
    c,serving,worker,value,storage,lot=f4;key=str(uuid4())
    with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda _:submit(f4,key),range(2)))
    assert all(r.status_code==202 for r in responses),[r.text for r in responses]
    assert responses[0].json()['data']['run_id']==responses[1].json()['data']['run_id']
    other=PlanningExecution(c[0][2],serving)
    with ThreadPoolExecutor(2) as pool:records=list(pool.map(lambda w:w.run_one(),(worker,other)))
    assert sum(r is not None for r in records)==1
    assert next(r for r in records if r).status=='completed'
    with Session(c[0][1]) as session:
        assert session.query(ForecastRun).count()==session.query(PlanningRun).count()==1


def test_pin_survives_live_configuration_change(f4):
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    # The runtime declaration is a future config choice; accepted execution uses
    # the retained pin, even if its replacement is deliberately unusable.
    serving.declaration=None
    with Session(c[0][1]) as session:
        from app.models.model_serving import ModelServingConfiguration
        session.query(ModelServingConfiguration).delete();session.commit()
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert record.public_acceptance.challenger_test.input==value


def test_artifact_changed_after_acceptance_fails_closed(f4):
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    bundle=storage.load_artifact(value.artifact_identity)
    # Only the disposable test artifact changes, never the original E2 artifact.
    (bundle.directory/'model_q25.txt').write_bytes(b'fault injected')
    record=worker.run_one()
    assert record.status=='failed' and record.error_code=='CHALLENGER_ARTIFACT_CORRUPT'
    assert record.result is None and record.capture is None
    with Session(c[0][1]) as session:
        assert session.query(ForecastRun).count()==0
        assert session.get(InventoryLot,lot).on_hand_quantity==1000


@pytest.mark.parametrize('phase',['acceptance','terminal','forecast_completion'])
def test_lost_ack_reconciles_native_run(f4,monkeypatch,phase):
    import psycopg
    from sqlalchemy.exc import OperationalError
    from app.repositories.planning import PlanningRepository
    c,serving,worker,value,storage,lot=f4;fired=[]
    original=Session.commit
    accept=PlanningRepository.accept
    replace=PlanningRepository._replace_locked
    def mark_accept(repo,record):
        result=accept(repo,record);repo.session.info['f4_accept']=True;return result
    def mark_replace(repo,row,record):
        result=replace(repo,row,record)
        if record.status=='completed':repo.session.info['f4_terminal']=True
        return result
    def commit(session):
        target=session.info.get('f4_accept' if phase=='acceptance' else 'f4_terminal')
        if phase=='forecast_completion':
            target=any(isinstance(row,ForecastRun) and row.status=='COMPLETED' for row in session.identity_map.values())
        original(session)
        if target and not fired:
            fired.append(True)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED lost acknowledgment'),connection_invalidated=True)
    monkeypatch.setattr(PlanningRepository,'accept',mark_accept)
    monkeypatch.setattr(PlanningRepository,'_replace_locked',mark_replace)
    monkeypatch.setattr(Session,'commit',commit)
    key=str(uuid4());response=submit(f4,key);assert response.status_code==202,response.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert fired==[True]
    assert submit(f4,key).json()['data']['run_id']==str(record.run_id)
    with Session(c[0][1]) as session:
        assert session.query(ForecastRun).count()==session.query(PlanningRun).count()==1


def test_actual_owner_kill_restart_recovery_stale_writer(f4):
    import multiprocessing
    from tests.planning_challenger_process import hold_claim
    from app.application.contracts.planning_run import PlanningClaim,PlanningPersistenceError
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    run=UUID(response.json()['data']['run_id'])
    context=multiprocessing.get_context('spawn');queue=context.Queue();release=context.Event()
    child=context.Process(target=hold_claim,args=(c[0][0].database_url,c[1].store_id,run,c[0][4][0].isoformat(),queue,release))
    child.start()
    try:
        claim=PlanningClaim.model_validate(queue.get(timeout=30))
        assert child.is_alive()
        child.terminate();child.join(20)
        assert not child.is_alive()
    finally:
        if child.is_alive():child.terminate();child.join(10)
    restarted=PlanningExecution(c[0][2],serving)
    recovered=restarted.recover()
    assert len(recovered)==1 and recovered[0].error_code=='PROCESS_INTERRUPTED'
    with pytest.raises(PlanningPersistenceError,match='TERMINAL_CONFLICT'):restarted.runs.fail(c[1].store_id,run,claim)
    changed=PlanningClaim.model_validate(claim.model_dump()|dict(token=uuid4()))
    with pytest.raises(PlanningPersistenceError,match='STALE_CLAIM'):restarted.runs.fail(c[1].store_id,run,changed)
    assert restarted.run_one() is None
    with Session(c[0][1]) as session:assert session.query(ForecastRun).count()==0


def test_transport_revoke_and_foreign_store(f4):
    from tests.integration.test_planning_public_security import staffed,revoke
    c,serving,worker,value,storage,lot=f4
    for headers in ({'Origin':'https://foreign.test'}, {'Origin':c[3]['Origin'],'X-CSRF-Token':'wrong'}):
        rejected=submit(f4,headers={**headers,'Idempotency-Key':str(uuid4())})
        assert rejected.status_code in (401,403),rejected.text
    mid=staffed(c)
    response=submit(f4);assert response.status_code==202,response.text
    revoke(c,mid,'planning.run')
    record=worker.run_one();assert record.status=='failed' and record.error_code=='PERMISSION_DENIED'
    revoke(c,mid,'procurement.cost.read')
    assert c[0][5].get(response.headers['Location']).status_code==403
    assert c[0][5].get(response.headers['Location']+'/explanation').status_code==403
    from tests.integration.test_auth_public import setup
    other=setup(c[0],'foreign-f4@example.test')
    login(c[0],'foreign-f4@example.test')
    assert c[0][5].get(response.headers['Location']).status_code==404
    with Session(c[0][1]) as session:assert session.query(ForecastRun).count()==0


@pytest.mark.parametrize('kind,code',[('dependency','CHALLENGER_RUNTIME_UNAVAILABLE'),('native_bug','CHALLENGER_TECHNICAL_FAILURE')])
def test_native_failure_no_fallback_or_fake_terminal(f4,monkeypatch,kind,code):
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    import app.application.use_cases.forecast_challenger as module
    def fault(*a,**k):
        if kind=='dependency':raise ImportError('INJECTED missing native dependency')
        raise RuntimeError('INJECTED native bug')
    monkeypatch.setattr(module,'infer_native',fault)
    record=worker.run_one();assert record.status=='failed' and record.error_code==code
    assert record.result is None and record.capture is None
    with Session(c[0][1]) as session:
        assert session.query(ForecastRun).one().status=='FAILED'
        assert session.get(InventoryLot,lot).on_hand_quantity==1000


def test_integration_code_pin_changed_rejects_before_inference(f4,monkeypatch):
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    import app.application.use_cases.planning_challenger as module
    monkeypatch.setattr(module,'integration_digest',lambda:'0'*64)
    record=worker.run_one()
    assert record.status=='failed' and record.error_code=='RESULT_INTEGRITY_UNAVAILABLE'
    with Session(c[0][1]) as session:assert session.query(ForecastRun).count()==0


def test_missing_pinned_artifact_is_explicit_failure(f4,tmp_path):
    c,serving,worker,value,storage,lot=f4
    response=submit(f4);assert response.status_code==202,response.text
    serving.service.storage=ChallengerStorage(tmp_path/'missing')
    record=worker.run_one()
    assert record.status=='failed' and record.error_code=='CHALLENGER_ARTIFACT_MISSING'
    assert record.capture is None and record.result is None
    with Session(c[0][1]) as session:assert session.query(ForecastRun).count()==0


def test_revocation_during_actual_native_inference_fences_planning_publication(f4,monkeypatch):
    from tests.integration.test_planning_public_security import staffed,revoke
    c,serving,worker,value,storage,lot=f4
    mid=staffed(c)
    response=submit(f4);assert response.status_code==202,response.text
    compute=serving.service._compute;calls=[]
    def native_then_revoke(*args):
        output=compute(*args)  # Actual pinned inference, not a fake forecast.
        calls.append(True);revoke(c,mid,'planning.run')
        return output
    monkeypatch.setattr(serving.service,'_compute',native_then_revoke)
    record=worker.run_one()
    assert calls==[True] and record.status=='failed' and record.error_code=='PERMISSION_DENIED'
    assert record.capture is None and record.result is None
    assert c[0][5].get(response.headers['Location']).json()['data']['result'] is None
    with Session(c[0][1]) as session:
        assert session.query(ForecastRun).one().status=='COMPLETED'
        assert session.get(InventoryLot,lot).on_hand_quantity==1000
