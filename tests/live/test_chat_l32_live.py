"""Synthetic real AS03 only, separate opt-in and shared write-ahead ledger."""
import hashlib,io,json,os,time
from pathlib import Path
from decimal import Decimal
from urllib.request import build_opener
from urllib.error import HTTPError
from uuid import uuid4
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.assistant_cases import realistic_record,retained_record,row_for
from tests.live.test_chat_l31_live import fingerprint
from scripts.conversational_shared_ledger import reserve,reservations,BOUND
from app.infrastructure.import_suggestions import NoRedirect
from app.infrastructure.conversational_provider import OpenRouterConversationalProvider
from app.application.use_cases.assistant_chat import AssistantChat
from app.application.contracts.chat_generation import ChatProfile
from app.models import PlanningRun
from app.infrastructure.auth_crypto import digest as key_digest

pytestmark=pytest.mark.skipif(os.environ.get('SHELFCASH_CHAT_L32_LIVE')!='shared-l31-l32-30-usd-1.00',reason='Paid L3.2 opt-in required')
BASE=Path('runtime/assistant-test');ROOT=BASE/'conversational-l32-live'
MAX_ATTEMPTS=30
CASES={'budget':'Kế hoạch này tốn bao nhiêu?', 'quantity':'Sữa tươi cần mua bao nhiêu?',
    'why':'Vì sao nhập Sữa tươi lượng đó?', 'why_missing':'Vì sao cần mua nguyên liệu này?',
    'proof':'Vì sao chọn phương án này?','comparison':'Phương án đắt hơn được lợi gì?',
    'no_winner':'Không có winner, đang vướng điều kiện nào?', 'conversation':'Sữa cần mua bao nhiêu?'}


