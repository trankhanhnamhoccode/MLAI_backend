"""Actual owned AS03/persistence, synthetic fake wording and old V6 replay."""
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import realistic_record,row_for
from tests.live.test_chat_v6_acceptance import audit_authority
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.chat_generation import ChatProfile,SemanticOutput,FactCard
from app.application.contracts.assistant_chat import ChatDiagnostics
from app.application.chat_assertions import proposal
from app.infrastructure.conversational_provider import ChatProviderResult
from app.models import PlanningRun,AssistantMessage,ChatGenerationRow


@pytest.mark.parametrize('enabled',[True,False])
def test_l4_new_presentation_fresh_receipt_old_replay_and_summary_independent(assistant,enabled):
    state,base,summary,headers,body,path=assistant
    record=realistic_record(actor_id=base.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    class Fake:
        calls=0;attempts=[]
        def generate(self,payload,profile,*,before_completion):
            before_completion();assert state[1].pool.checkedout()==0;self.calls+=1
            out=SemanticOutput(assertions=tuple(proposal(FactCard(**{k:v for k,v in f.items() if k!='wording'}),f['wording']+'.') for f in payload['facts'] if f['fact_id'] in payload['required']))
            v=7 if payload['task']=='conversational_chat/6' else 6
            return ChatProviderResult(out,ChatDiagnostics(reason='NONE',disposition='ACCEPTED',model=profile.model,resolved_model=profile.model,provider='OFFLINE_FAKE',attempts=1,
                prompt_version='conversational_chat_prompt/'+str(6 if v==7 else 5),validator_version='chat_assertions/'+str(v)))
    fake=Fake();service=AssistantChat(summary.planning,ChatProfile(enabled=True,model='synthetic'),fake)
    state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    body={**body,'expected_evidence_version':row.record_digest,'question':'Vì sao chọn phương án này?','ingredient_id':None,'history':[]}
    old=state[5].post(path,headers=headers,json=body);assert old.status_code==200,old.text
    old_data=old.json()['data'];calls=fake.calls
    service.presentation_version=7;service.profile=service.profile.model_copy(update={'enabled':enabled})
    assert state[5].post(path,headers=headers,json=body).json()['data']==old_data and fake.calls==calls
    key={**headers,'Idempotency-Key':str(uuid4())}
    new=state[5].post(path,headers=key,json=body);assert new.status_code==200,new.text
    data=new.json()['data'];assert len(data['claims'])<len(old_data['claims'])
    with Session(state[1]) as fresh:
        receipts=list(fresh.scalars(select(AssistantMessage)))
        assert any(r.record_json['response']==data for r in receipts)
        if enabled:assert any(r.record_json['selection_version']=='chat_evidence/7' for r in fresh.scalars(select(ChatGenerationRow)))
    before=fake.calls;service.presentation_version=6;service.profile=ChatProfile(enabled=False)
    assert state[5].post(path,headers=key,json=body).json()['data']==data and fake.calls==before
    checks=audit_authority(state,record,path,key,body,fake)
    assert checks['additional_completions']==0 and fake.calls==before
    summary_path=path.rsplit('/',1)[0]+'/summary';summary_body={k:v for k,v in body.items() if k not in ('question','ingredient_id','history')}
    res=state[5].post(summary_path,headers={**headers,'Idempotency-Key':str(uuid4())},json=summary_body)
    assert res.status_code==200 and res.json()['data']['result']['source']=='deterministic_fallback'


def test_l4_model_off_clarification_is_consistent_and_retained(assistant):
    state,base,summary,headers,body,path=assistant
    record=realistic_record(actor_id=base.actor_id);row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    service=AssistantChat(summary.planning,presentation_version=7);state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    req={**body,'expected_evidence_version':row.record_digest,'question':'Sữa cần mua bao nhiêu?','ingredient_id':None,'history':[]}
    res=state[5].post(path,headers=headers,json=req);assert res.status_code==200,res.text
    data=res.json()['data'];assert data['kind']=='clarification' and data['diagnostics']['disposition']=='CLARIFICATION'
    service.presentation_version=6
    assert state[5].post(path,headers=headers,json=req).json()['data']==data
