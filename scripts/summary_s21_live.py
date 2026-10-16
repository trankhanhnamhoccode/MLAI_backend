"""S2.1 independent frozen synthetic acceptance. Never writes the closed S2 ledger."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import UUID,uuid4
from urllib.request import build_opener
from urllib.error import HTTPError

from scripts.summary_s2_live import settings,write  # Read-only DB guard and generic JSON writer.

ROOT=Path('runtime/s21-summary')
MODEL='google/gemini-2.5-flash'
BOUND=Decimal('.025')
GROUP='summary-S2.1-10-USD0.15'


def ledger(root=ROOT):
    rows=[json.loads(p.read_text(encoding='utf8')) for p in sorted(root.glob('attempt-*.json'))]
    for n,r in enumerate(rows,1):
        assert r['attempt']==n and r['group']==GROUP and Decimal(r['reserved_usd'])==BOUND
        if r.get('cost_usd') is not None:assert 0<=Decimal(r['cost_usd'])<=BOUND
    return rows,sum((Decimal(r['cost_usd']) if r.get('cost_usd') is not None else BOUND for r in rows),Decimal(0))


def reserve(record,root=ROOT):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'ledger.lock').open('x') as f:f.write('Fail closed; no implicit refund')
    try:
        rows,cost=ledger(root)
        if (root/'STOP.json').exists():raise ValueError('S2.1 ledger closed')
        if sum(r.get('transport_attempts',3) for r in rows)+3>10 or cost+BOUND>Decimal('.15'):raise ValueError('S2.1 budget exhausted')
        if any(r['case']==record['case'] and r['source']==record['source'] for r in rows):raise ValueError('No repeated case on unchanged source')
        n=len(rows)+1;path=root/f'attempt-{n:02d}.json'
        with path.open('x',encoding='utf8') as f:
            json.dump(dict(record,attempt=n,group=GROUP,reserved_usd=str(BOUND),cost_usd=None,transport_attempts=3),f,indent=2)
            f.flush();os.fsync(f.fileno())
        return n,path
    finally:(root/'ledger.lock').unlink()


def fingerprint():
    paths=sorted([*Path('app').rglob('*.py'),Path('scripts/summary_s21_live.py'),Path('scripts/summary_s21_verify.py'),Path('scripts/summary_s2_live.py'),
        Path('tests/summary_s2_cases.py'),Path('tests/unit/test_owner_summary.py'),Path('tests/fixtures_owner_summary.py'),
        Path('tests/fixtures/decision_assistant/owner_summary_evidence.json')])
    hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),hashes


class CappedTransport:
    def __init__(self,case,freeze):self.case,self.freeze,self.calls,self.last=case,freeze,0,None
    def open(self,request,timeout):
        from app.infrastructure.import_suggestions import NoRedirect
        body=json.loads(request.data)
        assert request.full_url=='https://openrouter.ai/api/v1/chat/completions'
        assert body['model']==MODEL and body['max_tokens']<=1200 and body['reasoning']=={'enabled':False}
        assert body['provider']['order']==['Google'] and body['provider']['allow_fallbacks'] is False
        body['provider']['max_price']={'prompt':.3,'completion':2.5}
        request.data=json.dumps(body,ensure_ascii=False).encode('utf8');assert len(request.data)<=16000
        assert fingerprint()[0]==self.freeze['fingerprint']
        n,path=reserve(dict(case=self.case,source=self.freeze['fingerprint'],model=MODEL,provider='Google',max_tokens=1200))
        self.last=n;self.calls+=1;folder=ROOT/f'attempt-{n:02d}'
        write(folder/'request.json',body)
        started=time.monotonic()
        try:
            with build_opener(NoRedirect()).open(request,timeout=timeout) as response:raw=response.read(65537)
            assert len(raw)<=65536;response=json.loads(raw)
            safe={k:response.get(k) for k in ('id','model','provider','usage','choices','error')}
            write(folder/'raw.json',safe)
            r=json.loads(path.read_text(encoding='utf8'));usage=response.get('usage') or {}
            r.update(usage=usage,transport_attempts=1,latency_seconds=time.monotonic()-started,
                resolved_model=response.get('model'),resolved_provider=response.get('provider'),
                finish_reason=(response.get('choices') or [{}])[0].get('finish_reason'))
            if usage.get('cost') is not None:
                cost=Decimal(str(usage['cost']));assert 0<=cost<=BOUND;r['cost_usd']=str(cost)
            write(path,r);return io.BytesIO(raw)
        except Exception as error:
            r=json.loads(path.read_text(encoding='utf8'));r.update(transport_error=type(error).__name__,latency_seconds=time.monotonic()-started)
            if isinstance(error,HTTPError):
                text=error.read(65537).decode('utf8',errors='replace')
                auth=request.get_header('Authorization') or ''
                if auth:text=text.replace(auth,'[REDACTED]').replace(auth.removeprefix('Bearer '),'[REDACTED]')
                try:
                    parsed=json.loads(text);parsed.pop('user_id',None);text=json.dumps(parsed)
                    r['transport_attempts']=max(1,1+len(parsed.get('error',{}).get('metadata',{}).get('previous_errors',[])))
                except ValueError:pass
                write(folder/'http-error.json',dict(status=error.code,body=text[:32000]))
            write(path,r);raise


def prepare(state):
    from tests.integration.test_auth_public import login,ORIGIN
    from tests.summary_s2_cases import oracle
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.plan_summary import PlanSummaries
    from app.application.contracts.plan_summary import SummaryProfile,SummaryRequest,SummaryDiagnostics
    from app.application.owner_summary import owner_plan,render_owner,OWNER_VERSIONS
    from app.infrastructure.plan_summary_provider import payload_for
    wire=login(state,email='summary-s2@example.test');assert wire.status_code==200
    token=state[5].cookies.get('shelfcash_dev_session') or state[5].cookies.get('__Host-shelfcash_session')
    csrf=wire.json()['data']['session']['csrf_token']
    service=PlanSummaries(PublicPlanning(state[2],None),SummaryProfile(enabled=True,model=MODEL,providers=('Google',),max_tokens=1200,
        timeout_seconds=30,deadline_seconds=35,version='summary_profile/5'),None,clock=state[2].clock)
    state[5].app.state.plan_summaries=service
    runs=json.loads(Path('runtime/s2-summary/runs.json').read_text(encoding='utf8'))  # Read-only IDs, no credentials.
    matrix={}
    for kind in 'ABCDEF':
        run=UUID(runs[kind]);record,view=service.planning.read_record(token,run,evidence_only=True)
        request=SummaryRequest(expected_evidence_version=view.response_version,option_id=None,locale='vi',detail_level='simple')
        e=service._evidence(token,run,request);expected=oracle(e,kind)
        plan=owner_plan(e,request)
        fallback=render_owner(e,request,SummaryDiagnostics(disposition='FALLBACK',reason='MODEL_DISABLED',requested_model=None))
        payload=payload_for(e,request,fallback,service.profile)
        assert b'IGNORE SYSTEM' not in payload
        matrix[kind]=dict(run_id=str(run),request=request.model_dump(mode='json'),record=record.model_dump(mode='json'),
            source_digest=view.response_version,evidence=e.model_dump(mode='json'),oracle=expected,
            communication_plan=[asdict(f) for f in plan],provider_payload=json.loads(payload),
            obligations={key:[f.fact_id for f in plan if f.obligation==key] for key in ('required','optional','detail')},
            C05='NOT_USED')
    metadata=json.loads((ROOT/'provider-metadata.json').read_text(encoding='utf8'))
    required={'response_format','structured_outputs','temperature','max_tokens','reasoning'}
    routes=[e for e in metadata['data']['endpoints'] if e['provider_name']=='Google' and required<=set(e['supported_parameters'])
        and Decimal(e['pricing']['prompt'])<=Decimal('.0000003') and Decimal(e['pricing']['completion'])<=Decimal('.0000025')
        and Decimal(e['pricing'].get('request','0'))==0]
    assert 0<len(routes)<=3,'Refresh bounded route reservation if eligible routes change'
    fp,hashes=fingerprint()
    freeze=dict(fingerprint=fp,source_sha256=hashes,S2_checkpoint=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        versions=OWNER_VERSIONS,profile=service.profile.model_dump(mode='json'),matrix=matrix,
        metadata_sha256=hashlib.sha256((ROOT/'provider-metadata.json').read_bytes()).hexdigest(),
        limits=dict(attempts=10,usd='.15',max_tokens=1200,reserved_usd=str(BOUND),pending_transport_attempts=3),
        routing=dict(provider='Google',allow_fallbacks=False,max_price=dict(prompt=.3,completion=2.5)),synthetic=True)
    p=ROOT/f'freeze-{fp}.json'
    if p.exists():assert json.loads(p.read_text(encoding='utf8'))==json.loads(json.dumps(freeze,default=str))
    else:
        write(p,freeze)
        for name in hashes:
            dest=ROOT/'source'/fp/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(Path(name).read_bytes())
    return service,freeze,token,csrf,ORIGIN


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--allow-paid-s21-max-10-usd-0.15',dest='paid',action='store_true');parser.add_argument('--case',choices=list('ABCDEF'))
    a=parser.parse_args()
    if not a.prepare and not (a.paid and a.case):parser.error('Explicit prepare or S2.1 paid single-case opt-in required')
    from tests.integration.test_auth_public import env
    gen=env.__wrapped__(settings());state=next(gen)
    try:
        service,freeze,token,csrf,origin=prepare(state)
        if a.prepare:print(json.dumps(dict(prepared=list(freeze['matrix']),fingerprint=freeze['fingerprint'],paid_requests=len(ledger()[0]))));return
        from dotenv import dotenv_values
        from pydantic import SecretStr
        from app.infrastructure.plan_summary_provider import OpenRouterSummaryProvider
        values=dotenv_values(Path('../backend/.env'));key=values.get('OPENROUTER_API_KEY');values.clear()
        if not key:raise RuntimeError('Existing private ../backend/.env lacks OPENROUTER_API_KEY; live BLOCKED')
        transport=CappedTransport(a.case,freeze);service.provider=OpenRouterSummaryProvider(SecretStr(key),opener=transport);key=None
        case=freeze['matrix'][a.case];headers={'Origin':origin,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())}
        path=f'/api/v1/procurement-plans/{case["run_id"]}/assistant/summary'
        response=state[5].post(path,headers=headers,json=case['request']);assert response.status_code==200,f'AS01 HTTP{response.status_code}'
        data=response.json()['data'];n=transport.last
        assert n is not None,'No new dispatch: inspect retained generation/setup'
        folder=ROOT/f'attempt-{n:02d}'
        from app.application.contracts.summary_narrative import CompactNarrative
        from app.application.contracts.plan_summary import SummaryRequest
        from app.application.owner_summary import owner_plan,validate_surface,render_owner
        trace=dict(diagnostics=data['result']['diagnostics'],missing_required=[],optional_omitted=[],rejected=[])
        try:
            raw=json.loads((folder/'raw.json').read_text(encoding='utf8'))
            compact=CompactNarrative.model_validate_json(raw['choices'][0]['message']['content'])
            e=service._evidence(token,UUID(case['run_id']),SummaryRequest(**case['request']));plan=owner_plan(e,SummaryRequest(**case['request']))
            allowed={f.fact_id:f for f in plan if f.obligation!='detail'};seen={c.fact_id for c in compact.clauses}
            trace['missing_required']=sorted({f.fact_id for f in plan if f.obligation=='required'}-seen)
            trace['optional_omitted']=sorted({f.fact_id for f in plan if f.obligation=='optional'}-seen)
            trace['rejected']=[dict(fact_id=c.fact_id,text=c.text) for c in compact.clauses if c.fact_id not in allowed or not validate_surface(allowed[c.fact_id],c.text)]
            render_owner(e,SummaryRequest(**case['request']),service.read(token,UUID(case['run_id']),UUID(data['generation_id'])).result.diagnostics,compact)
        except Exception as error:trace['error']=type(error).__name__+': '+str(error)[:500]
        write(folder/'validation.json',trace)
        from sqlalchemy.orm import Session
        from app.models.plan_summary import PlanSummaryGeneration
        from app.application.use_cases.plan_summary import decode_summary
        with Session(state[1]) as fresh:assert decode_summary(fresh.get(PlanSummaryGeneration,UUID(data['generation_id']))).result.model_dump(mode='json')==data['result']
        calls=transport.calls
        assert state[5].get(path+'/'+data['generation_id']).json()['data']==data
        assert state[5].post(path,headers=headers,json=case['request']).json()['data']==data
        assert calls==transport.calls==1
        write(folder/'final.json',dict(case=a.case,source=freeze['fingerprint'],request=case['request'],idempotency_key=headers['Idempotency-Key'],
            response=data,fresh_session_equal=True,AS02_equal=True,replay_equal=True,extra_provider_calls=0))
        rows,cost=ledger();print(json.dumps(dict(case=a.case,request=n,source=data['result']['source'],reason=data['result']['diagnostics']['reason'],
            transport_attempts=sum(r.get('transport_attempts',3) for r in rows),exposure_usd=str(cost))))
    finally:
        try:next(gen)
        except StopIteration:pass


if __name__=='__main__':main()
