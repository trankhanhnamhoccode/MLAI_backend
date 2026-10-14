"""N9 retained acceptance budget, local-day filters and export discovery."""
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import planning, config, env, submit
from app.models.planning_configuration import PlanningBudget
from tests.integration.test_planning_exports import exports, flow, export, demand_and_offer
from tests.integration.test_discovery_c4 import count_read_queries


def test_history_acceptance_budget_creator_and_local_date(planning):
    c=planning;response=submit(c);assert response.status_code==202,response.text
    path=f'/api/v1/stores/{c[1].store_id}/procurement-plans'
    query={'created_by_user_id':str(c[1].user_id),'created_date_from':'2026-10-10','created_date_to':'2026-10-10'}
    read=c[0][5].get(path,params=query);assert read.status_code==200,read.text
    data=read.json();assert len(data['data']['items'])==1
    assert data['data']['items'][0]['captured_budget']==dict(availability='available',limit='100',currency='VND')
    assert data['meta']['applied_filters']['created_by_user_id']==str(c[1].user_id)
    with Session(c[0][1]) as s:
        cap=s.get(PlanningBudget,c[1].store_id);cap.amount='1';cap.version='changed';s.commit()
    assert c[0][5].get(path,params=query).json()['data']==data['data']
    assert c[0][5].get(path,params={**query,'created_by_user_id':str(uuid4())}).json()['data']['items']==[]
    assert c[0][5].get(path,params={**query,'created_date_from':'2026-10-11'}).status_code==422


def test_today_latest_status_is_the_newest_run_and_get_does_not_execute(planning):
    from datetime import timedelta
    c=planning;first=submit(c);assert first.status_code==202
    c[0][4][0]+=timedelta(minutes=1)
    second=submit(c);assert second.status_code==202
    path=f'/api/v1/stores/{c[1].store_id}/today'
    get=lambda:c[0][5].get(path,params={'section':'planning'})
    _,response=count_read_queries(c[0][1],get)
    snapshot=response.json()['meta']['snapshot_id'];latest=response.json()['data']['sections']['planning']['value']
    assert latest['run_id']==second.json()['data']['run_id'] and latest['status']=='queued'
    service=c[0][5].app.state.planning_public
    ident=UUID(latest['run_id']);claimed=service.runs.claim(c[1].store_id,ident)
    assert get().json()['data']['sections']['planning']['value']['status']=='running'
    failed=service.runs.fail(c[1].store_id,ident,claimed.claim,code='EXECUTION_ERROR')
    latest=get().json()['data']['sections']['planning']['value']
    assert latest['status']=='failed' and latest['outcome']==failed.outcome and latest['error_code']=='EXECUTION_ERROR'
    assert c[0][5].get(path,params={'section':'planning','snapshot_id':snapshot}).status_code==409


def test_history_budget_known_zero_is_not_missing_evidence(planning):
    c=planning
    accepted=submit(c,body=dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements=dict(
        budget_limit='0',paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])])))
    assert accepted.status_code==202,accepted.text
    result=c[0][5].get(f'/api/v1/stores/{c[1].store_id}/procurement-plans')
    assert result.status_code==200,result.text
    assert result.json()['data']['items'][0]['captured_budget']==dict(availability='available',limit='0',currency='VND')


def test_history_timezone_boundary_and_constant_queries(planning):
    from datetime import datetime,timezone
    from tests.integration.test_auth_public import login
    c=planning;ids=[]
    for stamp in ('2026-10-10T16:59:59+00:00','2026-10-10T17:00:00+00:00','2026-10-11T17:00:00+00:00'):
        c[0][4][0]=datetime.fromisoformat(stamp)
        c[3]['X-CSRF-Token']=login(c[0]).json()['data']['session']['csrf_token']
        result=submit(c,body=dict(requirements_mode='default',default_requirements_version='default-1',forecast_start_date='2026-10-12'))
        assert result.status_code==202,result.text
        ids.append(result.json()['data']['run_id'])
    path=f'/api/v1/stores/{c[1].store_id}/procurement-plans'
    filtered=c[0][5].get(path,params=dict(created_date_from='2026-10-11',created_date_to='2026-10-11',status='queued'))
    assert filtered.status_code==200,filtered.text
    assert [r['run_id'] for r in filtered.json()['data']['items']]==[ids[1]]
    one,small=count_read_queries(c[0][1],lambda:c[0][5].get(path,params={'limit':1}))
    many,_=count_read_queries(c[0][1],lambda:c[0][5].get(path,params={'limit':100}))
    assert one==many
    cursor=small.json()['meta']['pagination']['next_cursor']
    assert c[0][5].get(path,params={'limit':1,'cursor':cursor,'created_by_user_id':str(uuid4())}).status_code==422
    print(f'Query evidence: N9={many} queries, constant for page1/page100.')


def test_export_discovery_retained_locators_and_artifact_states(exports,monkeypatch):
    flow,svc=exports;c,_,_,worker=flow;demand_and_offer(flow)
    accepted=submit(c);worker.run_one();location=accepted.headers['Location'];path=location+'/exports'
    assert c[0][5].get(path).json()['data']['items']==[]
    queued=export(c,location);assert queued.status_code==202,queued.text
    item=c[0][5].get(path).json()['data']['items'][0]
    assert item['artifact_availability']=='pending' and item['allowed_actions']==['poll']
    assert item['sha256'] is item['byte_count'] is item['download_url'] is None
    again=export(c,location);assert again.status_code==202
    one,_=count_read_queries(c[0][1],lambda:c[0][5].get(path,params={'limit':1}))
    many,_=count_read_queries(c[0][1],lambda:c[0][5].get(path,params={'limit':100}))
    assert one==many
    print(f'Query evidence: EX01={many} queries, constant for page1/page100.')
    monkeypatch.setattr(svc.renderer,'render',lambda _:b'%PDF-synthetic discovery fixture')
    assert svc.run_one().status=='completed'
    assert svc.run_one().status=='completed'
    monkeypatch.setattr(svc.renderer,'render',lambda _:(_ for _ in ()).throw(AssertionError('GET rendered PDF')))
    available=c[0][5].get(path);assert available.status_code==200,available.text
    item=available.json()['data']['items'][0];assert item['artifact_availability']=='available' and item['byte_count']>0
    assert {r['export_id'] for r in available.json()['data']['items']}=={
        queued.json()['data']['export_id'],again.json()['data']['export_id']}
    assert item['download_url']
    artifact=svc.artifacts.root/(item['export_id']+'.pdf');artifact.write_bytes(b'%PDF-corrupt')
    corrupt=c[0][5].get(path).json()['data']['items'][0]
    assert corrupt['status']=='completed' and corrupt['artifact_availability']=='unverifiable'
    assert corrupt['sha256'] is corrupt['download_url'] is corrupt['byte_count'] is None
    assert c[0][5].get(path,params={'snapshot_id':available.json()['meta']['snapshot_id']}).status_code==409
    artifact.unlink()
    assert c[0][5].get(path).json()['data']['items'][0]['artifact_availability']=='missing'
    assert c[0][5].get(path,params={'option_id':'option-does-not-exist'}).status_code==422
    from app.models import PlanningExport
    from sqlalchemy import select,func
    with Session(c[0][1]) as s:assert s.scalar(select(func.count()).select_from(PlanningExport))==2
