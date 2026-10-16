"""Opt-in real AS03 synthetic evaluation: all attempts and payloads retained."""
import hashlib,io,json,os,time
from decimal import Decimal
from pathlib import Path
from urllib.request import build_opener
from urllib.error import HTTPError
from uuid import uuid4
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import realistic_record,retained_record,row_for
from app.models import PlanningRun
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.chat_generation import ChatProfile
from app.infrastructure.conversational_provider import OpenRouterConversationalProvider
from app.infrastructure.import_suggestions import NoRedirect

pytestmark=pytest.mark.skipif(os.environ.get('SHELFCASH_CHAT_L31_LIVE')!='synthetic-30-usd-1.00',reason='Separate explicit paid L3.1 opt-in required')
ROOT=Path('runtime/assistant-test/conversational-l31-live')
BOUND=Decimal(36864)*Decimal('.0000003')+Decimal(1200)*Decimal('.0000025')
CASES={'budget':'Kế hoạch này tốn bao nhiêu?', 'proof':'Vì sao chọn phương án này?',
    'ingredient':'Sữa tươi cần mua bao nhiêu?', 'tradeoff':'Phương án đắt hơn được lợi gì?',
    'no_winner':'Không có winner, đang vướng điều kiện nào?', 'clarification':'Sữa cần mua bao nhiêu?',
    'followup':'Còn nó đang tồn bao nhiêu?'}


def fingerprint():
    paths=sorted([*Path('app').rglob('*.py'),*Path('tests/fixtures/decision_assistant').glob('*.json')])
    return hashlib.sha256(b''.join(str(p).encode()+p.read_bytes() for p in paths)).hexdigest()


class LedgerTransport:
    def __init__(self,root,case,version):
        self.root,self.case,self.version=root,case,version
        self.opener=build_opener(NoRedirect());self.attempts=[];self.preflights=[]

    def open(self,request,timeout):
        if self.root.resolve()==ROOT.resolve():
            raise AssertionError('L3.1 caller retired; use shared L3.2 ledger')
        if request.data is None:
            with self.opener.open(request,timeout=timeout) as response:raw=response.read(262145)
            self.preflights.append(json.loads(raw));return io.BytesIO(raw)
        body=json.loads(request.data)
        assert len(request.data)<=24000 and body['max_tokens']<=1200
        assert body['model']=='google/gemini-2.5-flash'
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert body['reasoning']=={'enabled':False}
        assert Decimal(str(body['provider']['max_price']['prompt']))<=Decimal('.3')
        assert Decimal(str(body['provider']['max_price']['completion']))<=Decimal('2.5')
        assert Decimal(str(body['provider']['max_price']['request']))==0
        assert BOUND*30<=Decimal('1.00')
        self.root.mkdir(parents=True,exist_ok=True)
        for n in range(1,31):
            path=self.root/f'attempt-{n}.json'
            try:
                with path.open('x',encoding='utf8') as out:
                    json.dump(dict(batch_id='L31-synthetic-30-usd-1.00',attempt=n,case=self.case,frozen_version=self.version,
                        reserved_usd=str(BOUND),request_body=body,prompt_hash=hashlib.sha256(request.data).hexdigest(),
                        preflight=self.preflights[-1],timestamp=time.time()),out,ensure_ascii=False,indent=2)
                break
            except FileExistsError:continue
        else:raise AssertionError('30 completion reservations exhausted; never reset ledger')
        self.attempts.append(n);started=time.monotonic();safe={'outcome':'TRANSPORT_UNKNOWN'}
        try:
            with self.opener.open(request,timeout=timeout) as response:raw=response.read(65537)
            assert len(raw)<=65536
            data=json.loads(raw);choice=(data.get('choices') or [{}])[0]
            safe=dict(model=data.get('model'),provider=data.get('provider'),usage=data.get('usage'),
                finish_reason=choice.get('finish_reason'),content=choice.get('message',{}).get('content'),
                refusal=bool(choice.get('message',{}).get('refusal')),response_hash=hashlib.sha256(raw).hexdigest())
            return io.BytesIO(raw)
        except HTTPError as error:
            safe=dict(outcome='HTTP_REJECTED',http_status=error.code)
            raise
        finally:
            safe.update(attempt=n,case=self.case,frozen_version=self.version,latency_ms=int((time.monotonic()-started)*1000))
            (self.root/f'raw-{n}.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


@pytest.mark.parametrize('case',CASES)
def test_l31_live_as03(assistant,case):
    state,base,summary,headers,body,path=assistant
    record=retained_record('infeasible',actor_id=base.actor_id) if case=='no_winner' else realistic_record(actor_id=base.actor_id)
    row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    from dotenv import dotenv_values
    values=dotenv_values(Path('.env'))
    model=values.get('CHAT_MODEL') or values.get('SUMMARY_MODEL')
    assert model=='google/gemini-2.5-flash'
    providers=tuple(json.loads(values.get('CHAT_PROVIDERS') or '[]'))
    profile=ChatProfile(enabled=True,model=model,providers=providers,input_bytes=24000,max_tokens=1200,
        completion_limit=2,deadline_seconds=60,max_request_cost_usd='0.10')
    version=fingerprint();transport=LedgerTransport(ROOT,case,version)
    provider=OpenRouterConversationalProvider(SecretStr(values['OPENROUTER_API_KEY']),opener=transport);values.clear()
    service=AssistantChat(summary.planning,profile,provider);state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    body={**body,'expected_evidence_version':row.record_digest,'question':CASES[case],'ingredient_id':None,'history':[]}
    if case=='followup':
        from app.application.contracts.assistant_chat import ChatContext
        from uuid import UUID
        body['context']=ChatContext(run_id=record.run_id,evidence_version=row.record_digest,ingredient_id=UUID(int=200),topic='purchase').model_dump(mode='json')
        body['history']=[{'role':'user','content':'Sữa tươi cần mua bao nhiêu?'}]
    started=time.monotonic();response=state[5].post(path,headers=headers,json=body)
    final=dict(batch_id='L31-synthetic-30-usd-1.00',case=case,frozen_version=version,as03_request=body,
        completion_attempts=transport.attempts,http_status=response.status_code,application_latency_ms=int((time.monotonic()-started)*1000))
    if response.status_code==200:
        result=response.json()['data'];final['final']=result
        count=len(transport.attempts)
        replay=state[5].post(path,headers=headers,json=body)
        assert replay.status_code==200 and replay.json()['data']==result
        final['replay_completions']=len(transport.attempts)-count
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/f'final-{case}-{version[:12]}-{uuid4().hex[:8]}.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    assert response.status_code==200,response.text
    assert final['replay_completions']==0
    if case=='clarification':assert result['kind']=='clarification' and len(result['clarification']['candidates'])==2 and not transport.attempts
    else:assert result['source']=='model',result['diagnostics']
