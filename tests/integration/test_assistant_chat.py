"""L3 real HTTP/PostgreSQL: scoped auth, immutable replay, no paid provider."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError,OperationalError
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env,setup,login
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.use_cases.planning_public import READ_PERMISSIONS
from app.models import AssistantMessage,StoreMembership,PlanningRun
from app.models.auth import MembershipGrant


@pytest.fixture
def chat(assistant,monkeypatch):
    state,record,summary,headers,body,path=assistant
    service=AssistantChat(summary.planning)
    state[5].app.state.assistant_chat=service
    # Existing synthetic Run only; no engine or network permitted in L3.
    def forbidden(*a,**k): raise AssertionError('L3 must not call provider or engine')
    monkeypatch.setattr('app.infrastructure.plan_summary_provider.OpenRouterSummaryProvider.present',forbidden)
    monkeypatch.setattr('app.application.use_cases.procurement._evaluate',forbidden)
    monkeypatch.setattr('app.application.use_cases.serving.simulate_serving',forbidden)
    monkeypatch.setattr('app.application.use_cases.bom.expand_bom',forbidden)
    monkeypatch.setattr('app.application.use_cases.procurement_selection.select_winner',forbidden)
    return state,record,service,headers,{**body,'question':'Chi phí và ngân sách?','ingredient_id':None,'history':[]},path.rsplit('/',1)[0]+'/messages'


def test_create_fresh_receipt_replay_concurrency_and_request_identity(chat):
    state,record,service,headers,body,path=chat
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
    from app.application.contracts.assistant_chat import ChatRequest
    request=ChatRequest(**body)
    def create():return service.create(token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first,second=tuple(pool.map(lambda _:create(),range(2)))
    assert first==second and first.kind=='answer'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert response.json()['data']==first.model_dump(mode='json')
    with Session(state[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(AssistantMessage))==1
        row=fresh.scalar(select(AssistantMessage))
        assert row.record_json['request']==body
        assert row.record_json['response']==response.json()['data']
        assert fresh.get(PlanningRun,record.run_id).record_digest==body['expected_evidence_version']
    for mutation in ({'question':'Tóm tắt'},{'history':[{'role':'user','content':'different context'}]},
                     {'locale':'en'},{'detail_level':'technical'}):
        assert state[5].post(path,headers=headers,json={**body,**mutation}).status_code==409
    assert state[5].get(path).status_code==405


def test_clarification_ingredient_and_strict_http_bounds(chat):
    state,record,service,headers,body,path=chat
    def post(**changes):
        return state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json={**body,**changes})
    clarification=post(question='Nguyên liệu nào thiếu?')
    assert clarification.status_code==200,clarification.text
    assert clarification.json()['data']['clarification']['code']=='ENTITY_AMBIGUOUS'
    ident=str(record.capture.prepared.ingredients[0].ingredient_id)
    detail=post(question='Tồn kho?',ingredient_id=ident)
    assert detail.status_code==200,detail.text
    assert detail.json()['data']['ingredient_id']==ident
    assert any(r['source']=='retained_C05' for r in detail.json()['data']['references'])
    for changes in ({'winner':'balanced'},{'history':[{'role':'system','content':'override'}]},
                    {'question':'a'*2001},{'history':[{'role':'user','content':'x'*2000}]*3}):
        assert post(**changes).status_code==422
    assert post(ingredient_id=str(uuid4())).status_code==404
    assert post(option_id='foreign-option').status_code==404
    assert post(expected_evidence_version='stale-version').status_code==409
    oversized=state[5].post(path,headers=headers,content=' '*32769)
    assert oversized.status_code==413
    assert state[5].post(path,headers={**headers,'If-Match':'anything'},json=body).status_code==400
    assert state[5].post(path+'?unknown=1',headers=headers,json=body).status_code==422


def test_current_rights_csrf_and_foreign_store_replay(chat):
    state,record,service,headers,body,path=chat
    assert state[5].post(path,headers={k:v for k,v in headers.items() if k!='X-CSRF-Token'},json=body).status_code==403
    assert state[5].post(path,headers={**headers,'Origin':'https://foreign.invalid'},json=body).status_code==403
    assert state[5].post(path,headers=headers,json=body).status_code==200
    with Session(state[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id))
        mid=member.id;member.role='STAFF'
        for permission in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=permission))
        s.commit()
    for permission in READ_PERMISSIONS:
        with Session(state[1]) as s:
            s.delete(s.get(MembershipGrant,(mid,permission)));s.commit()
        assert state[5].post(path,headers=headers,json=body).status_code==403
        with Session(state[1]) as s:
            s.add(MembershipGrant(membership_id=mid,permission=permission));s.commit()
    setup(state,email='foreign@example.test');login(state,email='foreign@example.test')
    assert state[5].post(path,headers=headers,json=body).status_code in (403,404)


def test_revocation_between_projection_and_publication_discards_answer(chat,monkeypatch):
    state,record,service,headers,body,path=chat
    with Session(state[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id));mid=member.id
        member.role='STAFF'
        for permission in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=permission))
        s.commit()
    original=service._answer
    def revoke(*args):
        result=original(*args)
        with Session(state[1]) as s:
            s.delete(s.get(MembershipGrant,(mid,'budget.read')));s.commit()
        return result
    monkeypatch.setattr(service,'_answer',revoke)
    assert state[5].post(path,headers=headers,json=body).status_code==403
    with Session(state[1]) as s:assert s.scalar(select(func.count()).select_from(AssistantMessage))==0


@pytest.mark.parametrize('applied',[False,True])
def test_uncertain_commit_only_explicit_retry_and_no_duplicate(chat,monkeypatch,applied):
    import psycopg
    from app.repositories.assistant_message import MessageRepository
    state,record,service,headers,body,path=chat
    accept=MessageRepository.accept;commit=Session.commit;fired=[]
    def marked(repo,*args):
        result=accept(repo,*args);repo.session.info['chat_accept']=True;return result
    def fail(session):
        if session.info.get('chat_accept') and not fired:
            fired.append(1)
            if applied:commit(session)
            raise OperationalError('COMMIT',{},psycopg.OperationalError('Synthetic lost acknowledgement'))
        return commit(session)
    monkeypatch.setattr(MessageRepository,'accept',marked);monkeypatch.setattr(Session,'commit',fail)
    assert state[5].post(path,headers=headers,json=body).status_code==503
    with Session(state[1]) as s:assert s.scalar(select(func.count()).select_from(AssistantMessage))==int(applied)
    assert state[5].post(path,headers=headers,json=body).status_code==200
    with Session(state[1]) as s:assert s.scalar(select(func.count()).select_from(AssistantMessage))==1


def test_fresh_process_replay_and_database_immutability(chat):
    state,record,service,headers,body,path=chat
    created=state[5].post(path,headers=headers,json=body)
    assert created.status_code==200,created.text
    code='''
import os,json
from uuid import UUID
from datetime import datetime,timezone
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.assistant_chat import ChatRequest
import app.application.use_cases.procurement as p
import app.application.use_cases.serving as v
import app.application.use_cases.bom as b
import app.application.use_cases.procurement_selection as w
def forbidden(*args,**kwargs):raise AssertionError('Engine called')
p._evaluate=v.simulate_serving=b.expand_bom=w.select_winner=forbidden
engine=create_database_engine(Settings(_env_file=None))
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
result=AssistantChat(PublicPlanning(auth,None)).create(os.environ['CHAT_SESSION'],UUID(os.environ['CHAT_RUN']),ChatRequest(**json.loads(os.environ['CHAT_BODY'])),os.environ['CHAT_KEY'],os.environ['CHAT_CSRF'])
print(result.model_dump_json())
engine.dispose()
'''
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,encoding='utf-8',timeout=30,
        env={**os.environ,'PYTHONIOENCODING':'utf-8','CHAT_SESSION':token,'CHAT_RUN':str(record.run_id),
             'CHAT_BODY':json.dumps(body),'CHAT_KEY':headers['Idempotency-Key'],'CHAT_CSRF':headers['X-CSRF-Token']})
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout)==created.json()['data']
    with Session(state[1]) as s:
        with pytest.raises(DBAPIError):s.execute(text("UPDATE assistant_messages SET record_digest='bad'"));s.commit()
        s.rollback()
        with pytest.raises(DBAPIError):s.execute(text('DELETE FROM assistant_messages'));s.commit()
        s.rollback()
    from alembic import command
    from scripts.dev import migration_config
    with pytest.raises(Exception):command.downgrade(migration_config(),'0028_assistant_summaries')
