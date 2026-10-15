"""New assertion lifecycle on the real AS03 and owned isolated PostgreSQL."""
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from tests.integration.test_conversational_chat import conversation,Valid
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import realistic_record,row_for
from app.models import PlanningRun
from app.application.contracts.chat_generation import ChatProfile,SemanticOutput,FactCard
from app.application.chat_assertions import proposal
from app.infrastructure.conversational_provider import ChatProviderResult


def test_real_as03_milk_clarification_then_stock_switch_without_model_on_ambiguity(conversation):
    state,record,service,headers,body,path=conversation
    record=realistic_record(actor_id=record.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    body={**body,'expected_evidence_version':row.record_digest,'question':'Sữa cần mua bao nhiêu?'}
    service.profile=ChatProfile(enabled=False)
    results=[]
    for question in ('Sữa cần mua bao nhiêu?','Sữa tươi','Còn nó đang tồn bao nhiêu?','Đổi sang sữa đặc thì sao?'):
        request={**body,'question':question}
        if results:request['context']=results[-1]['context']
        result=state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=request)
        assert result.status_code==200,result.text
        results.append(result.json()['data'])
    assert results[0]['kind']=='clarification' and len(results[0]['clarification']['candidates'])==2
    assert results[1]['kind']=='answer' and '20 g' in results[1]['answer']
    assert 'đã chụp' in results[2]['answer'] and 'đã chụp' in results[3]['answer']
    assert results[2]['ingredient_id']!=results[3]['ingredient_id']
    assert service.provider.calls==0
    product_question={**body,'question':'Món SYNTHETIC 0 và SYNTHETIC 1 đáp ứng bao nhiêu?'}
    result=state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=product_question)
    assert result.status_code==200,result.text
    clarified=result.json()['data'];assert len(clarified['clarification']['product_candidates'])==2
    selection={**product_question,'question':'SYNTHETIC 0','context':clarified['context']}
    result=state[5].post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=selection)
    assert result.status_code==200,result.text
    selected=result.json()['data'];assert selected['context']['product_id'].endswith('0064') and selected['kind']=='answer'


