"""Real retained PostgreSQL/HTTP, fake narrative provider only; no network."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session

from tests.integration.test_assistant_summary import assistant, env
from app.application.contracts.plan_summary import SummaryProfile,SummaryDiagnostics
from app.application.contracts.summary_narrative import SummaryNarrative, NarrativeSection, NarrativeClause
from app.application.use_cases.plan_summary import PlanSummaries, decode_summary
from app.application.use_cases.planning_public import PublicPlanning, READ_PERMISSIONS
from app.infrastructure.plan_summary_provider import PresentationResult
from app.models.plan_summary import PlanSummaryGeneration,PlanSummaryReceipt
from app.models import PlanningRun, StoreMembership
from app.models.auth import MembershipGrant


class FakeNarrative:
    calls = 0
    def present(self,payload,profile):
        self.calls += 1
        body=json.loads(payload)
        assert body['task']=='plan_summary_narrative/2'
        def section(family):
            return NarrativeSection(family=family,clauses=tuple(NarrativeClause(fact_id=f['fact_id'],
                text=f['surfaces'][-1],evidence_ids=f['evidence_ids']) for f in body['facts'] if f['family']==family))
        narrative=SummaryNarrative(schema_version='summary_narrative/2',headline=section('outcome'),summary=section('cost'),
            key_points=tuple(section(k) for k in ('requirements','coverage','proof')),warning_summary=section('limitations'))
        return PresentationResult(None,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',
            requested_model=profile.model,resolved_model=profile.model,attempts=1),narrative)


def enable(service, provider=None):
    service.profile=SummaryProfile(enabled=True,model='synthetic-summary',version='summary_profile/2',max_tokens=3072)
    service.provider=provider or FakeNarrative()
    return service.provider


@pytest.mark.parametrize('assistant',['stock','purchase','infeasible','failed-partial'],indirect=True)
def test_narrative_publication_fresh_session_and_replay_of_each_terminal_state(assistant,request):
    state,record,service,headers,body,path=assistant
    provider=enable(service)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    data=response.json()['data']
    result=data['result']
    assert result['source']=='model_presentation' and result['renderer_version']=='plan_summary_renderer/2'
    assert result['diagnostics']['validator_version']=='summary_narrative_guard/2'
    with Session(state[1]) as fresh:
        row=fresh.scalar(select(PlanSummaryGeneration))
        assert decode_summary(row).result.model_dump(mode='json')==result
        assert fresh.get(PlanningRun,record.run_id).record_digest==body['expected_evidence_version']
    # Fresh service/profile/cache after publication must read the same retained text.
    class Forbidden:
        def present(self,*args):raise AssertionError('Replay invoked provider')
    state[5].app.state.plan_summaries=PlanSummaries(PublicPlanning(state[2],None),SummaryProfile(model='UNCONFIGURED'),Forbidden())
    assert state[5].get(path+'/'+data['generation_id']).json()['data']==data
    assert state[5].post(path,headers=headers,json=body).json()['data']==data
    assert provider.calls==1
    if request.node.callspec.params['assistant']=='stock':
        # A separate interpreter has no in-memory cache and must replay profile/2.
        code='''
import os,json
from uuid import UUID
from datetime import datetime,timezone
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.plan_summary import PlanSummaries
from app.application.contracts.plan_summary import SummaryProfile
engine=create_database_engine(Settings(_env_file=None))
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Forbidden:
 def present(self,*a): raise AssertionError('Cold read called provider')
service=PlanSummaries(PublicPlanning(auth,None),SummaryProfile(model='UNCONFIGURED'),Forbidden())
print(json.dumps(service.read(os.environ['SUMMARY_TEST_SESSION'],UUID(os.environ['SUMMARY_TEST_RUN']),UUID(os.environ['SUMMARY_TEST_GENERATION'])).model_dump(mode='json')))
engine.dispose()
'''
        child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=30,
            env={**os.environ,'SUMMARY_TEST_RUN':str(record.run_id),'SUMMARY_TEST_GENERATION':data['generation_id'],
                 'SUMMARY_TEST_SESSION':state[5].cookies.get('shelfcash_dev_session') or state[5].cookies.get('__Host-shelfcash_session')})
        assert child.returncode==0,child.stderr
        assert json.loads(child.stdout)==data


def test_legacy_generation_keeps_original_bytes_and_new_identity_is_separate(assistant):
    state,record,service,headers,body,path=assistant
    legacy=state[5].post(path,headers=headers,json=body).json()['data']
    assert legacy['result']['renderer_version']=='plan_summary_renderer/1'
    with Session(state[1]) as fresh:
        before=fresh.scalar(select(PlanSummaryGeneration)).record_json
    provider=enable(service)
    assert state[5].post(path,headers=headers,json=body).json()['data']==legacy
    assert provider.calls==0
    current=state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=body).json()['data']
    assert current['generation_id']!=legacy['generation_id'] and provider.calls==1
    with Session(state[1]) as fresh:
        assert fresh.get(PlanSummaryGeneration,legacy['generation_id']).record_json==before
        assert fresh.scalar(select(func.count()).select_from(PlanSummaryGeneration))==2
    assert state[5].get(path+'/'+legacy['generation_id']).json()['data']==legacy


@pytest.mark.parametrize('fault',['false_prose','missing_main','timeout'])
def test_bad_narrative_falls_back_and_never_retries_on_read(assistant,fault):
    state,record,service,headers,body,path=assistant
    class Bad(FakeNarrative):
        def present(self,*args):
            if fault=='timeout':
                self.calls+=1
                raise TimeoutError()
            presented=super().present(*args)
            raw=presented.narrative.model_dump(mode='json')
            if fault=='false_prose':raw['headline']['clauses'][0]['text']='Không khả thi; xác suất đáp ứng 99%.'
            else:raw['headline']['clauses']=raw['summary']['clauses'][:1]
            return PresentationResult(None,presented.diagnostics,SummaryNarrative.model_validate(raw))
    provider=enable(service,Bad())
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    data=response.json()['data']
    assert data['result']['source']=='deterministic_fallback'
    assert data['result']['diagnostics']['reason']==('PROVIDER_UNAVAILABLE' if fault=='timeout' else 'GROUNDING_REJECTED')
    assert data['result']['renderer_version']=='plan_summary_renderer/2'
    assert state[5].get(path+'/'+data['generation_id']).json()['data']==data
    assert state[5].post(path,headers=headers,json=body).json()['data']==data
    assert provider.calls==1


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_narrative_uncertain_commit_reconciles_exact_retained_response(assistant,monkeypatch,phase):
    import psycopg
    from sqlalchemy.exc import OperationalError
    state,record,service,headers,body,path=assistant
    provider=enable(service)
    original=Session.commit; fired=[]
    def commit(session):
        target=session.info.get('summary_accept') if phase=='acceptance' else session.info.get('summary_transition')=='completed'
        original(session)
        if target and not fired:
            fired.append(1)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('Synthetic lost ACK'),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',commit)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert state[5].post(path,headers=headers,json=body).json()['data']==response.json()['data']
    assert fired==[1] and provider.calls==1
    with Session(state[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PlanSummaryGeneration))==1
        assert decode_summary(fresh.scalar(select(PlanSummaryGeneration))).result.model_dump(mode='json')==response.json()['data']['result']


def test_narrative_concurrency_and_transaction_closed(assistant):
    state,record,service,headers,body,path=assistant
    entered,released=Event(),Event()
    class Waiting(FakeNarrative):
        def present(self,*args):
            assert state[1].pool.checkedout()==0
            entered.set()
            assert released.wait(20)
            return super().present(*args)
    provider=enable(service,Waiting())
    token=state[5].cookies.get('shelfcash_dev_session') or state[5].cookies.get('__Host-shelfcash_session')
    from app.application.contracts.plan_summary import SummaryRequest
    request=SummaryRequest(**body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(service.create,token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
        assert entered.wait(20)
        try:
            with pytest.raises(Exception) as error:service.create(token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
            assert error.value.code=='GENERATION_IN_PROGRESS'
        finally:released.set()
        result=future.result(timeout=25)
    assert result.result.source=='model_presentation' and provider.calls==1
    with Session(state[1]) as fresh:retained=decode_summary(fresh.scalar(select(PlanSummaryGeneration)))
    with pytest.raises(Exception) as error:service._publish(retained,result.result,token=token,csrf=headers['X-CSRF-Token'])
    assert error.value.code=='STALE_SUMMARY_CLAIM'


@pytest.mark.parametrize('phase',['dispatch','publication'])
def test_current_rights_fences_before_dispatch_and_after_provider(assistant,monkeypatch,phase):
    state,record,service,headers,body,path=assistant
    with Session(state[1]) as session:
        member=session.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id))
        member.role='STAFF';mid=member.id
        for right in READ_PERMISSIONS:session.add(MembershipGrant(membership_id=mid,permission=right))
        session.commit()
    def revoke():
        with Session(state[1]) as session:
            session.delete(session.get(MembershipGrant,(mid,'budget.read')));session.commit()
    class Revoke(FakeNarrative):
        def present(self,*args):
            result=super().present(*args)
            if phase=='publication':revoke()
            return result
    provider=enable(service,Revoke())
    if phase=='dispatch':
        import app.application.use_cases.plan_summary as use_case
        original=use_case.payload_for
        def payload(*args):
            value=original(*args);revoke();return value
        monkeypatch.setattr(use_case,'payload_for',payload)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==403,response.text
    assert provider.calls==(0 if phase=='dispatch' else 1)
    with Session(state[1]) as fresh:
        row=fresh.scalar(select(PlanSummaryGeneration))
        assert row.status=='failed' and row.record_json['result'] is None
        assert row.record_json['error_code']=='AUTHORITY_CHANGED'
