"""Provider outside transaction, immutable grounded final, retained restart/replay."""
import json,os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError,DBAPIError
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.chat_generation import ChatProfile,ConversationalOutput,ModelStatement,FactCard
from app.application.contracts.assistant_chat import ChatRequest,ChatDiagnostics
from app.application.chat_grounding import canonical_clause
from app.application.chat_assertions import proposal
from app.application.contracts.chat_generation import SemanticOutput
from app.infrastructure.conversational_provider import ChatProviderResult
from app.models import ChatGenerationRow,AssistantMessage,StoreMembership,PlanningRun
from app.models.auth import MembershipGrant
from app.application.use_cases.planning_public import READ_PERMISSIONS


class Valid:
    calls=0
    def generate(self,payload,profile,*,before_completion=None):
        if before_completion:before_completion()
        self.calls+=1
        cards=[FactCard(**{k:v for k,v in f.items() if k!='wording'}) for f in payload['facts']]
        statements=[]
        for card in cards:
            text=canonical_clause(card,payload['language'])+'.'
            if card.kind=='total':text=f'Phương án này có tổng chi phí là {card.display} {card.unit}.'
            statements.append(proposal(card,text))
        return ChatProviderResult(SemanticOutput(assertions=tuple(statements)),ChatDiagnostics(reason='NONE',
            disposition='ACCEPTED',model=profile.model,resolved_model=profile.model,provider='Synthetic',attempts=1,
            prompt_version='conversational_chat_prompt/3',validator_version='chat_assertions/3'))


@pytest.fixture
def conversation(assistant):
    state,record,summary,headers,body,path=assistant
    provider=Valid();service=AssistantChat(summary.planning,ChatProfile(enabled=True,model='synthetic-gemini'),provider)
    state[5].app.state.assistant_chat=service
    return state,record,service,headers,{**body,'question':'Kế hoạch này tốn bao nhiêu?','ingredient_id':None,'history':[]},path.rsplit('/',1)[0]+'/messages'


def test_actual_as03_free_prose_durable_replay_profile_change_and_no_get_generation(conversation):
    state,record,service,headers,body,path=conversation;provider=service.provider
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    answer=response.json()['data'];assert answer['source']=='model' and 'Phương án này có tổng chi phí' in answer['answer']
    with Session(state[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ChatGenerationRow))==1
        generation=fresh.scalar(select(ChatGenerationRow));assert generation.status=='completed'
        assert generation.record_json['profile']['model']=='synthetic-gemini'
        assert generation.record_json['output']['assertions']
        assert fresh.scalar(select(AssistantMessage)).record_json['response']==answer
        assert fresh.get(PlanningRun,record.run_id).record_digest==body['expected_evidence_version']
    service.profile=ChatProfile(enabled=False,model='different-config')
    assert state[5].post(path,headers=headers,json=body).json()['data']==answer
    assert provider.calls==1
    assert state[5].get(path).status_code==405
    assert state[5].post(path,headers=headers,json={**body,'question':'Changed question'}).status_code==409
    assert provider.calls==1