def test_development_tradeoff_wording_replayed_offline_through_as03(conversation):
    from pathlib import Path
    import json
    state,record,service,headers,body,path=conversation
    record=realistic_record(actor_id=record.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    class RecordedForm(Valid):
        def generate(self,payload,profile,*,before_completion=None):
            if before_completion:before_completion()
            self.calls+=1;rows=[]
            for data in payload['facts']:
                c=FactCard(**{k:v for k,v in data.items() if k!='wording'})
                text=f'Chênh lệch tổng chi là {c.display} {c.unit}.' if c.kind=='pair_cost' else f'Lượng phục vụ món "{c.label}" trên đường "{c.path}" tăng {c.display} {c.unit}.'
                rows.append(proposal(c,text))
            from app.application.contracts.assistant_chat import ChatDiagnostics
            return ChatProviderResult(SemanticOutput(assertions=tuple(rows)),ChatDiagnostics(reason='NONE',model=profile.model,
                resolved_model=profile.model,provider='OFFLINE_FAKE',attempts=1,disposition='ACCEPTED',
                prompt_version='conversational_chat_prompt/3',validator_version='chat_assertions/3'))
    provider=RecordedForm();service.provider=provider
    body={**body,'expected_evidence_version':row.record_digest,'question':'Phương án đắt hơn được lợi gì?'}
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    result=response.json()['data'];assert result['source']=='model' and len(result['claims'])==8
    assert 'balanced, protected trừ lean' in result['answer'] and 'mô phỏng' in result['answer']
    assert state[5].post(path,headers=headers,json=body).json()['data']==result and provider.calls==1
    output=Path('runtime/assistant-test/l31/offline-pair-replay.json');output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(dict(mode='OFFLINE_FAKE_PROVIDER',note='Wording form observed in L3.1 development attempt4; rebound to new synthetic scoped fact IDs, not another live call or rewritten original final.',request=body,final=result,replay_completions=0),ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def test_proof_eligibility_and_requirement_coverage_through_as03(conversation):
    state,record,service,headers,body,path=conversation
    record=realistic_record(actor_id=record.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    class Worded(Valid):
        def generate(self,payload,profile,*,before_completion=None):
            if before_completion:before_completion()
            assert service.engine.pool.checkedout()==0
            self.calls+=1
            cards=[FactCard(**{k:v for k,v in d.items() if k!='wording'}) for d in payload['facts']]
            out=SemanticOutput(assertions=tuple(proposal(c,d['wording']+'.') for c,d in zip(cards,payload['facts'])))
            from app.application.contracts.assistant_chat import ChatDiagnostics
            return ChatProviderResult(out,ChatDiagnostics(reason='NONE',model=profile.model,resolved_model=profile.model,
                provider='OFFLINE_FAKE',attempts=1,disposition='ACCEPTED',prompt_version='conversational_chat_prompt/3',validator_version='chat_assertions/3'))
    service.provider=Worded();body={**body,'expected_evidence_version':row.record_digest,'question':'Vì sao chọn phương án này?'}
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    final=response.json()['data'];assert final['source']=='model' and len(final['claims'])==7
    assert '95%' in final['answer'] and 'PASS; thiếu 0 cup' in final['answer']
    assert state[5].post(path,headers=headers,json=body).json()['data']==final and service.provider.calls==1


def test_old_l31_pair_fallback_keeps_original_seven_claims_on_replay(conversation):
    from app.application.use_cases.conversational_chat import ConversationalChat
    from app.application.contracts.chat_generation import ChatGeneration
    from app.application.contracts.assistant_chat import ChatRequest,ChatDiagnostics
    from app.application.planning_serialization import digest
    from app.infrastructure.auth_crypto import digest as key_digest
    from app.infrastructure.planning_process import current_process
    from app.repositories.chat_generation import ChatGenerationRepository
    from datetime import datetime,timezone
    state,record,service,headers,body,path=conversation
    record=realistic_record(actor_id=record.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
    body={**body,'expected_evidence_version':row.record_digest,'question':'Phương án đắt hơn được lợi gì?'}
    request=ChatRequest(**body);use=ConversationalChat(service)
    evidence,old_plan=use.prepare(token,record.run_id,request,'chat_assertions/3','chat_evidence/2')
    _,new_plan=use.prepare(token,record.run_id,request)
    assert len(old_plan.fallback.claims)==7 and len(new_plan.fallback.claims)==8
    diag=ChatDiagnostics(reason='PROVIDER_UNAVAILABLE',model=service.profile.model,attempts=1,
        prompt_version='conversational_chat_prompt/3',validator_version='chat_assertions/3')
    answer=old_plan.fallback.model_copy(update={'diagnostics':diag})
    claim=ChatGeneration(generation_id=uuid4(),actor_id=record.actor_id,store_id=record.store_id,run_id=record.run_id,
        key_digest=key_digest(headers['Idempotency-Key']),request_digest=digest('assistant-message-request',request),request=request,
        profile=service.profile,evidence_digest=digest('chat-evidence',evidence),plan_digest=digest('chat-plan',old_plan),
        process=current_process(),claim_token=uuid4(),created_at=datetime.now(timezone.utc),prompt_version='conversational_chat_prompt/3',
        validator_version='chat_assertions/3',schema_version='conversational_assertions/2')
    with Session(state[1]) as s:ChatGenerationRepository(s).accept(claim);s.commit()
    use.publish(claim,answer,token=token,csrf=headers['X-CSRF-Token'])
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    assert response.json()['data']==answer.model_dump(mode='json') and service.provider.calls==0


@pytest.mark.parametrize('mode,expected,calls',[('repair','REPAIRED',1),('trim','TRIMMED',1),('regenerate','REGENERATED',2),('fail','FALLBACK',2),('unknown','FALLBACK',1)])
def test_bounded_repair_regeneration_and_immutable_replay(conversation,mode,expected,calls):
    state,record,service,headers,body,path=conversation
    service.profile=ChatProfile(enabled=True,model='synthetic-gemini',completion_limit=2)
    class Sequence(Valid):
        profiles=[]
        def generate(self,payload,profile,*,before_completion=None):
            self.profiles.append(profile)
            assert service.engine.pool.checkedout()==0
            if mode=='unknown':self.calls+=1;raise TimeoutError()
            result=super().generate(payload,profile,before_completion=before_completion)
            rows=result.output.assertions
            if mode=='repair':rows=(rows[0].model_copy(update={'text':'Tổng chi là 99 VND.','value':'99'}),*rows[1:])
            elif mode=='trim':rows=(rows[0],rows[1].model_copy(update={'text':'Chi phí mua là 99 kg.'}),*rows[2:])
            elif mode=='fail' or mode=='regenerate' and self.calls==1:
                rows=(rows[0].model_copy(update={'text':'Tổng chi là 99 kg vì nhu cầu tăng.'}),*rows[1:])
            if self.calls==2:
                assert payload['feedback']['failures']
                assert '99 kg' not in str(payload['facts'])
            return ChatProviderResult(result.output.model_copy(update={'assertions':rows}),result.diagnostics)
    provider=Sequence();service.provider=provider
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    result=response.json()['data'];assert result['diagnostics']['disposition']==expected
    assert result['diagnostics']['attempts']==calls
    if mode!='unknown':assert result['diagnostics']['failure_trace']
    assert state[5].post(path,headers=headers,json=body).json()['data']==result
    assert provider.calls==calls
    if calls==2:assert provider.profiles[1].deadline_seconds<provider.profiles[0].deadline_seconds


def test_cost_reservation_blocks_regeneration_and_keeps_unknown_cost(conversation):
    state,record,service,headers,body,path=conversation
    # One call fits .006; a second conservative reservation cannot fit.
    service.profile=ChatProfile(enabled=True,model='synthetic-gemini',completion_limit=2,max_request_cost_usd='0.006')
    class Wrong(Valid):
        def generate(self,*args,**kwargs):
            result=super().generate(*args,**kwargs)
            rows=result.output.assertions
            return ChatProviderResult(result.output.model_copy(update={'assertions':(rows[0].model_copy(update={'text':'Tổng chi là 9 kg.'}),*rows[1:])}),result.diagnostics)
    service.provider=Wrong()
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    d=response.json()['data']['diagnostics']
    assert service.provider.calls==1 and d['cost_usd'] is None
    assert 'SHARED_DEADLINE_OR_COST_BOUND' in d['failure_trace']


@pytest.mark.parametrize('version',['chat_assertion_grammar/2','chat_assertions/3'])
def test_legacy_generation_remains_readable_with_original_pinned_plan(conversation,version):
    from app.application.use_cases.conversational_chat import ConversationalChat
    from app.application.contracts.chat_generation import ChatGeneration,ConversationalOutput,ModelStatement
    from app.application.contracts.assistant_chat import ChatDiagnostics,ChatRequest
    from app.application.chat_grounding import canonical_clause,model_answer
    from app.application.planning_serialization import digest
    from app.infrastructure.auth_crypto import digest as key_digest
    from app.infrastructure.planning_process import current_process
    from app.repositories.chat_generation import ChatGenerationRepository
    from datetime import datetime,timezone
    state,record,service,headers,body,path=conversation
    token=state[5].cookies.get('__Host-shelfcash_session') or state[5].cookies.get('shelfcash_dev_session')
    use=ConversationalChat(service);request=ChatRequest(**body)
    if version=='chat_assertions/3':request=request.model_copy(update={'question':'Vì sao chọn phương án này?'})
    evidence,plan=use.prepare(token,record.run_id,request,version,'chat_evidence/2')
    prompt='conversational_chat_prompt/3' if version=='chat_assertions/3' else 'conversational_chat_prompt/2'
    diag=ChatDiagnostics(reason='NONE',disposition='ACCEPTED',attempts=1,model=service.profile.model,resolved_model=service.profile.model,provider='Synthetic',prompt_version=prompt,validator_version=version)
    if version=='chat_assertions/3':
        from app.application.chat_assertions import semantic_answer
        output=SemanticOutput(assertions=tuple(proposal(c) for c in plan.facts))
        answer=semantic_answer(output,plan,diag)
        assert {c.kind for c in plan.facts}=={'winner','selector','proof_boundary'} # completed stock fixture
    else:
        output=ConversationalOutput(statements=tuple(ModelStatement(text=canonical_clause(c)+'.',fact_ids=(c.fact_id,)) for c in plan.facts))
        answer=model_answer(output,plan,diag)
    claimed=ChatGeneration(generation_id=uuid4(),actor_id=record.actor_id,store_id=record.store_id,run_id=record.run_id,
        key_digest=key_digest(headers['Idempotency-Key']),request_digest=digest('assistant-message-request',request),request=request,profile=service.profile,
        evidence_digest=digest('chat-evidence',evidence),plan_digest=digest('chat-plan',plan),process=current_process(),claim_token=uuid4(),created_at=datetime.now(timezone.utc),
        prompt_version=prompt,validator_version=version,schema_version='conversational_assertions/2' if version=='chat_assertions/3' else 'conversational_output/1')
    with Session(state[1]) as s:ChatGenerationRepository(s).accept(claimed);s.commit()
    use.publish(claimed,answer,output,token=token,csrf=headers['X-CSRF-Token'])
    response=state[5].post(path,headers=headers,json=request.model_dump(mode='json'))
    assert response.status_code==200,response.text
    assert response.json()['data']==answer.model_dump(mode='json') and service.provider.calls==0
