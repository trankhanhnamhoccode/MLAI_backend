"""S4.9 guarded real PostgreSQL + public HTTP; actual retained Run evidence."""
from tests.planning_process_cases import child_public_claim
from uuid import uuid4,UUID
import pytest
from sqlalchemy.orm import Session
from tests.integration.test_planning_configuration_public import config,env,base,cap
from tests.integration.test_readiness_context import configure_baseline
from app.application.use_cases.planning_public import PublicPlanning
from app.models import PlanningRun
from app.application.use_cases.planning_worker import PlanningExecution


@pytest.fixture
def planning(config):
    c=config
    c[0][5].app.state.planning_public=PublicPlanning(c[0][2],c[0][5].app.state.forecast_serving)
    configure_baseline(c)
    assert cap(c,**{'If-None-Match':'*'}).status_code==201
    return c


def submit(c,key=None,body=None):
    return c[0][5].post(base(c)+'/procurement-plans',headers={**c[3],'Idempotency-Key':key or str(uuid4())},
        json=body or dict(requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-10'))


def test_receipt_retained_queued_replay_and_original_presence(planning):
    c=planning;key=str(uuid4())
    response=submit(c,key);assert response.status_code==202,response.text
    value=response.json()
    assert set(value['data'])=={'run_id','status','accepted_at'}
    assert value['data']['status']=='queued' and value['meta']['poll_after_ms']==2000
    assert response.headers['Retry-After']=='2'
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    result=read.json()['data']
    from pathlib import Path
    examples=Path('runtime/s49');examples.mkdir(parents=True,exist_ok=True)
    (examples/'c02_accepted_actual_test.json').write_text(response.text,encoding='utf-8')
    (examples/'c03_queued_actual_test.json').write_text(read.text,encoding='utf-8')
    assert result['run_id']==value['data']['run_id'] and result['result'] is None
    assert result['configuration']['budget']['limit']=='100'
    assert result['configuration']['effective_requirements']['budget_limit'] is None
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,UUID(result['run_id']))
        assert row.status=='queued' and row.record_json['public_audit'][0]['action']=='ACCEPTED'
        assert row.record_json['public_acceptance']['serving']['policy']['mode']=='BASELINE'
    # Replays precede resolution, including a newly changed cap.
    with Session(c[0][1]) as s:
        from app.models.planning_configuration import PlanningBudget
        budget=s.get(PlanningBudget,c[1].store_id);budget.amount='1';budget.version='changed';s.commit()
    assert submit(c,key).json()==value
    assert c[0][5].get(response.headers['Location'],headers={'If-None-Match':read.headers['ETag']}).status_code==200
    assert submit(c,key,dict(requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-11')).status_code==409


def test_invalid_transport_has_no_acceptance(planning):
    c=planning
    for headers,body,expected in [({**c[3]}, {},400),({**c[3],'Idempotency-Key':'bad'},{},400)]:
        response=c[0][5].post(base(c)+'/procurement-plans',headers=headers,json=dict(
            requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-10'))
        assert response.status_code==expected,response.text
        assert response.json()['meta']=={}
    response=submit(c,body=dict(requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-10',strategy='lean'))
    assert response.status_code==422 and response.json()['error']['details']['field_errors']
    with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==0


@pytest.fixture
def flow(config,monkeypatch):
    from tests.integration.test_readiness_context import known_facts
    c=config
    c[0][5].app.state.planning_public=PublicPlanning(c[0][2],c[0][5].app.state.forecast_serving)
    from app.application.use_cases import forecast_trained_execution
    monkeypatch.setattr(forecast_trained_execution,'_now',lambda:c[0][4][0])
    ingredient,recipe=known_facts(c)
    return c,ingredient,recipe,PlanningExecution(c[0][2],c[0][5].app.state.forecast_serving)


def test_real_baseline_worker_stock_and_retained_poll(flow):
    from datetime import date
    from app.models import SalesDaily,InventoryLot,ForecastRun
    from tests.integration.test_readiness_context import declaration
    from app.application.contracts import import_domains as d
    c,ingredient,recipe,worker=flow;lot=uuid4()
    with Session(c[0][1]) as s:
        s.query(SalesDaily).filter(SalesDaily.product_id==c[2]).one().quantity=5
        s.add(InventoryLot(id=lot,store_id=c[1].store_id,ingredient_id=ingredient,received_date=date(2026,10,9),expiry_date=None,
            on_hand_quantity=100,unit='ml',unit_cost=1));s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,state='COMPLETE_CURRENT_LOTS',
            observed_at=c[0][4][0],covered_lot_ids=(lot,),evidence_reference='physical observed100'), 'inventory')
        s.commit()
    response=submit(c);assert response.status_code==202,response.text
    record=worker.run_one()
    assert record.status=='completed',record.error_code
    assert record.outcome=='recommendation_available',[p.code for p in record.capture.problems]
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    value=read.json()['data']
    assert value['result']['winner_option_id'] and value['forecast']['model_type']=='historical_quantile_baseline'
    assert value['forecast']['quality_status']=='not_evaluated'
    assert len(value['result']['strategies'])==3
    assert all(not o['purchases'] and o['costs']['total']['numerator']=='0' for o in value['result']['options'])
    with Session(c[0][1]) as s:
        assert s.query(ForecastRun).count()==1
        row=s.get(PlanningRun,UUID(value['run_id']))
        assert row.status=='completed' and [a['action'] for a in row.record_json['public_audit']]==['ACCEPTED','CLAIMED','CAPTURE_RETAINED','COMPLETED']
        assert s.get(InventoryLot,lot).on_hand_quantity==100
    assert worker.run_one() is None


def demand_and_offer(flow,*,cost='2',maximum=None,system='synthetic'):
    from datetime import date
    from app.models import SalesDaily
    from app.application.contracts import import_domains as d
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    from tests.integration.test_readiness_context import declaration
    c,ingredient,recipe,_=flow;supplier,term=uuid4(),uuid4()
    with Session(c[0][1]) as s:
        s.query(SalesDaily).filter(SalesDaily.product_id==c[2]).one().quantity=5
        writer=OperationalConfiguration(s,c[1].store_id)
        writer.supplier(d.SupplierSource(source_supplier_key='supplier',name='Synthetic supplier',active=True),supplier,system,{},create=True)
        writer.term(d.TermSource(source_term_key='offer',supplier_id=supplier,ingredient_id=ingredient,effective_from=date(2026,10,1),effective_to=None,
            unit='ml',pack_size_base_quantity='5',pack_cost=cost,currency='VND',minimum_order_packs=1,lead_time_days=0,shelf_life_days=None,
            active=True,maximum_order_base_quantity=maximum),term,system,{})
        # Supplier creation invalidates previous procurement-context dependency.
        declaration(s,c[1].store_id,d.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',effective_from=date(2026,10,10),effective_to=None,
            committed_inbound_state='CONFIRMED_NONE',no_additional_orders_state='CONFIRMED_NONE',capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),
            supplier_limit_state='EXPLICIT_NOT_CONFIGURED',supplier_limits=(),evidence_reference='observed one-order context'),'context')
        s.commit()
    return term


@pytest.mark.parametrize('mode,budget,outcome',[('default',None,'recommendation_available'),('custom','0','no_eligible_candidate'),('saved','100','recommendation_available')])
def test_real_purchase_and_budget_modes(flow,mode,budget,outcome):
    from tests.integration.test_planning_configuration_public import save,full
    c,ingredient,recipe,worker=flow;term=demand_and_offer(flow)
    if mode=='default':body=None
    elif mode=='custom':body=dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements=dict(
        paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])],budget_limit=budget))
    else:
        saved=save(c,full(requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])],budget_limit=budget)))
        assert saved.status_code==201,saved.text
        body=dict(requirements_mode='saved',saved_requirement_id=saved.json()['data']['saved_requirement_id'],forecast_start_date='2026-10-10')
    response=submit(c,body=body);assert response.status_code==202,response.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert record.outcome==outcome,[p.code for p in record.capture.problems]
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    value=read.json()['data'];options=value['result']['options']
    if outcome=='recommendation_available':
        winner=next(o for o in options if o['option_id']==value['result']['winner_option_id'])
        assert winner['purchases'][0]['supplier_term_id']==str(term)
        assert winner['purchases'][0]['packs']==7 and winner['costs']['total']['numerator']=='14'
        assert winner['costs']['total']['numerator']!='100' # Budget is a ceiling.
    else:
        assert value['result']['winner_option_id'] is None and value['result']['winner_reason']=='NO_ELIGIBLE_CANDIDATE'
        assert all(s['proof']=='UNPROVEN' and s['customer_feasibility']=='UNKNOWN' for s in value['result']['strategies'])