def test_concurrent_provider_once_closed_sessions_and_stale_terminal_writer(conversation):
    state,record,service,headers,body,path=conversation;entered,released=Event(),Event()
    class Waiting(Valid):
        def generate(self,payload,profile,**kwargs):
            assert service.engine.pool.checkedout()==0
            entered.set();assert released.wait(20)
            # Mutating current configuration cannot relabel an accepted call.
            service.profile=ChatProfile(enabled=False,model='changed-profile')
            return super().generate(payload,profile,**kwargs)
    provider=Waiting();service.provider=provider
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
    request=ChatRequest(**body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(service.create,token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
        assert entered.wait(20)
        with pytest.raises(Exception) as error:service.create(token,record.run_id,request,headers['Idempotency-Key'],headers['X-CSRF-Token'])
        assert error.value.code=='GENERATION_IN_PROGRESS'
        released.set();answer=future.result(timeout=30)
    assert answer.source=='model' and provider.calls==1
    from app.application.use_cases.conversational_chat import ConversationalChat,decode_generation
    with Session(state[1]) as s:claimed=decode_generation(s.scalar(select(ChatGenerationRow)))
    with pytest.raises(Exception) as error:ConversationalChat(service).publish(claimed,answer,claimed.output,token=token,csrf=headers['X-CSRF-Token'])
    assert error.value.code=='STALE_CHAT_CLAIM'


@pytest.mark.parametrize('failure,reason',[('wrong','GROUNDING_REJECTED'),('missing','COVERAGE_REJECTED'),('timeout','PROVIDER_UNAVAILABLE')])
def test_rejection_fallback_keeps_topic_coverage_and_replay(conversation,failure,reason):
    state,record,service,headers,body,path=conversation
    class Bad(Valid):
        def generate(self,*args,**kwargs):
            if failure=='timeout':self.calls+=1;raise TimeoutError()
            result=super().generate(*args,**kwargs);statements=result.output.assertions
            output=result.output.model_copy(update={'assertions':tuple(a for a in statements if a.fact_id not in args[0]['required']) if failure=='missing' else
                (statements[0].model_copy(update={'text':'Tổng chi là 9000 kg vì nhu cầu tăng.'}),*statements[1:])})
            return ChatProviderResult(output,result.diagnostics)
    provider=Bad();service.provider=provider
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    result=response.json()['data']
    assert result['source']=='deterministic_fallback' and result['diagnostics']['reason']==reason
    assert 'Tổng chi' in result['answer'] and result['claims']
    assert state[5].post(path,headers=headers,json=body).json()['data']==result
    assert provider.calls==1


def test_revocation_during_provider_discards_output_and_denies_replay(conversation):
    state,record,service,headers,body,path=conversation
    with Session(state[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id));mid=member.id;member.role='STAFF'
        for p in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=p))
        s.commit()
    class Revoke(Valid):
        def generate(self,*args,**kwargs):
            answer=super().generate(*args,**kwargs)
            with Session(state[1]) as s:s.delete(s.get(MembershipGrant,(mid,'budget.read')));s.commit()
            return answer
    provider=Revoke();service.provider=provider
    assert state[5].post(path,headers=headers,json=body).status_code==403
    assert state[5].post(path,headers=headers,json=body).status_code==403
    assert provider.calls==1
    with Session(state[1]) as s:
        row=s.scalar(select(ChatGenerationRow));assert row.status=='failed' and row.record_json['result'] is None
        assert s.scalar(select(func.count()).select_from(AssistantMessage))==0


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_applied_lost_ack_reconciles_exact_record_without_second_completion(conversation,monkeypatch,phase):
    import psycopg
    state,record,service,headers,body,path=conversation;commit=Session.commit;fired=[]
    def fail(session):
        target=session.info.get('chat_accept') if phase=='acceptance' else session.info.get('chat_transition')=='completed'
        commit(session)
        if target and not fired:
            fired.append(1);raise OperationalError('COMMIT',{},psycopg.OperationalError('Synthetic lost ACK'),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',fail)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert state[5].post(path,headers=headers,json=body).json()['data']==response.json()['data']
    assert service.provider.calls==1 and fired==[1]


@pytest.mark.parametrize('phase',['acceptance','terminal'])
def test_unapplied_commit_never_fabricates_success_or_repeats_unknown_completion(conversation,monkeypatch,phase):
    import psycopg
    state,record,service,headers,body,path=conversation;commit=Session.commit;fired=[]
    def fail(session):
        target=session.info.get('chat_accept') if phase=='acceptance' else session.info.get('chat_transition')=='completed'
        if target and not fired:
            fired.append(1);raise OperationalError('COMMIT',{},psycopg.OperationalError('Synthetic unapplied commit'))
        return commit(session)
    monkeypatch.setattr(Session,'commit',fail)
    assert state[5].post(path,headers=headers,json=body).status_code==503
    if phase=='acceptance':
        assert service.provider.calls==0
        assert state[5].post(path,headers=headers,json=body).status_code==200
    else:
        assert service.provider.calls==1
        assert state[5].post(path,headers=headers,json=body).status_code==409
        assert service.provider.calls==1


def test_model_result_fresh_process_and_terminal_immutability(conversation):
    state,record,service,headers,body,path=conversation
    response=state[5].post(path,headers=headers,json=body);assert response.status_code==200,response.text
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
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
engine=create_database_engine(Settings(_env_file=None))
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Never:
 def generate(self,*args):raise AssertionError('Replay called model')
service=AssistantChat(PublicPlanning(auth,None),provider=Never())
result=service.create(os.environ['CHAT_SESSION'],UUID(os.environ['CHAT_RUN']),ChatRequest(**json.loads(os.environ['CHAT_BODY'])),os.environ['CHAT_KEY'],os.environ['CHAT_CSRF'])
print(result.model_dump_json());engine.dispose()
'''
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,encoding='utf-8',timeout=30,
        env={**os.environ,'PYTHONIOENCODING':'utf-8','CHAT_SESSION':token,'CHAT_RUN':str(record.run_id),
             'CHAT_BODY':json.dumps(body),'CHAT_KEY':headers['Idempotency-Key'],'CHAT_CSRF':headers['X-CSRF-Token']})
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout)==response.json()['data']
    with Session(state[1]) as s:
        with pytest.raises(DBAPIError):s.execute(text("UPDATE chat_generations SET status='running'"));s.commit()
        s.rollback()
    from alembic import command
    from scripts.dev import migration_config
    with pytest.raises(Exception):command.downgrade(migration_config(),'0029_assistant_messages')


def test_dead_process_replay_never_repeats_ambiguous_provider_work(conversation):
    state,record,service,headers,body,path=conversation
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
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
from app.application.contracts.chat_generation import ChatProfile
engine=create_database_engine(Settings(_env_file=None))
auth=AuthUseCases(engine,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Crash:
 def generate(self,*args,**kwargs):os._exit(17)
service=AssistantChat(PublicPlanning(auth,None),ChatProfile(enabled=True,model='synthetic-gemini'),Crash())
service.create(os.environ['CHAT_SESSION'],UUID(os.environ['CHAT_RUN']),ChatRequest(**json.loads(os.environ['CHAT_BODY'])),os.environ['CHAT_KEY'],os.environ['CHAT_CSRF'])
'''
    child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,encoding='utf-8',timeout=30,
        env={**os.environ,'PYTHONIOENCODING':'utf-8','CHAT_SESSION':token,'CHAT_RUN':str(record.run_id),
             'CHAT_BODY':json.dumps(body),'CHAT_KEY':headers['Idempotency-Key'],'CHAT_CSRF':headers['X-CSRF-Token']})
    assert child.returncode==17,child.stderr
    with Session(state[1]) as s:assert s.scalar(select(ChatGenerationRow)).status=='running'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==409 and response.json()['error']['code']=='GENERATION_FAILED'
    assert service.provider.calls==0
    with Session(state[1]) as s:
        row=s.scalar(select(ChatGenerationRow));assert row.status=='failed' and row.record_json['error_code']=='PROCESS_INTERRUPTED'


