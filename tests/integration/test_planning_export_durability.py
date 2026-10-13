"""Real claim races, OS process death, ACK reconciliation, current fences."""
from tests.planning_process_cases import child_claim_export
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from tests.integration.test_planning_exports import exports,flow,config,env,export
from tests.integration.test_planning_public import submit
from tests.integration.test_auth_public import setup,login
from app.models import PlanningExport,StoreMembership
from app.models.auth import MembershipGrant
from app.application.contracts.planning_configuration import ConfigurationError


def accepted_export(exports):
    flow,svc=exports;c,_,_,worker=flow;response=submit(c);run=worker.run_one();assert run.status=='completed'
    location=response.headers['Location'];accepted=export(c,location);assert accepted.status_code==202,accepted.text
    return c,svc,location,accepted.json()['data']


def test_two_actual_workers_one_terminal_artifact(exports):
    from app.application.use_cases.planning_exports import PlanningExports
    c,svc,location,receipt=accepted_export(exports)
    second=PlanningExports(svc.public,svc.artifacts,svc.renderer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda worker:worker.run_one(),(svc,second)))
    assert sum(r is not None for r in results)==1
    assert next(r for r in results if r).status=='completed'
    with Session(c[0][1]) as s:
        row=s.get(PlanningExport,UUID(receipt['export_id']));assert row.status=='completed' and row.revision==3
        assert s.query(PlanningExport).count()==1
    assert len(list(svc.artifacts.root.glob('*.pdf')))==1 and not list(svc.artifacts.root.glob('*.tmp'))
    assert c[0][5].get(location+'/exports/'+receipt['export_id']).status_code==200


@pytest.mark.parametrize('phase',['acceptance','claim','terminal'])
def test_real_commit_lost_ack_exact_receipt_reconciliation(exports,monkeypatch,phase):
    import psycopg
    flow,svc=exports;c,_,_,worker=flow;response=submit(c);assert worker.run_one().status=='completed'
    location=response.headers['Location'];original=Session.commit;fired=[]
    def fault(s):
        target=s.info.get('pdf_export_accept') if phase=='acceptance' else s.info.get('pdf_export_transition')==('running' if phase=='claim' else 'completed')
        original(s)
        if target and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED lost ACK after real export commit'),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',fault)
    key=str(uuid4());accepted=export(c,location,key=key);assert accepted.status_code==202,accepted.text
    record=svc.run_one();assert record.status=='completed',record.error_code
    assert fired==[1]
    assert export(c,location,key=key).json()['data']==accepted.json()['data']
    with Session(c[0][1]) as s:assert s.query(PlanningExport).count()==1
    assert c[0][5].get(location+'/exports/'+accepted.json()['data']['export_id']).status_code==200




def test_proven_process_death_live_owner_and_bounded_controlled_retry(exports):
    import multiprocessing
    from app.application.contracts.planning_run import PlanningClaim
    c,svc,location,receipt=accepted_export(exports);ident=UUID(receipt['export_id'])
    context=multiprocessing.get_context('spawn');queue=context.Queue();release=context.Event()
    child=context.Process(target=child_claim_export,args=(c[0][1].url.render_as_string(hide_password=False),ident,c[0][4][0].isoformat(),queue,release))
    child.start();claim=PlanningClaim.model_validate(queue.get(timeout=20))
    assert svc.recover()==()  # Actual owner still alive, no timeout takeover.
    release.set();child.join(20);assert not child.is_alive() and child.exitcode==0
    recovered=svc.recover();assert len(recovered)==1 and recovered[0].error_code=='PROCESS_INTERRUPTED'
    assert c[0][5].get(location+'/exports/'+str(ident)).status_code==409
    retried=svc.retry_failed(ident);assert retried.job_id==UUID(receipt['job_id']) and retried.attempt==2
    result=svc.run_one();assert result.status=='completed' and result.claim.generation==2
    with pytest.raises(ConfigurationError,match='STALE_EXPORT_CLAIM'):svc.fail(ident,claim,'RENDER_FAILED')
    with pytest.raises(ConfigurationError,match='EXPORT_RETRY_NOT_ALLOWED'):svc.retry_failed(ident)
    assert len(list(svc.artifacts.root.glob('*.pdf')))==1


