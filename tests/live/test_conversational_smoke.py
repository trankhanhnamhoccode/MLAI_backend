"""Explicit paid synthetic AS03 corpus; durable reservation before every POST."""
import hashlib,io,json,os,time
from decimal import Decimal
from pathlib import Path
from uuid import UUID,uuid4
from urllib.request import build_opener
from urllib.error import HTTPError
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import retained_record,row_for
from app.models import PlanningRun
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.assistant_chat import AssistantResponse
from app.application.contracts.chat_generation import ChatProfile
from app.infrastructure.conversational_provider import OpenRouterConversationalProvider
from app.infrastructure.import_suggestions import NoRedirect

pytestmark=pytest.mark.skipif(os.environ.get('SHELFCASH_CHAT_LIVE')!='synthetic-10-usd-0.10',reason='Explicit paid conversational smoke only')

CASES=[
    ('budget','purchase','Kế hoạch này tốn bao nhiêu?',None,[]),
    ('proof','purchase','Vì sao chọn phương án này?',None,[]),
    ('tradeoff','purchase','Phương án khác đắt hơn thì được lợi gì?',None,[]),
    ('ingredient','purchase','Nguyên liệu này cần mua bao nhiêu?',str(UUID(int=200)),[]),
    ('no_winner','infeasible','Nếu không có winner, đang vướng điều kiện nào?',None,[]),
    ('followup','purchase','Còn nó cần mua bao nhiêu?',None,[{'role':'user','content':'Nguyên liệu '+str(UUID(int=200))+' cần mua bao nhiêu?'}]),
]


class BudgetTransport:
    def __init__(self,root,case_id,model):
        self.root,self.case_id,self.model=root,case_id,model;self.calls=0;self.raw=None;self.attempt=None
        self.opener=build_opener(NoRedirect())

    def open(self,request,timeout):
        if request.data is None:return self.opener.open(request,timeout=timeout)
        body=json.loads(request.data)
        assert body['model']==self.model=='google/gemini-2.5-flash'
        assert len(request.data)<=12000 and body['max_tokens']<=768
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert Decimal(str(body['provider']['max_price']['prompt']))<=Decimal('0.3')
        assert Decimal(str(body['provider']['max_price']['completion']))<=Decimal('2.5')
        assert Decimal(str(body['provider']['max_price']['request']))==0
        assert body['reasoning']=={'enabled':False}
        assert set(body)<={'model','temperature','max_tokens','reasoning','provider','messages','response_format'}
        # UTF-8 text-only request<=12KiB; 32768 conservatively includes tokenizer/
        # message/schema envelope overhead. Reserve worst case, not average cost.
        large=Decimal(32768)*Decimal('0.0000003')+Decimal(768)*Decimal('0.0000025')
        small=Decimal(8192)*Decimal('0.0000003')+Decimal(128)*Decimal('0.0000025')
        assert large*8+small*2<=Decimal('0.10')
        self.root.mkdir(parents=True,exist_ok=True)
        for attempt in range(1,11):
            if (self.root/f'attempt-{attempt}.json').exists():continue
            bound=large
            if attempt>=9:
                assert len(request.data)<=6144 and body['max_tokens']<=128,'Last two attempts require smaller input/output caps'
                bound=small
            try:
                with (self.root/f'attempt-{attempt}.json').open('x',encoding='utf8') as out:
                    json.dump(dict(case=self.case_id,reserved_usd=str(bound),model=self.model,
                        prompt_hash=hashlib.sha256(request.data).hexdigest(),timestamp=time.time()),out)
                self.attempt=attempt;break
            except FileExistsError:continue
        else:raise AssertionError('Ten reservations exhaust this batch; no more completions')
        self.calls+=1;started=time.monotonic()
        try:
            with self.opener.open(request,timeout=timeout) as response:raw=response.read(65537)
            assert len(raw)<=65536
            data=json.loads(raw)
            choice=(data.get('choices') or [{}])[0]
            # Never retain Authorization, sessions, key, hidden reasoning or headers.
            self.raw=dict(model=data.get('model'),provider=data.get('provider'),usage=data.get('usage'),
                finish_reason=choice.get('finish_reason'),content=choice.get('message',{}).get('content'),
                refusal=bool(choice.get('message',{}).get('refusal')),
                latency_ms=int((time.monotonic()-started)*1000),response_hash=hashlib.sha256(raw).hexdigest())
            return io.BytesIO(raw)
        except HTTPError as error:
            data=json.loads(error.read(8192))
            message=str(data.get('error',{}).get('message',''))
            secret=(request.get_header('Authorization') or '').removeprefix('Bearer ')
            if secret:message=message.replace(secret,'[REDACTED]')
            self.raw=dict(http_status=error.code,error_code=data.get('error',{}).get('code'),
                message=message[:1000],latency_ms=int((time.monotonic()-started)*1000),outcome='HTTP_REJECTED')
            raise
        finally:
            safe=dict(attempt=self.attempt,case=self.case_id,raw=self.raw or {'outcome':'TRANSPORT_UNKNOWN'},reserved_usd=str(bound))
            safe['request_body']=body
            (self.root/f'raw-{self.attempt}.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf8')