class Transport:
    def __init__(self,case,version):
        self.case=case;self.version=version;self.opener=build_opener(NoRedirect());self.preflight=None;self.attempts=[];self.rate_limited=False

    def open(self,request,timeout):
        assert fingerprint()==self.version,'Source changed after freeze'
        if self.rate_limited:raise AssertionError('HTTP429 stops batch; no retry')
        if request.data is None:
            try:
                with self.opener.open(request,timeout=timeout) as response:raw=response.read(262145)
            except HTTPError as error:
                self.rate_limited=error.code==429
                if self.rate_limited:
                    ROOT.mkdir(parents=True,exist_ok=True)
                    (ROOT/f'preflight-429-{uuid4().hex[:8]}.json').write_text(json.dumps(dict(case=self.case,http_status=429,
                        frozen_version=self.version,stage='unpaid_preflight',completion_attempts=0)),encoding='utf8')
                raise
            assert len(raw)<=262144
            self.preflight=json.loads(raw)
            return io.BytesIO(raw)
        body=json.loads(request.data)
        assert len(request.data)<=24000 and body['max_tokens']<=1200
        assert body['model']==self.model
        route=body['provider'];assert route['allow_fallbacks'] is False and route['require_parameters'] is True
        assert body['reasoning']=={'enabled':False}
        assert Decimal(route['max_price']['prompt'])<=Decimal('.3') and Decimal(route['max_price']['completion'])<=Decimal('2.5')
        assert Decimal(route['max_price']['request'])==0
        # Read both ledgers immediately before every completion, including regen.
        n=reserve(BASE,dict(case=self.case,frozen_version=self.version,request_body=body,
            prompt_hash=hashlib.sha256(request.data).hexdigest(),preflight=self.preflight,timestamp=time.time()))
        self.attempts.append(n);started=time.monotonic();safe={'outcome':'TRANSPORT_UNKNOWN'}
        try:
            with self.opener.open(request,timeout=timeout) as response:raw=response.read(65537)
            assert len(raw)<=65536
            data=json.loads(raw);choice=(data.get('choices') or [{}])[0]
            safe=dict(model=data.get('model'),provider=data.get('provider'),usage=data.get('usage'),finish_reason=choice.get('finish_reason'),
                content=choice.get('message',{}).get('content'),refusal=bool(choice.get('message',{}).get('refusal')),response_hash=hashlib.sha256(raw).hexdigest())
            return io.BytesIO(raw)
        except HTTPError as error:
            self.rate_limited=error.code==429
            safe=dict(outcome='HTTP_REJECTED',http_status=error.code)
            raise
        finally:
            safe.update(attempt=n,case=self.case,frozen_version=self.version,latency_ms=int((time.monotonic()-started)*1000))
            (ROOT/f'raw-{n}.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


@pytest.mark.parametrize('case',CASES)
def test_l32_live_as03(assistant,case,monkeypatch):
    run_case(assistant,case,monkeypatch)


def run_case(assistant,case,monkeypatch,*,audit_final=None):
    state,base,summary,headers,body,path=assistant
    record=retained_record('infeasible',actor_id=base.actor_id) if case in ('no_winner','why_missing') else realistic_record(actor_id=base.actor_id)
    row=row_for(record)
    with Session(state[1]) as s:s.add(PlanningRun(**vars(row)));s.commit()
    from dotenv import dotenv_values
    values=dotenv_values('.env')
    # Same already-authorized configured model as L3.1; production never inherits
    # summary settings. This isolated live fixture explicitly enables chat only.
    model=values.get('CHAT_MODEL') or values.get('SUMMARY_MODEL')
    assert model=='google/gemini-2.5-flash'
    providers=tuple(json.loads(values.get('CHAT_PROVIDERS') or '[]'))
    profile=ChatProfile(enabled=True,model=model,providers=providers,input_bytes=24000,max_tokens=1200,
        completion_limit=2,deadline_seconds=60,max_request_cost_usd='0.10')
    version=fingerprint()
    frozen=ROOT/f'freeze-{version}.json'
    assert frozen.is_file(),'Freeze final source after offline verification before live acceptance'
    assert json.loads(frozen.read_text(encoding='utf8'))['frozen_version']==version
    transport=Transport(case,version);transport.model=model
    provider=OpenRouterConversationalProvider(SecretStr(values['OPENROUTER_API_KEY']),opener=transport);values.clear()
    service=AssistantChat(summary.planning,profile,provider);state[5].app.state.assistant_chat=service
    from app.application import chat_assertions
    original_inspect=chat_assertions.inspect_output;checks=[]
    def capture(output,plan,locale,**kwargs):
        result=original_inspect(output,plan,locale,**kwargs)
        checks.append(dict(validator_version='chat_assertions/'+plan.version.split('/')[-1],input=output.model_dump(mode='json'),
            required=list(plan.required),facts=[f.model_dump(mode='json') for f in plan.facts],
            failures=list(result.failures),disposition=result.disposition,
            verified_output=result.output.model_dump(mode='json') if result.output else None))
        return result
    monkeypatch.setattr(chat_assertions,'inspect_output',capture)
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant/messages'
    body={**body,'expected_evidence_version':row.record_digest,'question':CASES[case],'ingredient_id':None,'history':[]}
    if case=='why_missing':
        from app.application.planning_public_projection import project_run
        from app.application.decision_evidence_projection import project_evidence
        view=project_run(record,response_version=row.record_digest)
        scoped=project_evidence(record,view,option_id=view.result.winner_option_id)
        body['ingredient_id']=str(scoped.overview.ingredients[0].ingredient_id)
    questions=('Sữa cần mua bao nhiêu?','Sữa tươi','Vì sao lượng đó?','Còn sữa đặc?') if case=='conversation' else (CASES[case],)
    context=None
    for turn,q in enumerate(questions,1):
        shared,_=reservations(BASE)
        remaining=MAX_ATTEMPTS-len(shared)
        if remaining<=0:pytest.skip('Shared completion cap exhausted; unexecuted live turn remains pending')
        service.profile=profile.model_copy(update={'completion_limit':min(profile.completion_limit,remaining)})
        req={**body,'question':q}
        if context:req['context']=context
        attempt_start=len(transport.attempts);validation_start=len(checks)
        key={**headers,'Idempotency-Key':str(uuid4())};started=time.monotonic()
        response=state[5].post(path,headers=key,json=req)
        final=dict(case=case,turn=turn,frozen_version=version,request=req,completion_attempts=list(transport.attempts),http_status=response.status_code,
            application_latency_ms=int((time.monotonic()-started)*1000),validation_checks=list(checks))
        final['turn_completion_attempts']=list(transport.attempts[attempt_start:])
        final['turn_validation_checks']=list(checks[validation_start:])
        if response.status_code==200:
            result=response.json()['data'];final['final']=result;context=result.get('context')
            count=len(transport.attempts)
            replay=state[5].post(path,headers=key,json=req)
            get=state[5].get(path)
            final['replay_completions']=len(transport.attempts)-count;final['get_status']=get.status_code
            final['replay_equal']=replay.status_code==200 and replay.json()['data']==result
            with Session(state[1]) as fresh:
                from app.models import AssistantMessage
                from sqlalchemy import select
                final['fresh_persisted_response']=fresh.scalar(select(AssistantMessage).where(AssistantMessage.key_digest==key_digest(key['Idempotency-Key']))).record_json['response']==result
            if audit_final is not None:
                try:final['authority_checks']=audit_final(state,record,path,key,req,transport)
                except AssertionError:
                    final['authority_checks']={'failure':'AUTHORITY_ASSERTION_FAILED'}
        ROOT.mkdir(parents=True,exist_ok=True)
        (ROOT/f'final-{case}-{turn}-{version[:12]}-{uuid4().hex[:8]}.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        assert response.status_code==200,response.text
        assert final['replay_equal'] and final['replay_completions']==0 and final['fresh_persisted_response'] and final['get_status']==405
        assert final.get('authority_checks',{}).get('failure') is None
        if transport.rate_limited:pytest.fail('HTTP429: batch stopped; usage remains unknown and reservation consumed')