@pytest.mark.parametrize('phase',['materialization','publication'])
def test_staff_current_read_export_replay_worker_and_download_rights(exports,monkeypatch,phase):
    flow,svc=exports;c,ingredient,_,worker=flow;response=submit(c);assert worker.run_one().status=='completed'
    location=response.headers['Location'];client=c[0][5]
    assert client.get(location+'/ingredients').status_code==200  # Warm Owner cache.
    staff=setup(c[0],'pdf-staff@example.test',store=False)
    with Session(c[0][1]) as s:
        member=StoreMembership(id=uuid4(),store_id=c[1].store_id,user_id=staff.user_id,role='STAFF',active=True);s.add(member);s.flush()
        for grant in ('planning.export','planning.result.read','budget.read','procurement.cost.read'):
            s.add(MembershipGrant(membership_id=member.id,permission=grant))
        mid=member.id;s.commit()
    session=login(c[0],'pdf-staff@example.test').json()['data']
    staff_c=(c[0],c[1],c[2],{**c[3],'X-CSRF-Token':session['session']['csrf_token']})
    history=client.get(f'/api/v1/stores/{c[1].store_id}/procurement-plans')
    assert history.status_code==200 and history.json()['data']['items'][0]['created_by']['user_id']==str(c[1].user_id)
    key=str(uuid4());accepted=export(staff_c,location,key=key);assert accepted.status_code==202,accepted.text
    receipt=accepted.json()['data'];download=location+'/exports/'+receipt['export_id']
    def revoke():
        with Session(c[0][1]) as s:s.query(MembershipGrant).filter(MembershipGrant.membership_id==mid,MembershipGrant.permission=='planning.export').delete();s.commit()
    if phase=='materialization':revoke()
    else:
        actual=svc.renderer.render
        def render(report):
            data=actual(report);revoke();return data
        monkeypatch.setattr(svc.renderer,'render',render)
    terminal=svc.run_one();assert terminal.status=='failed' and terminal.error_code=='PERMISSION_DENIED'
    assert export(staff_c,location,key=key).status_code==403
    assert client.get('/api/v1/jobs/'+receipt['job_id']).status_code==403
    assert client.get(download).status_code==403
    assert client.get(location+'/ingredients').status_code==200 # Result rights are independent.
    with Session(c[0][1]) as s:s.query(MembershipGrant).filter(MembershipGrant.membership_id==mid,MembershipGrant.permission=='procurement.cost.read').delete();s.commit()
    for suffix in ('','/ingredients','/ingredients/'+str(ingredient),'/explanation'):
        denied=client.get(location+suffix);assert denied.status_code==403 and denied.json()['data'] is None
    assert client.get(f'/api/v1/stores/{c[1].store_id}/procurement-plans').status_code==403
    assert not list(svc.artifacts.root.glob('*.pdf')) and not list(svc.artifacts.root.glob('*.tmp'))
    login(c[0]);job=client.get('/api/v1/jobs/'+receipt['job_id']);assert job.status_code==200
    assert job.json()['data']['status']=='failed' and job.json()['data']['result'] is None and job.json()['error'] is None
    with Session(c[0][1]) as s:assert s.get(PlanningExport,UUID(receipt['export_id'])).status=='failed'


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_commit_not_applied_never_fabricates_success(exports,monkeypatch,phase):
    import psycopg
    flow,svc=exports;c,_,_,worker=flow;response=submit(c);assert worker.run_one().status=='completed'
    location=response.headers['Location'];original=Session.commit;fired=[]
    def fault(s):
        target=s.info.get('pdf_export_accept') if phase=='acceptance' else s.info.get('pdf_export_transition')=='completed'
        if target and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED before actual commit'),connection_invalidated=False)
        return original(s)
    monkeypatch.setattr(Session,'commit',fault)
    accepted=export(c,location)
    if phase=='acceptance':
        assert accepted.status_code==503,accepted.text
        with Session(c[0][1]) as s:assert s.query(PlanningExport).count()==0
    else:
        assert accepted.status_code==202
        result=svc.run_one();assert result.status=='failed' and result.error_code=='SERVICE_UNAVAILABLE'
        assert c[0][5].get(location+'/exports/'+accepted.json()['data']['export_id']).status_code==409
        # Controlled retry reconciles the orphan only because deterministic
        # rendering proves identical bytes, and current accepted rights still hold.
        retried=svc.retry_failed(result.export_id);assert retried.attempt==2
        assert svc.run_one().status=='completed'
    assert fired==[1]


def test_export_admission_bound_replay_and_renderer_unavailable(exports,monkeypatch):
    flow,svc=exports;c,_,_,worker=flow;response=submit(c);assert worker.run_one().status=='completed'
    location=response.headers['Location'];key=str(uuid4());accepted=export(c,location,key=key);assert accepted.status_code==202
    for _ in range(19):assert export(c,location).status_code==202
    assert export(c,location).json()['error']['code']=='RESOURCE_LIMIT_EXCEEDED'
    assert export(c,location,key=key).json()['data']==accepted.json()['data']
    monkeypatch.setattr(type(svc.renderer),'available',property(lambda self:False))
    unavailable=export(c,location);assert unavailable.status_code==503 and unavailable.json()['error']['code']=='SERVICE_UNAVAILABLE'
    with Session(c[0][1]) as s:assert s.query(PlanningExport).count()==20