@pytest.mark.parametrize('maximum,expected',[(None,'computation_blocked'),('100','recommendation_available')])
def test_zero_cost_bounds_are_explicit(flow,maximum,expected):
    c,_,_,worker=flow;demand_and_offer(flow,cost='0',maximum=maximum)
    response=submit(c);assert response.status_code==202,response.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert record.outcome==expected,[(p.code,p.detail) for p in record.capture.problems]
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    if maximum is None:
        assert 'OFFER_BOUND_UNKNOWN' in {x['code'] for x in read.json()['data']['errors']}
        assert read.json()['data']['result']['strategies']==[]
    else:
        assert record.declarations.offers[0].bound.source=='TECHNICAL_SEARCH_LIMIT'
        assert record.declarations.supplier_limits==() # Source maximum is not a fabricated declaration.
        assert record.declarations.offers[0].bound.maximum_packs==20


@pytest.mark.parametrize('missing,fee_unknown,expected',[('history',False,'no_computable_products'),('recipe',False,'no_computable_products'),('history',True,'computation_blocked')])
def test_local_exclusion_does_not_hide_global_unknown(flow,missing,fee_unknown,expected):
    from app.models import SalesDaily,Recipe
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    from app.application.contracts import import_domains as d
    from datetime import date
    c,_,recipe,worker=flow
    with Session(c[0][1]) as s:
        if missing=='history':s.query(SalesDaily).delete()
        else:s.get(Recipe,recipe).effective_to=__import__('datetime').date(2026,10,9)
        if fee_unknown:
            OperationalConfiguration(s,c[1].store_id).fee(d.FeeSource(source_fee_key='none',scope='STORE_PROCUREMENT',effective_from=date(2026,10,10),effective_to=None,
                mode='PER_OFFER',coverage='UNKNOWN',currency='VND',components=(),covered_source_term_keys=(),covered_source_supplier_keys=(),
                evidence_reference='unknown payable coverage',reason='new source evidence'),uuid4(),'synthetic',{}, {})
        s.commit()
    response=submit(c);assert response.status_code==202,response.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert record.outcome==expected,[p.code for p in record.capture.problems]
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    data=read.json()['data']
    assert data['scope']['computed_count']==0 and data['result']['strategies']==[] and data['result']['options']==[]
    assert data['execution'] is None and data['result']['winner_option_id'] is None
    if missing=='history':assert data['forecast'] is None
    if fee_unknown:assert 'PAYABLE_FEE_UNKNOWN' in {e['code'] for e in data['errors']}


