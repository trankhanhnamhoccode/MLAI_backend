"""S4.9 current fences, retained integrity, real lifecycle/runtime availability."""
from copy import deepcopy
from time import perf_counter,sleep
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,event
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow,planning,config,env,submit,demand_and_offer
from tests.integration.test_planning_configuration_public import base,cap,save,full
from app.models import StoreMembership,PlanningRun,Product,InventoryLot
from app.models.auth import MembershipGrant
from app.application.use_cases.planning_public import RUN_PERMISSIONS,READ_PERMISSIONS
from app.application.planning_serialization import digest


def staffed(c):
    with Session(c[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.user_id==c[1].user_id,StoreMembership.store_id==c[1].store_id))
        member.role='STAFF';mid=member.id
        for grant in set((*RUN_PERMISSIONS,*READ_PERMISSIONS,'planning.context.read','sales.read')):
            s.add(MembershipGrant(membership_id=mid,permission=grant))
        s.commit()
    return mid


def revoke(c,mid,permission):
    with Session(c[0][1]) as s:
        s.delete(s.get(MembershipGrant,(mid,permission)));s.commit()


@pytest.mark.parametrize('phase',['acceptance','execution','publication','read'])
def test_current_revoke_at_every_boundary(flow,monkeypatch,phase):
    c,_,_,worker=flow;mid=staffed(c);key=str(uuid4())
    if phase=='acceptance':
        revoke(c,mid,'budget.read');response=submit(c,key)
        assert response.status_code==403,response.text
        with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==0
        return
    if phase=='publication':demand_and_offer(flow)
    response=submit(c,key);assert response.status_code==202,response.text
    if phase=='execution':revoke(c,mid,'planning.run')
    if phase=='publication':
        from app.infrastructure.procurement_milp_v2 import NativeProductSearch
        revoked=[]
        def actual_search(request,offers):
            assert c[0][1].pool.checkedout()==0 # No solver-owned Session.
            if not revoked:revoke(c,mid,'planning.run');revoked.append(True)
            return NativeProductSearch(request,offers)
        worker.search_factory=actual_search
    record=worker.run_one()
    if phase in ('execution','publication'):
        assert record.status=='failed' and record.error_code=='PERMISSION_DENIED'
        assert submit(c,key).status_code==403
        read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
        assert read.json()['data']['result'] is None
    else:
        assert record.status=='completed'
        revoke(c,mid,'procurement.cost.read')
        assert c[0][5].get(response.headers['Location']).status_code==403
        assert submit(c,key).status_code==403


