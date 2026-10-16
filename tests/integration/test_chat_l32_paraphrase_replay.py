"""V6 real AS03/owned PG, fake provider rebinding two observed V5 wording forms."""
import json
import hashlib
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_conversational_chat import conversation
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import realistic_record,retained_record,row_for
from app.models import PlanningRun,AssistantMessage
from app.application.contracts.chat_generation import FactCard,SemanticOutput,ChatProfile
from app.application.contracts.assistant_chat import ChatDiagnostics
from app.application.chat_assertions import proposal
from app.infrastructure.conversational_provider import ChatProviderResult


@pytest.mark.parametrize('kind',['why','no_winner'])
def test_two_live_wording_forms_accepted_offline_with_new_scoped_refs_and_replay(conversation,kind):
    state,base,service,headers,body,path=conversation
    record=realistic_record(actor_id=base.actor_id) if kind=='why' else retained_record('infeasible',actor_id=base.actor_id)
    row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    class Rebound:
        calls=0
        def generate(self,payload,profile,*,before_completion):
            before_completion();assert service.engine.pool.checkedout()==0;self.calls+=1;assertions=[]
            for data in payload['facts']:
                if data['fact_id'] not in payload['required']:continue
                c=FactCard(**{k:v for k,v in data.items() if k!='wording'})
                a=proposal(c,data['wording']+'.')
                if c.kind=='detail_unknown':a=a.model_copy(update={'text':a.text.replace('Evidence đang dùng chưa có','Không có')})
                if c.kind=='rejection':a=a.model_copy(update={'text':a.text.replace(': ',' ',1)})
                assertions.append(a)
            return ChatProviderResult(SemanticOutput(assertions=tuple(assertions)),ChatDiagnostics(reason='NONE',disposition='ACCEPTED',model=profile.model,
                resolved_model=profile.model,provider='OFFLINE_FAKE',attempts=1,prompt_version='conversational_chat_prompt/5',validator_version='chat_assertions/6'))
    fake=Rebound();service.provider=fake
    body={**body,'expected_evidence_version':row.record_digest,'question':'Vì sao Sữa tươi cần mua?' if kind=='why' else 'Không có winner, vướng gì?'}
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    headers={**headers,'Idempotency-Key':str(uuid4())}
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    final=response.json()['data'];assert final['source']=='model' and final['diagnostics']['disposition']=='ACCEPTED'
    with Session(state[1]) as fresh:
        stored=fresh.scalar(select(AssistantMessage))
        assert stored.record_json['response']==final
    service.profile=ChatProfile(enabled=False)
    assert state[5].post(path,headers=headers,json=body).json()['data']==final
    assert state[5].get(path).status_code==405 and fake.calls==1
    out=Path(f'runtime/assistant-test/l32/offline-v6-paraphrase-replay-{kind}.json')
    source_paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json')])
    source_hash=hashlib.sha256(b''.join(str(p).encode()+p.read_bytes() for p in source_paths)).hexdigest()
    out.write_text(json.dumps(dict(mode='OFFLINE_FAKE_PROVIDER_REBOUND_WORDING',
        application_source_fingerprint=source_hash,
        note='V5 observed raw22/raw27 wording form rebound to new synthetic scoped fact IDs; not a rewritten original live response, not another paid call.',
        request=body,final=final,fresh_persistence_checked=True,replay_completions=0,get_status=405),ensure_ascii=False,indent=2),encoding='utf8')
