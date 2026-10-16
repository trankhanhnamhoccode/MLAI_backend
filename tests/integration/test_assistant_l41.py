import json
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_l41_cases import create_milk_run
from tests.assistant_cases import row_for
from tests.live.test_chat_v6_acceptance import audit_authority
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.chat_generation import ChatProfile,FactCard,SemanticOutput
from app.application.contracts.assistant_chat import ChatDiagnostics
from app.application.chat_assertions import proposal
from app.infrastructure.conversational_provider import ChatProviderResult
from app.models import AssistantMessage


@pytest.mark.parametrize('kind',['mixed','failed'])
def test_engine_retained_focused_variants_are_consistent(assistant,kind):
    state,base,summary,headers,body,path=assistant
    record=create_milk_run(state[1],base.actor_id,kind)
    from app.application.planning_public_projection import project_run
    from app.application.decision_evidence_projection import project_evidence
    view=project_run(record,response_version=row_for(record).record_digest)
    evidence=project_evidence(record,view,include_comparisons=True)
    if kind=='mixed':
        assert evidence.overview.comparisons
        assert any(len({p.fulfilled.decimal_view for p in pair.products if p.product_id==product})>1
            for pair in evidence.overview.comparisons for product in {p.product_id for p in pair.products})
    else:assert evidence.overview.status=='failed' and not evidence.overview.recommendation_available
    service=AssistantChat(summary.planning,presentation_version=8);state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    req={**body,'expected_evidence_version':row_for(record).record_digest,'ingredient_id':None,'history':[],
        'question':'So sánh hai phương án?' if kind=='mixed' else 'Run lỗi còn thông tin gì?'}
    response=state[5].post(path,headers=headers,json=req);assert response.status_code==200,response.text
    final=response.json()['data'];assert final['kind']=='answer'
    assert state[5].post(path,headers=headers,json=req).json()['data']==final
    with Session(state[1]) as fresh:
        assert any(r.record_json['response']==final for r in fresh.scalars(select(AssistantMessage)))
    if kind=='mixed':assert 'mô phỏng' in final['answer'].lower()
    else:assert 'lỗi' in final['answer'].lower() and 'được khuyến nghị' not in final['answer']
    root=Path('runtime/assistant-test/l41');root.mkdir(parents=True,exist_ok=True)
    (root/f'offline-retained-{kind}-{record.run_id}.json').write_text(json.dumps(dict(mode='VALIDATED_ENGINE_AND_PERSISTENCE_NO_PROVIDER',
        record=record.model_dump(mode='json'),aggregate_sha256=row_for(record).record_digest,overview=evidence.overview.model_dump(mode='json'),
        request=req,final=final,fresh_persisted_equal=True,replay_equal=True),ensure_ascii=False,indent=2),encoding='utf8')


def test_valid_engine_retained_20_35_four_turn_http_and_old_generations(assistant):
    state,base,summary,headers,body,path=assistant
    record=create_milk_run(state[1],base.actor_id);row=row_for(record)
    root=Path('runtime/assistant-test/l41');root.mkdir(parents=True,exist_ok=True)
    class Fake:
        calls=0;attempts=[]
        def generate(self,payload,profile,*,before_completion):
            before_completion();self.calls+=1;self.attempts.append(self.calls)
            v=int(payload['task'].split('/')[-1])+1
            out=SemanticOutput(assertions=tuple(proposal(FactCard(**{k:v for k,v in f.items() if k!='wording'}),f['wording']+'.') for f in payload['facts'] if f['fact_id'] in payload['required']))
            return ChatProviderResult(out,ChatDiagnostics(reason='NONE',disposition='ACCEPTED',attempts=1,model=profile.model,resolved_model=profile.model,provider='OFFLINE_FAKE',
                prompt_version=f'conversational_chat_prompt/{v-1}',validator_version=f'chat_assertions/{v}'))
    fake=Fake();service=AssistantChat(summary.planning,ChatProfile(enabled=True,model='synthetic'),fake,presentation_version=8)
    state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    template={**body,'expected_evidence_version':row.record_digest,'ingredient_id':None,'history':[]}
    # Create and retain old generations against this SAME validated aggregate.
    originals=[]
    for version in (6,7):
        service.presentation_version=version;key={**headers,'Idempotency-Key':str(uuid4())}
        req={**template,'question':'Vì sao chọn phương án này?'}
        res=state[5].post(path,headers=key,json=req);assert res.status_code==200,res.text
        originals.append((key,req,res.json()['data']))
    service.presentation_version=8;context=None;turns=[]
    for n,q in enumerate(('Sữa cần mua bao nhiêu?','Sữa tươi','Vì sao lượng đó?','Còn sữa đặc?'),1):
        req={**template,'question':q}
        if context:req['context']=context
        key={**headers,'Idempotency-Key':str(uuid4())};res=state[5].post(path,headers=key,json=req);assert res.status_code==200,res.text
        data=res.json()['data'];context=data['context'];before=fake.calls
        assert state[5].post(path,headers=key,json=req).json()['data']==data and fake.calls==before
        with Session(state[1]) as fresh:
            assert any(r.record_json['response']==data for r in fresh.scalars(select(AssistantMessage)))
        checks=audit_authority(state,record,path,key,req,fake);assert fake.calls==before
        turns.append(dict(turn=n,question=q,final=data,fresh_persisted_equal=True,replay_calls=0,authority=checks))
    assert turns[0]['final']['kind']=='clarification' and len(turns[0]['final']['clarification']['candidates'])==2
    assert '20 g' in turns[1]['final']['answer'] and '35 g' in turns[3]['final']['answer']
    assert turns[1]['final']['ingredient_id']==turns[2]['final']['ingredient_id']!=turns[3]['final']['ingredient_id']
    assert turns[2]['final']['context']['topic']==turns[3]['final']['context']['topic']=='purchase_rationale'
    assert set(turns[1]['final']['claims'][0]['evidence_ids']).isdisjoint(turns[3]['final']['claims'][0]['evidence_ids'])
    for key,req,old in originals:
        before=fake.calls;assert state[5].post(path,headers=key,json=req).json()['data']==old and fake.calls==before
    (root/f'offline-retained-20-35-http-{record.run_id}.json').write_text(json.dumps(dict(mode='REAL_HTTP_PERSISTENCE_FAKE_WORDING_NOT_LIVE',
        factory='PlanningRunUseCases accept/claim/retain/finalize with capture/exact engine; pack17.5g input generates35g, no result patch',
        run_id=str(record.run_id),aggregate_sha256=row.record_digest,record=record.model_dump(mode='json'),turns=turns,old6_and7_replay_equal=True),ensure_ascii=False,indent=2),encoding='utf8')
