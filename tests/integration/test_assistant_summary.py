"""Owned assistant PostgreSQL, real auth/HTTP, static retained historical graphs."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select,func,text,event
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env,setup,login,ORIGIN
from tests.assistant_cases import retained_record,row_for
from app.models import Store,StoreMembership,PlanningRun,Product
from app.models.plan_summary import PlanSummaryGeneration,PlanSummaryReceipt
from app.models.auth import MembershipGrant
from app.application.use_cases.planning_public import PublicPlanning,READ_PERMISSIONS
from app.application.use_cases.plan_summary import PlanSummaries
from app.application.contracts.plan_summary import SummaryProfile
from app.application.planning_serialization import digest
from app.infrastructure.plan_summary_provider import PresentationResult
from app.application.plan_summary_rendering import DEFAULT_EXPRESSION
from app.application.contracts.plan_summary import SummaryDiagnostics


@pytest.fixture
def assistant(env):
    from sqlalchemy.engine import make_url
    target = make_url(env[0].database_url)
    assert (target.database, target.username, target.host, target.port) in {
        ('shelfcash_assistant_test', 'shelfcash_assistant_tester', '127.0.0.1', 5436),
        ('shelfcash_integration_test', 'shelfcash_integration_tester', '127.0.0.1', 5441),
        # Separate recovery/handoff integration instance; never reuse sibling L5 DB.
        ('shelfcash_integration_test', 'shelfcash_integration_tester', '127.0.0.1', 5442),
        # Dedicated PDF integration instance; no Summary/L5/demo DB reuse.
        ('shelfcash_integration_test', 'shelfcash_integration_tester', '127.0.0.1', 5447),
    }, 'Only the owned Assistant or L5 disposable target'
    owner=setup(env)
    record=retained_record(actor_id=owner.user_id)
    row=row_for(record)
    with Session(env[1]) as s:
        s.add(Store(id=record.store_id,name='Frozen synthetic Store',timezone='UTC',currency='VND',active=True))
        s.flush()
        s.add(StoreMembership(store_id=record.store_id,user_id=owner.user_id,role='OWNER',active=True))
        s.add(PlanningRun(**vars(row)))
        s.commit()
    wire=login(env).json()['data']
    public=PublicPlanning(env[2],env[5].app.state.forecast_serving)
    class Off:
        def present(self,*a): raise AssertionError('Disabled model must never be invoked')
    service=PlanSummaries(public,SummaryProfile(model='UNCONFIGURED'),Off(),clock=env[2].clock)
    env[5].app.state.plan_summaries=service
    env[5].app.state.planning_public=public
    headers={'Origin':ORIGIN,'X-CSRF-Token':wire['session']['csrf_token'],'Idempotency-Key':str(uuid4())}
    body=dict(expected_evidence_version=row.record_digest,option_id=None,locale='vi',detail_level='simple')
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/summary'
    return env,record,service,headers,body,path


def test_create_execute_fresh_read_replay_and_no_implicit_get(assistant):
    env,record,service,headers,body,path=assistant
    response=env[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    data=response.json()['data']
    assert data['status']=='completed' and data['result']['source']=='deterministic_fallback'
    assert data['result']['diagnostics']['reason']=='MODEL_DISABLED'
    assert env[5].get(path+'/'+data['generation_id']).json()['data']==data
    assert env[5].post(path,headers=headers,json=body).json()['data']==data
    # A new key for the same generation identity does not create a duplicate.
    assert env[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=body).json()['data']==data
    assert env[5].post(path,headers=headers,json={**body,'locale':'en'}).status_code==409
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PlanSummaryGeneration))==1
        assert fresh.scalar(select(func.count()).select_from(PlanSummaryReceipt))==2
        assert fresh.get(PlanningRun,record.run_id).record_digest==body['expected_evidence_version']
        fresh.add(Product(id=record.capture.menu[0].product_id,store_id=record.store_id,name='Live injected name',selling_unit='different-unit',active=True))
        from app.models.planning_configuration import PlanningBudget
        fresh.add(PlanningBudget(store_id=record.store_id,version='live-budget-99',amount='99999',updated_at=env[4][0],updated_by=record.actor_id))
        fresh.get(Store,record.store_id).name='Changed live Store'
        fresh.commit()
    # New reader cache and new Session after unrelated live changes preserve history.
    env[5].app.state.plan_summaries=PlanSummaries(PublicPlanning(env[2],env[5].app.state.forecast_serving),service.profile,service.provider)
    assert env[5].get(path+'/'+data['generation_id']).json()['data']==data
    code='''
import os,json
from sqlalchemy.orm import Session
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.repositories.planning import PlanningRepository
from app.application.planning_retained_reads import VerifiedPlanningReads
from uuid import UUID
import app.application.use_cases.procurement as p
import app.application.use_cases.serving as v
import app.application.use_cases.bom as b
import app.application.use_cases.procurement_selection as w
def forbidden(*a,**k):raise AssertionError('Engine called on cold process read')
p._evaluate=v.simulate_serving=b.expand_bom=w.select_winner=w.selection_facts=forbidden
engine=create_database_engine(Settings(_env_file=None))
with Session(engine) as s:
 row=PlanningRepository(s).get(UUID(os.environ['ASSISTANT_STORE']),UUID(os.environ['ASSISTANT_RUN']))
 record,view=VerifiedPlanningReads().read(row,evidence=True)
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.plan_summary import PlanSummaries
from app.application.contracts.plan_summary import SummaryProfile
from datetime import datetime,timezone
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Off:
 def present(self,*a):raise AssertionError('GET called provider')
service=PlanSummaries(PublicPlanning(auth,None),SummaryProfile(model='UNCONFIGURED'),Off())
summary=service.read(os.environ['ASSISTANT_SESSION'],record.run_id,UUID(os.environ['ASSISTANT_GENERATION']))
print(json.dumps(dict(digest=view.response_version,outcome=record.outcome,summary=summary.model_dump(mode='json'))))
engine.dispose()
'''
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,
        env={**os.environ,'ASSISTANT_STORE':str(record.store_id),'ASSISTANT_RUN':str(record.run_id),
             'ASSISTANT_GENERATION':data['generation_id'],
             'ASSISTANT_SESSION':env[5].cookies.get('__Host-shelfcash_session') or env[5].cookies.get('shelfcash_dev_session')},timeout=30)
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout)['digest']==body['expected_evidence_version']
    assert json.loads(child.stdout)['summary']==data


def test_default_router_is_accepted_at_application_publication(assistant):
    state,record,service,headers,body,path=assistant
    class Router:
        def present(self,*args):
            return PresentationResult(DEFAULT_EXPRESSION,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',
                requested_model='synthetic-model',resolved_model='synthetic-model',resolved_provider='Google',attempts=1))
    service.profile=SummaryProfile(enabled=True,model='synthetic-model')
    service.provider=Router()
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert response.json()['data']['result']['source']=='model_presentation'


def test_sensitive_rights_revocation_and_foreign_store(assistant):
    env,record,service,headers,body,path=assistant
    created=env[5].post(path,headers=headers,json=body).json()['data']
    with Session(env[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id))
        member.role='STAFF'
        for right in READ_PERMISSIONS: s.add(MembershipGrant(membership_id=member.id,permission=right))
        s.commit()
    assert env[5].get(path+'/'+created['generation_id']).status_code==200
    for right in READ_PERMISSIONS:
        with Session(env[1]) as s:
            row=s.scalar(select(MembershipGrant).where(MembershipGrant.permission==right))
            mid=row.membership_id;s.delete(row);s.commit()
        assert env[5].get(path+'/'+created['generation_id']).status_code==403
        assert env[5].post(path,headers=headers,json=body).status_code==403
        with Session(env[1]) as s:
            s.add(MembershipGrant(membership_id=mid,permission=right));s.commit()
    other=setup(env,email='other@example.test')
    login(env,email='other@example.test')
    assert env[5].get(path+'/'+created['generation_id']).status_code==404
    assert env[5].post(path,headers=headers,json=body).status_code in (403,404)


def test_mock_generation_concurrent_once_transaction_closed_and_late_writer(assistant):
    env,record,service,headers,body,path=assistant
    entered,released=Event(),Event()
    class Mock:
        calls=0
        def present(self,payload,profile):
            self.calls+=1
            # Separate connection can update canonical Store while provider waits;
            # application authority locks/transaction have been released.
            with Session(env[1]) as fresh:
                fresh.execute(text("SET LOCAL lock_timeout='1s'"))
                fresh.get(Store,record.store_id).name='Live changed during provider'
                fresh.commit()
            entered.set()
            assert released.wait(20)
            return PresentationResult(DEFAULT_EXPRESSION,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',requested_model='mock-qwen',attempts=1))
    provider=Mock()
    service.profile=SummaryProfile(enabled=True,model='mock-qwen',providers=('mock',))
    service.provider=provider
    token=env[5].cookies.get('shelfcash_dev_session') or env[5].cookies.get('__Host-shelfcash_session')
    from app.application.contracts.plan_summary import SummaryRequest
    request=SummaryRequest(**body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(service.create,token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
        assert entered.wait(20)
        for key in (headers['Idempotency-Key'],str(uuid4())):
            with pytest.raises(Exception) as error:
                service.create(token,record.run_id,request,key,headers['X-CSRF-Token'])
            assert error.value.code=='GENERATION_IN_PROGRESS'
        released.set()
        result=first.result(timeout=25)
    assert provider.calls==1 and result.result.source=='model_presentation'
    from app.application.use_cases.plan_summary import decode_summary
    with Session(env[1]) as s:
        old=decode_summary(s.scalar(select(PlanSummaryGeneration)))
    with pytest.raises(Exception) as error: service._publish(old,result.result,token=token,csrf=headers['X-CSRF-Token'])
    assert error.value.code=='STALE_SUMMARY_CLAIM'
    assert service.create(token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])==result


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_real_lost_commit_ack_reconciles_without_duplicate_generation(assistant,monkeypatch,phase):
    import psycopg
    from sqlalchemy.exc import OperationalError
    env,record,service,headers,body,path=assistant
    original=Session.commit;fired=[]
    def fault(session):
        target=session.info.get('summary_accept') if phase=='acceptance' else session.info.get('summary_transition')=='completed'
        original(session)
        if target and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED lost summary ACK'),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',fault)
    response=env[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert fired==[1]
    assert env[5].post(path,headers=headers,json=body).json()['data']==response.json()['data']
    with Session(env[1]) as s:
        assert s.scalar(select(func.count()).select_from(PlanSummaryGeneration))==1


def test_revocation_during_mock_discards_output_and_new_key_can_retry(assistant):
    env,record,service,headers,body,path=assistant
    with Session(env[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id))
        member.role='STAFF';mid=member.id
        for right in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=right))
        s.commit()
    class Revoke:
        calls=0
        def present(self,*args):
            self.calls+=1
            if self.calls==1:
                with Session(env[1]) as s:
                    s.delete(s.get(MembershipGrant,(mid,'budget.read')));s.commit()
            return PresentationResult(DEFAULT_EXPRESSION,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',requested_model='mock-qwen',attempts=1))
    provider=Revoke()
    service.profile=SummaryProfile(enabled=True,model='mock-qwen',providers=('mock',));service.provider=provider
    assert env[5].post(path,headers=headers,json=body).status_code==403
    with Session(env[1]) as s:
        generation=s.scalar(select(PlanSummaryGeneration))
        assert generation.status=='failed' and generation.record_json['result'] is None
        assert generation.record_json['error_code']=='AUTHORITY_CHANGED'
        s.add(MembershipGrant(membership_id=mid,permission='budget.read'));s.commit()
    retry=env[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=body)
    assert retry.status_code==200,retry.text
    assert retry.json()['data']['status']=='completed' and provider.calls==2


def test_additive_migration_parity_and_terminal_immutability(assistant):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from scripts.dev import migration_config
    from app.infrastructure.database.base import Base
    from sqlalchemy.exc import DBAPIError
    env,record,service,headers,body,path=assistant
    command.downgrade(migration_config(),'0027_self_service_stores')
    command.upgrade(migration_config(),'head')
    with env[1].connect() as c:
        assert compare_metadata(MigrationContext.configure(c,opts={'compare_server_default':True}),Base.metadata)==[]
    result=env[5].post(path,headers=headers,json=body)
    assert result.status_code==200,result.text
    with Session(env[1]) as s:
        assert s.get(PlanningRun,record.run_id).record_digest==body['expected_evidence_version']
        with pytest.raises(DBAPIError):
            s.execute(text("UPDATE plan_summary_generations SET status='running'"));s.commit()
        s.rollback()
    with pytest.raises(Exception):command.downgrade(migration_config(),'0027_self_service_stores')


def test_dead_process_explicit_replay_never_reissues_provider_attempt(assistant):
    env,record,service,headers,body,path=assistant
    code='''
import os,json
from uuid import UUID
from datetime import datetime,timezone
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.plan_summary import PlanSummaries
from app.application.contracts.plan_summary import SummaryProfile,SummaryRequest
engine=create_database_engine(Settings(_env_file=None))
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Crash:
 def present(self,*args):os._exit(17)
service=PlanSummaries(PublicPlanning(auth,None),SummaryProfile(enabled=True,model='mock-qwen',providers=('mock',)),Crash(),clock=auth.clock)
service.create(os.environ['ASSISTANT_SESSION'],UUID(os.environ['ASSISTANT_RUN']),SummaryRequest(**json.loads(os.environ['ASSISTANT_BODY'])),os.environ['ASSISTANT_KEY'],os.environ['ASSISTANT_CSRF'])
'''
    token=env[5].cookies.get('__Host-shelfcash_session') or env[5].cookies.get('shelfcash_dev_session')
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=30,
        env={**os.environ,'ASSISTANT_RUN':str(record.run_id),'ASSISTANT_BODY':json.dumps(body),
            'ASSISTANT_SESSION':token,'ASSISTANT_KEY':headers['Idempotency-Key'],'ASSISTANT_CSRF':headers['X-CSRF-Token']})
    assert child.returncode==17,child.stderr
    with Session(env[1]) as s:
        row=s.scalar(select(PlanSummaryGeneration));ident=row.id
        assert row.status=='running'
    read=env[5].get(path+'/'+str(ident))
    assert read.status_code==200 and read.json()['data']['status']=='running'
    replay=env[5].post(path,headers=headers,json=body)
    assert replay.status_code==200,replay.text
    assert replay.json()['data']['status']=='failed'
    assert replay.json()['data']['error_code']=='PROCESS_INTERRUPTED'
    assert replay.json()['data']['result'] is None


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_unapplied_commit_failure_does_not_fabricate_success(assistant,monkeypatch,phase):
    import psycopg
    from sqlalchemy.exc import OperationalError
    env,record,service,headers,body,path=assistant
    original=Session.commit;fired=[]
    def fault(session):
        target=session.info.get('summary_accept') if phase=='acceptance' else session.info.get('summary_transition')=='completed'
        if target and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('INJECTED before summary commit'),connection_invalidated=False)
        return original(session)
    monkeypatch.setattr(Session,'commit',fault)
    response=env[5].post(path,headers=headers,json=body)
    assert response.status_code==503,response.text
    with Session(env[1]) as s:
        rows=tuple(s.scalars(select(PlanSummaryGeneration)))
        if phase=='acceptance':assert rows==()
        else:assert len(rows)==1 and rows[0].status=='failed' and rows[0].record_json['result'] is None


@pytest.mark.parametrize('failure,reason',[('schema','SCHEMA_REJECTED'),('timeout','PROVIDER_UNAVAILABLE'),('input','INPUT_LIMIT')])
def test_provider_failures_publish_complete_deterministic_fallback(assistant,failure,reason):
    from tests.unit.test_plan_summary import Transport
    from app.infrastructure.plan_summary_provider import OpenRouterSummaryProvider
    from pydantic import SecretStr
    env,record,service,headers,body,path=assistant
    transport=Transport(TimeoutError() if failure=='timeout' else {'answer':'BALANCED đã được chọn vì nhu cầu cao.'})
    service.profile=SummaryProfile(enabled=True,model='synthetic-qwen',providers=('SYNTHETIC_PROVIDER',),input_bytes=1000 if failure=='input' else 16000)
    service.provider=OpenRouterSummaryProvider(SecretStr('synthetic-only'),opener=transport)
    result=env[5].post(path,headers=headers,json=body)
    assert result.status_code==200,result.text
    data=result.json()['data']
    assert data['status']=='completed' and data['result']['source']=='deterministic_fallback'
    assert data['result']['diagnostics']['reason']==reason and len(data['result']['claims'])==6
    assert transport.calls==(0 if failure=='input' else 1)
    assert env[5].get(path+'/'+data['generation_id']).json()['data']==data
    assert env[5].post(path,headers=headers,json=body).json()['data']==data
    assert transport.calls==(0 if failure=='input' else 1)


def test_mutation_csrf_origin_and_client_fact_guards_precede_acceptance(assistant):
    env,record,service,headers,body,path=assistant
    missing={k:v for k,v in headers.items() if k!='X-CSRF-Token'}
    for forged in (missing,{**headers,'X-CSRF-Token':'invalid'},{**headers,'Origin':'https://foreign.example.test'}):
        response=env[5].post(path,headers=forged,json=body)
        assert response.status_code==403,response.text
    for extra in ({'winner':'balanced'},{'proof':'CERTIFIED'},{'history':[]}):
        assert env[5].post(path,headers=headers,json={**body,**extra}).status_code==422
    assert env[5].post(path,headers=headers,json={**body,'expected_evidence_version':'foreign-version'}).status_code==409
    with Session(env[1]) as s:
        assert s.scalar(select(func.count()).select_from(PlanSummaryGeneration))==0
        assert s.scalar(select(func.count()).select_from(PlanSummaryReceipt))==0