def test_exact_reuse_fresh_operational_capture_and_model_freeze(flow,monkeypatch):
    from app.models import SalesDaily,Product,ForecastRun
    from app.models.model_serving import ModelServingConfiguration
    c,_,_,worker=flow
    first=submit(c);a=worker.run_one();assert a.outcome=='recommendation_available'
    second=submit(c)
    with Session(c[0][1]) as s:
        product=s.get(Product,c[2]);product.price=7
        row=s.get(ModelServingConfiguration,c[1].store_id);row.version='model-changed-after-acceptance'
        s.commit()
    b=worker.run_one();assert b.outcome=='recommendation_available',b.error_code
    assert b.public_capture.forecast.reused and b.public_capture.forecast.forecast_run_id==a.public_capture.forecast.forecast_run_id
    assert b.public_capture.identity.serving_version==a.public_capture.identity.serving_version
    assert b.public_capture.source_versions.catalog!=a.public_capture.source_versions.catalog
    third=submit(c);d=worker.run_one();assert not d.public_capture.forecast.reused
    with Session(c[0][1]) as s:
        assert s.query(ForecastRun).count()==2
        s.query(SalesDaily).one().quantity=1;s.commit()
    fourth=submit(c);e=worker.run_one();assert not e.public_capture.forecast.reused
    assert e.public_capture.identity.source_digest!=d.public_capture.identity.source_digest