def test_store_membership_read_is_not_creator_only_and_foreign_hidden(flow):
    from tests.integration.test_auth_public import setup,login,provision
    c,_,_,worker=flow;response=submit(c);worker.run_one()
    other=provision(c[0],'foreign@example.test')
    reader=setup(c[0],'reader@example.test',store=False)
    with Session(c[0][1]) as s:
        member=StoreMembership(id=uuid4(),user_id=reader.user_id,store_id=c[1].store_id,role='STAFF')
        s.add(member);s.flush()
        s.add_all(MembershipGrant(membership_id=member.id,permission=p) for p in READ_PERMISSIONS);s.commit()
    signed_in=login(c[0],'reader@example.test')
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    assert read.json()['data']['store_id']==str(c[1].store_id)
    foreign=c[0][5].post(f'/api/v1/stores/{other.store_id}/procurement-plans',headers={**c[3],
        'X-CSRF-Token':signed_in.json()['data']['session']['csrf_token'],'Idempotency-Key':str(uuid4())},json=dict(
            requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-10'))
    assert foreign.status_code==404,foreign.text
    with Session(c[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.user_id==reader.user_id));member.active=False;s.commit()
    assert c[0][5].get(response.headers['Location']).status_code==404


def test_logout_preserves_intent_current_actor_worker_fence(flow):
    c,_,_,worker=flow;response=submit(c)
    logout=c[0][5].post('/api/v1/auth/logout',headers=c[3]);assert logout.status_code==204
    record=worker.run_one();assert record.status=='completed'
    assert c[0][5].get(response.headers['Location']).status_code==401


@pytest.mark.parametrize('mode',['default','saved'])
def test_config_values_fixed_when_source_changes_after_acceptance(flow,mode):
    from app.models.planning_configuration import PlanningDefault,PlanningBudget,SavedRequirement
    c,_,_,worker=flow
    if mode=='saved':
        saved=save(c,full(requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='90',product_overrides=[])],budget_limit='50'))).json()['data']
        body=dict(requirements_mode='saved',saved_requirement_id=saved['saved_requirement_id'],forecast_start_date='2026-10-10')
    else:body=None
    response=submit(c,body=body);assert response.status_code==202,response.text
    before=c[0][5].get(response.headers['Location']).json()['data']['configuration']
    with Session(c[0][1]) as s:
        defaults=s.get(PlanningDefault,c[1].store_id);defaults.version='later-default'
        budget=s.get(PlanningBudget,c[1].store_id);budget.version='later-cap';budget.amount='1'
        if mode=='saved':
            row=s.get(SavedRequirement,UUID(saved['saved_requirement_id']));row.version='later-saved';row.state='archived'
            row.requirements_json=dict(paths=[dict(path='HIGH',min_fill_rate_percent='0',product_overrides=[])],budget_limit='0')
        s.commit()
    record=worker.run_one();assert record.status=='completed',record.error_code
    after=c[0][5].get(response.headers['Location']);assert after.status_code==200,after.text
    assert after.json()['data']['configuration']==before


@pytest.mark.parametrize('when',['acceptance','capture'])
def test_active_menu_limit_is_not_computed_menu_limit(flow,when):
    c,_,_,worker=flow
    if when=='capture':response=submit(c)
    with Session(c[0][1]) as s:
        s.add_all(Product(id=uuid4(),store_id=c[1].store_id,name='No history '+str(i),selling_unit='cup',active=True) for i in range(50));s.commit()
    if when=='acceptance':
        response=submit(c);assert response.status_code==422,response.text
        assert response.json()['error']['details']['field_errors'][0]['code']=='RESOURCE_LIMIT_EXCEEDED'
    else:
        record=worker.run_one();assert record.outcome=='computation_blocked'
        assert any(p.code=='RESOURCE_LIMIT_EXCEEDED' for p in record.capture.problems)
        assert len(record.capture.menu)==51


def test_retained_read_immutable_no_live_compute_bounded_queries_and_payload(flow,monkeypatch):
    from app.models import SalesDaily,Recipe,ForecastRun
    c,_,recipe,worker=flow;response=submit(c);worker.run_one()
    before=c[0][5].get(response.headers['Location']);assert before.status_code==200,before.text
    with Session(c[0][1]) as s:
        s.query(SalesDaily).one().quantity=1000;s.get(Product,c[2]).price=9000;s.get(Recipe,recipe).assigned=False;s.commit()
    def forbidden(*args,**kwargs):raise AssertionError('GET MUST NOT execute/capture/provider')
    monkeypatch.setattr(worker.forecast,'serve',forbidden)
    monkeypatch.setattr(worker.forecast,'prepare',forbidden)
    monkeypatch.setattr(worker.capture,'read',forbidden)
    monkeypatch.setattr(worker,'run_one',forbidden)
    queries=[]
    def counted(conn,cursor,statement,parameters,context,executemany):queries.append(statement)
    engine=c[0][5].app.state.planning_public.engine
    event.listen(engine,'before_cursor_execute',counted)
    started=perf_counter()
    try:after=c[0][5].get(response.headers['Location'])
    finally:event.remove(engine,'before_cursor_execute',counted)
    elapsed=perf_counter()-started
    assert after.status_code==200,after.text
    assert after.json()==before.json() and after.headers['ETag']==before.headers['ETag']
    assert len(queries)<=12 and len(after.content)<100000 and elapsed<10
    assert not any(table in q.lower() for q in queries for table in ('inventory_lots','supplier_terms','sales_daily','recipes'))
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,UUID(before.json()['data']['run_id']))
        assert row.record_digest==digest('aggregate',row.record_json)
    from pathlib import Path
    import json
    out=Path('runtime/s49');out.mkdir(parents=True,exist_ok=True)
    (out/'retained_read_measurement.json').write_text(json.dumps(dict(queries=len(queries),bytes=len(after.content),http_seconds=elapsed,
        fixture='one active Product,one Ingredient,zero demand actual baseline/engine; not maximum-scope SLA')),encoding='utf-8')
    (out/'c03_completed_actual_test.json').write_text(after.text,encoding='utf-8')