def test_foreign_store_denial_precedes_provider_materialization(conversation):
    from tests.integration.test_auth_public import setup,login
    state,record,service,headers,body,path=conversation
    setup(state,email='foreign-conversation@example.test')
    session=login(state,email='foreign-conversation@example.test').json()['data']['session']
    headers={**headers,'X-CSRF-Token':session['csrf_token']}
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code in (403,404) and response.json()['data'] is None
    assert service.provider.calls==0


def test_model_off_natural_question_uses_same_factual_family_and_preserves_receipt(conversation):
    state,record,service,headers,body,path=conversation
    service.profile=ChatProfile(enabled=False,model='synthetic-gemini')
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    result=response.json()['data']
    assert result['source']=='deterministic_fallback' and 'Tổng chi' in result['answer']
    assert result['diagnostics']['validator_version']=='decision_chat_renderer/4'
    service.profile=ChatProfile(enabled=True,model='synthetic-gemini')
    assert state[5].post(path,headers=headers,json=body).json()['data']==result
    assert service.provider.calls==0


def test_elliptical_purchase_form_is_accepted_offline_through_as03(conversation):
    from pathlib import Path
    from uuid import UUID
    from tests.assistant_cases import retained_record,row_for
    state,record,service,headers,body,path=conversation
    purchase=retained_record('purchase',actor_id=record.actor_id);row=row_for(purchase)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    class Ellipsis(Valid):
        def generate(self,payload,profile,*,before_completion=None):
            result=super().generate(payload,profile,before_completion=before_completion)
            card=FactCard(**{k:v for k,v in payload['facts'][0].items() if k!='wording'})
            output=SemanticOutput(assertions=(proposal(card,f'Phương án được khuyến nghị là mua {card.display} {card.unit}.'),))
            return ChatProviderResult(output,result.diagnostics)
    provider=Ellipsis();service.provider=provider
    body={**body,'expected_evidence_version':row.record_digest,'question':'Còn nó cần mua bao nhiêu?',
          'ingredient_id':None,'history':[{'role':'user','content':str(UUID(int=200))+' cần mua bao nhiêu?'}]}
    path=f'/api/v1/procurement-plans/{purchase.run_id}/assistant/messages'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    result=response.json()['data']
    assert result['source']=='model' and result['ingredient_id']==str(UUID(int=200))
    assert '20 g' in result['answer'] and 'đề xuất' in result['answer']
    assert state[5].post(path,headers=headers,json=body).json()['data']==result and provider.calls==1
    target=Path('runtime/assistant-test/l31/offline-ellipsis-replay.json');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(dict(mode='OFFLINE_FAKE_PROVIDER',
        note='Regression for the wording form observed in live attempt10; new synthetic evidence IDs, not a new live completion.',
        request=body,response=result),ensure_ascii=False,indent=2),encoding='utf8')


def test_revocation_during_preflight_prevents_completion_request(conversation):
    from pydantic import SecretStr
    from tests.unit.test_conversational_chat import Transport
    from app.infrastructure.conversational_provider import OpenRouterConversationalProvider
    state,record,service,headers,body,path=conversation
    with Session(state[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id));mid=member.id;member.role='STAFF'
        for p in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=p))
        s.commit()
    class MetadataRevokes(Transport):
        def open(self,request,timeout):
            response=super().open(request,timeout)
            if request.data is None:
                with Session(state[1]) as s:s.delete(s.get(MembershipGrant,(mid,'budget.read')));s.commit()
            return response
    transport=MetadataRevokes(None)
    service.provider=OpenRouterConversationalProvider(SecretStr('synthetic'),opener=transport)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==403 and transport.completions==0
    with Session(state[1]) as s:assert s.scalar(select(ChatGenerationRow)).record_json['error_code']=='AUTHORITY_CHANGED'