@pytest.mark.parametrize('changes,expected',[(1,'no_eligible_candidate'),(3,'execution_error')])
def test_real_source_changes_bounded_reprepare(flow,monkeypatch,changes,expected):
    from app.models import SalesDaily
    c,_,_,worker=flow;actual=worker.capture.read;calls=[]
    def changing(*args):
        calls.append(1)
        if len(calls)<=changes:
            with Session(c[0][1]) as s:s.query(SalesDaily).one().quantity=len(calls);s.commit()
        return actual(*args)
    monkeypatch.setattr(worker.capture,'read',changing)
    response=submit(c);record=worker.run_one()
    assert record.outcome==expected,record.error_code
    assert len(calls)==2 if changes==1 else len(calls)==3
    if changes==3:
        assert record.error_code=='INPUT_CHANGED_DURING_CAPTURE'
        read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
        assert read.json()['data']['result'] is None


def test_concurrent_acceptance_and_two_workers_one_publication(flow):
    from concurrent.futures import ThreadPoolExecutor
    c,_,_,worker=flow;key=str(uuid4())
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:submit(c,key),range(2)))
    assert all(r.status_code==202 for r in responses),[r.text for r in responses]
    assert responses[0].json()['data']['run_id']==responses[1].json()['data']['run_id']
    other=PlanningExecution(c[0][2],c[0][5].app.state.forecast_serving)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda w:w.run_one(),(worker,other)))
    assert sum(r is not None for r in results)==1
    with Session(c[0][1]) as s:
        assert s.query(PlanningRun).count()==1
        record=s.query(PlanningRun).one().record_json
        assert [e['action'] for e in record['public_audit']].count('COMPLETED')==1




def test_actual_process_death_recovery_and_stale_attempt(flow):
    import multiprocessing
    from app.application.contracts.planning_run import PlanningClaim,PlanningPersistenceError
    c,_,_,worker=flow;response=submit(c);run=UUID(response.json()['data']['run_id'])
    context=multiprocessing.get_context('spawn');queue=context.Queue()
    child=context.Process(target=child_public_claim,args=(c[0][1].url.render_as_string(hide_password=False),c[1].store_id,run,c[0][4][0].isoformat(),queue))
    child.start();claim=PlanningClaim.model_validate(queue.get(timeout=20));child.join(20)
    assert not child.is_alive() and child.exitcode==0
    recovered=worker.recover();assert len(recovered)==1 and recovered[0].error_code=='PROCESS_INTERRUPTED'
    with pytest.raises(PlanningPersistenceError,match='STALE_CLAIM'):
        worker.runs.fail(c[1].store_id,run,claim.model_copy(update={'token':uuid4()}))
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    assert read.json()['data']['status']=='failed' and read.json()['data']['errors'][0]['code']=='PROCESS_INTERRUPTED'
    assert worker.run_one() is None


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_actual_commit_lost_ack_is_reconciled(flow,monkeypatch,phase):
    import psycopg
    from sqlalchemy.exc import OperationalError
    c,_,_,worker=flow;original=Session.commit;fired=[]
    def fault(s):
        targeted=bool(s.info.get('public_terminal_write')) if phase=='terminal' else bool(s.info.get('public_accept_insert'))
        original(s)
        if targeted and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED lost acknowledgment after actual commit'),connection_invalidated=True)
    from app.repositories.planning import PlanningRepository
    insert=PlanningRepository.accept
    def mark(repo,record):
        result=insert(repo,record);repo.session.info['public_accept_insert']=True;return result
    monkeypatch.setattr(PlanningRepository,'accept',mark)
    replace=PlanningRepository._replace_locked
    def mark_terminal(repo,row,record):
        result=replace(repo,row,record)
        if record.status=='completed':repo.session.info['public_terminal_write']=True
        return result
    monkeypatch.setattr(PlanningRepository,'_replace_locked',mark_terminal)
    monkeypatch.setattr(Session,'commit',fault)
    key=str(uuid4());response=submit(c,key);assert response.status_code==202,response.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert fired==[1]
    retry=submit(c,key);assert retry.status_code==200,retry.text
    assert retry.json()['data']['run_id']==response.json()['data']['run_id']
    with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==1