@pytest.mark.parametrize('case_id,kind,question,ingredient,history',CASES,ids=[c[0] for c in CASES])
def test_conversational_live_as03(assistant,case_id,kind,question,ingredient,history):
    state,record,summary,headers,body,path=assistant
    # Only this test's synthetic retained graphs, never a configured application DB.
    if kind!='stock':
        record=retained_record(kind,actor_id=record.actor_id)
        row=row_for(record)
        with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
        body={**body,'expected_evidence_version':row.record_digest}
    from dotenv import dotenv_values
    values=dotenv_values(Path(__file__).resolve().parents[2]/'.env')
    model=values.get('CHAT_MODEL') or values.get('SUMMARY_MODEL')
    assert model=='google/gemini-2.5-flash'
    small=os.environ.get('SHELFCASH_CHAT_SMALL')=='1'
    profile=ChatProfile(enabled=True,model=model,providers=tuple(json.loads(values.get('CHAT_PROVIDERS') or '[]')),
        max_tokens=128 if small else 768,input_bytes=6144 if small else 12000,max_prompt_price='0.3',max_completion_price='2.5')
    root=Path('runtime/assistant-test/conversational-live')
    transport=BudgetTransport(root,case_id,model)
    provider=OpenRouterConversationalProvider(SecretStr(values['OPENROUTER_API_KEY']),opener=transport)
    values.clear()
    service=AssistantChat(summary.planning,profile,provider);state[5].app.state.assistant_chat=service
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    body={**body,'question':question,'ingredient_id':ingredient,'history':history}
    if os.environ.get('SHELFCASH_CHAT_VARIANT')=='natural_followup':
        body={**body,'question':'Chi phí mua, phí phải trả và ngân sách đã lưu là bao nhiêu?' if case_id=='budget' else 'Vì sao chọn phương án này trong các phương án đã đánh giá?'}
    started=time.monotonic();response=state[5].post(path,headers=headers,json=body)
    safe=dict(case=case_id,attempt=transport.attempt,http_status=response.status_code,
        raw=transport.raw,application_latency_ms=int((time.monotonic()-started)*1000))
    if response.status_code==200:
        result=response.json()['data'];AssistantResponse.model_validate(result)
        safe['final']=result
        safe['coverage_review']=dict(required_scope=case_id,accepted=result['source']=='model',
            reference_count=len(result['references']),claim_count=len(result['claims']),reason=result['diagnostics']['reason'])
        replay=state[5].post(path,headers=headers,json=body)
        assert replay.status_code==200 and replay.json()['data']==result
        assert state[5].get(path).status_code==405
        assert transport.calls==1
        safe['replay_completions']=0
    (root/f'final-{transport.attempt or case_id}.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf8')
    assert response.status_code==200,response.text
    # A fallback is reported honestly as fallback, not hidden by HTTP200.
    assert result['kind']=='answer' and result['references']