@pytest.mark.parametrize('rehashed',[False,True])
def test_retained_digest_and_typed_evidence_corruption_fails_closed(flow,rehashed):
    c,_,_,worker=flow;response=submit(c);worker.run_one()
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,UUID(response.json()['data']['run_id']))
        value=deepcopy(row.record_json)
        value['public_capture']['forecast']['model_version']='fake'
        row.record_json=value
        if rehashed:row.record_digest=digest('aggregate',value)
        s.commit()
    read=c[0][5].get(response.headers['Location'])
    assert read.status_code==503,read.text
    assert read.json()['error']['code']=='RESULT_INTEGRITY_UNAVAILABLE'


def test_running_alive_owner_and_read_never_restarts(flow):
    c,_,_,worker=flow;response=submit(c);run=UUID(response.json()['data']['run_id'])
    record=worker.runs.claim(c[1].store_id,run)
    assert worker.recover()==()
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    assert read.json()['data']['status']=='running' and read.json()['data']['result'] is None
    from pathlib import Path
    Path('runtime/s49/c03_running_actual_test.json').write_text(read.text,encoding='utf-8')
    assert read.json()['meta']['poll_after_ms']==2000 and worker.run_one() is None


def test_actual_lifespan_worker_and_runtime_readiness(flow):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.application.use_cases.readiness import ReadinessReads
    from app.application.use_cases.planning_public import PublicPlanning
    c,_,_,execution=flow
    assert c[0][0].planning_worker_enabled is False
    app=create_app(c[0][0].model_copy(update={'planning_worker_enabled':True}))
    app.state.auth=c[0][2]
    app.state.planning_public=PublicPlanning(c[0][2],app.state.forecast_serving)
    app.state.planning_execution=execution
    app.state.readiness=ReadinessReads(c[0][2],app.state.forecast_serving,planning_available=lambda:app.state.planning_worker is not None and app.state.planning_worker.available)
    with TestClient(app,base_url='https://backend.example.test') as client:
        client.cookies.update(c[0][5].cookies)
        read=client.get(base(c)+'/readiness',params={'actions':'planning','forecast_start_date':'2026-10-10'})
        assert read.status_code==200,read.text
        assert read.json()['data']['actions'][0]['execution_status']=='available'
        context=client.get(base(c)+'/planning-context');assert context.status_code==200,context.text
        assert context.json()['data']['capabilities']['winner_selection'] is True
        response=client.post(base(c)+'/procurement-plans',headers={**c[3],'Idempotency-Key':str(uuid4())},json=dict(
            requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-10'))
        assert response.status_code==202,response.text
        deadline=perf_counter()+30
        while perf_counter()<deadline:
            poll=client.get(response.headers['Location']);assert poll.status_code==200,poll.text
            if poll.json()['data']['status'] in ('completed','failed'):break
            sleep(.1)
        assert poll.json()['data']['status']=='completed',poll.text
        assert poll.json()['data']['result']['winner_option_id']
        assert app.state.planning_worker.available
    assert not app.state.planning_worker.available


def test_overall_deadline_records_actual_engine_elapsed_without_false_cancel(flow,monkeypatch):
    import app.application.use_cases.planning_worker as module
    c,_,_,worker=flow;response=submit(c)
    # Labeled clock failure injection, after an actual native computation.
    ticks=iter((0,.01,.02,.03,181,181,181))
    monkeypatch.setattr(module,'perf_counter',lambda:next(ticks,181))
    record=worker.run_one()
    assert record.status=='failed' and record.error_code=='EXECUTION_DEADLINE_EXCEEDED'
    assert record.public_execution.elapsed_seconds==181 and record.public_execution.stage_overrun_seconds==1
    assert record.public_execution.engine_seconds is not None
    assert record.result is None # No fabricated or uncommitted business result.
    poll=c[0][5].get(response.headers['Location']);assert poll.status_code==200,poll.text
    assert poll.json()['data']['errors'][0]['code']=='EXECUTION_DEADLINE_EXCEEDED'
    from pathlib import Path
    output=Path('runtime/s49/c03_failed_actual_test.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(poll.text,encoding='utf-8')


def test_worker_unavailable_leaves_data_valid_and_get_does_not_start_it(flow,monkeypatch):
    from app.application.use_cases.readiness import ReadinessReads
    c,_,_,worker=flow;app=c[0][5].app
    assert app.state.planning_worker is None
    app.state.readiness=ReadinessReads(c[0][2],app.state.forecast_serving,planning_available=lambda:False)
    def forbidden(*args,**kwargs):raise AssertionError('GET cannot execute planning')
    monkeypatch.setattr(worker,'run_one',forbidden)
    readiness=c[0][5].get(base(c)+'/readiness',params={'actions':'planning','forecast_start_date':'2026-10-10'})
    assert readiness.status_code==200,readiness.text
    action=readiness.json()['data']['actions'][0]
    assert action['data_status']=='valid' and action['execution_status']=='unavailable'
    assert not action['can_execute'] and app.state.planning_worker is None
    with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==0


def test_partial_verified_recommendation_does_not_hide_engine_error(flow):
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    c,_,_,worker=flow;demand_and_offer(flow)
    class FaultOneStrategy:
        def __init__(self,request,offers):self.actual=NativeProductSearch(request,offers)
        def solve(self,strategy,phase,deadline):
            if strategy=='LEAN':raise RuntimeError('INJECTED D:/private/model/secret-artifact')
            return self.actual.solve(strategy,phase,deadline)
    worker.search_factory=FaultOneStrategy
    response=submit(c);record=worker.run_one()
    assert record.status=='failed' and record.result is not None
    assert record.result.selection.winner_token is not None
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    data=read.json()['data']
    assert data['outcome']=='execution_error' and data['result']['winner_option_id']
    assert data['result']['completeness']=='partial' and data['result']['strategies'][0]['execution']=='ERROR'
    assert data['errors'][0]['code']=='EXECUTION_ERROR' and 'private/model' not in read.text


def test_c02_json_and_stream_limits_before_acceptance(planning):
    c=planning;client=c[0][5]
    headers={**c[3],'Idempotency-Key':str(uuid4()),'Content-Type':'application/json'}
    for body in ('{"requirements_mode":"default","requirements_mode":"custom"}', '{"a":NaN}', '{', '{}'):
        response=client.post(base(c)+'/procurement-plans',content=body,headers=headers if body!='{}' else c[3])
        assert response.status_code==400,response.text
    response=client.post(base(c)+'/procurement-plans',content=b' ' * 65537,headers=headers)
    assert response.status_code==422,response.text
    assert response.json()['error']['details']['field_errors'][0]['code']=='RESOURCE_LIMIT_EXCEEDED'
    with Session(c[0][1]) as s:assert s.query(PlanningRun).count()==0
