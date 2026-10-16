"""User-authorized S2 synthetic HTTP acceptance; isolated ledger, no implicit retry.

The private key is read in memory from the named existing configuration. Only
allowlisted request bodies and provider response fields enter ignored evidence.
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID,uuid4
from urllib.request import build_opener

ROOT=Path('runtime/s2-summary')
GROUP='summary-S2-16-USD0.30'
BOUND=Decimal('0.025')  # Three Google routes: 17,024 input + 1,200 output each, rounded up.
MODEL='google/gemini-2.5-flash'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')


def ledger(root=ROOT):
    rows=[json.loads(p.read_text(encoding='utf8')) for p in sorted(root.glob('attempt-*.json'))]
    for n,row in enumerate(rows,1):
        assert row['attempt']==n and row['group']==GROUP and Decimal(row['reserved_usd'])==BOUND
        if row.get('cost_usd') is not None:assert Decimal(0)<=Decimal(row['cost_usd'])<=BOUND
    used=sum((Decimal(r['cost_usd']) if r.get('cost_usd') is not None else Decimal(r['reserved_usd']) for r in rows),Decimal(0))
    return rows,used


def reserve(record,root=ROOT):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'ledger.lock').open('x') as lock:lock.write('Fail closed on interrupted reservation')
    try:
        rows,used=ledger(root)
        if sum(r.get('transport_attempts',3) for r in rows)+3>16 or used+BOUND>Decimal('.30'):raise ValueError('S2 budget exhausted')
        if (root/'STOP.json').exists():raise ValueError('S2 stopped; inspect existing failure before another attempt')
        n=len(rows)+1
        path=root/f'attempt-{n:02d}.json'
        with path.open('x',encoding='utf8') as out:
            json.dump(dict(record,group=GROUP,attempt=n,reserved_usd=str(BOUND),cost_usd=None,transport_attempts=3),out,indent=2)
            out.flush();os.fsync(out.fileno())
        return n,path
    finally:(root/'ledger.lock').unlink()


def fingerprint():
    paths=sorted([*Path('app').rglob('*.py'),Path('tests/summary_s2_cases.py'),Path('scripts/summary_s2_live.py')])
    hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    value=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return value,hashes


class CappedTransport:
    def __init__(self,case,freeze):self.case,self.freeze,self.calls,self.last=case,freeze,0,None

    def open(self,request,timeout):
        from app.infrastructure.import_suggestions import NoRedirect
        sent=json.loads(request.data)
        assert request.full_url=='https://openrouter.ai/api/v1/chat/completions'
        assert sent['model']==MODEL and sent['max_tokens']<=1200
        assert sent['provider']['order']==['Google'] and not sent['provider']['allow_fallbacks']
        assert sent['provider']['require_parameters']
        # Price ceiling excludes the higher-priced priority route in metadata.
        sent['provider']['max_price']={'prompt':.3,'completion':2.5}
        # Summary clauses need no hidden reasoning; keep the 1,200-token cap for
        # the structured answer, as supported by the frozen Google metadata.
        assert sent['reasoning']=={'enabled':False}
        request.data=json.dumps(sent,ensure_ascii=False).encode('utf8')
        assert len(request.data)<=16000
        assert fingerprint()[0]==self.freeze['fingerprint'],'Source changed after freeze'
        n,path=reserve(dict(case=self.case,source=self.freeze['fingerprint'],model=MODEL,provider='Google',max_tokens=1200))
        self.last=n;self.calls+=1
        folder=ROOT/f'attempt-{n:02d}'
        write(folder/'request.json',sent)  # No Authorization/cookies/CSRF.
        started=time.monotonic()
        try:
            with build_opener(NoRedirect()).open(request,timeout=timeout) as response:raw=response.read(65537)
            assert len(raw)<=65536
            body=json.loads(raw)
            safe={k:body.get(k) for k in ('id','model','provider','usage','choices','error')}
            write(folder/'raw.json',safe)
            row=json.loads(path.read_text(encoding='utf8'))
            usage=body.get('usage') or {}
            cost=usage.get('cost')
            row.update(latency_seconds=time.monotonic()-started,usage=usage,resolved_model=body.get('model'),
                resolved_provider=body.get('provider'),finish_reason=(body.get('choices') or [{}])[0].get('finish_reason'),transport_attempts=1)
            if cost is not None:
                actual=Decimal(str(cost))
                assert actual>=0 and actual<=BOUND,'Reported cost exceeds conservative reservation'
                row['cost_usd']=str(actual)
            write(path,row)
            return io.BytesIO(raw)
        except Exception as error:
            row=json.loads(path.read_text(encoding='utf8'))
            row.update(latency_seconds=time.monotonic()-started,transport_error=type(error).__name__,http_status=getattr(error,'code',None))
            from urllib.error import HTTPError
            if isinstance(error,HTTPError):
                raw_error=error.read(65537).decode('utf8',errors='replace')
                authorization=request.get_header('Authorization') or ''
                if authorization:
                    raw_error=raw_error.replace(authorization,'[REDACTED]').replace(authorization.removeprefix('Bearer '),'[REDACTED]')
                try:
                    error_body=json.loads(raw_error)
                    error_body.pop('user_id',None)
                    raw_error=json.dumps(error_body)
                    previous=error_body.get('error',{}).get('metadata',{}).get('previous_errors',[])
                    row['transport_attempts']=max(1,len(previous)+1)
                except ValueError:pass
                write(folder/'http-error.json',dict(status=error.code,body=raw_error[:32000]))
            write(path,row)
            raise


def settings():
    from sqlalchemy.engine import make_url
    from sqlalchemy import text
    from app.config import Settings
    from app.infrastructure.database.engine import create_database_engine
    from scripts.dev import validate_reset_target,inspect_database
    url=Path('runtime/s1/private/test-url.txt').read_text(encoding='utf8')
    u=make_url(url)
    assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5443,'shelfcash_assistant_test','shelfcash_assistant_tester')
    value=Settings(_env_file=None,environment='test',database_url=url,test_database_url=url,
        chat_llm_enabled=False,summary_llm_enabled=False,auth_email_delivery_enabled=False,
        import_llm_suggestions_enabled=False,import_worker_enabled=False,planning_worker_enabled=False,
        pdf_export_worker_enabled=False,notification_worker_enabled=False)
    validate_reset_target(value)
    engine=create_database_engine(value)
    with engine.connect() as c:
        assert c.scalar(text('SELECT current_database()'))==u.database and c.scalar(text('SELECT current_user'))==u.username
        assert not any(c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one())
    engine.dispose()
    assert inspect_database(value)['at_head']
    os.environ.update(ENVIRONMENT='test',DATABASE_URL=url,TEST_DATABASE_URL=url,CHAT_LLM_ENABLED='false',SUMMARY_LLM_ENABLED='false',
        AUTH_EMAIL_DELIVERY_ENABLED='false',IMPORT_LLM_SUGGESTIONS_ENABLED='false')
    return value


def prepare(state):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tests.integration.test_auth_public import setup,login,ORIGIN
    from tests.assistant_cases import retained_record,row_for
    from tests.summary_s2_cases import persist_case,oracle
    from app.models import Store,StoreMembership,PlanningRun
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.plan_summary import PlanSummaries
    from app.application.contracts.plan_summary import SummaryProfile,SummaryRequest,SummaryDiagnostics
    from app.application.summary_narrative import communication_plan,render_narrative,versions
    from app.infrastructure.plan_summary_provider import payload_for
    # Persistent harness deliberately does not reset on exit or resume.
    with Session(state[1]) as s:owner=s.scalar(select(StoreMembership).where(StoreMembership.store_id==UUID(int=1)))
    if owner is None:
        receipt=setup(state,email='summary-s2@example.test')
        actor_id=receipt.user_id
        with Session(state[1]) as s:
            s.add(Store(id=UUID(int=1),name='S2 synthetic Cafe',timezone='UTC',currency='VND',active=True));s.flush()
            s.add(StoreMembership(store_id=UUID(int=1),user_id=actor_id,role='OWNER',active=True));s.commit()
    else:actor_id=owner.user_id
    if not (ROOT/'runs.json').exists():
        records={kind:persist_case(state[1],actor_id,kind) for kind in ('A','D','F')}
        records.update({kind:retained_record(name,actor_id=actor_id) for kind,name in (('B','stock'),('C','infeasible'),('E','failed-partial'))})
        with Session(state[1]) as s:
            for kind in ('B','C','E'):s.add(PlanningRun(**vars(row_for(records[kind]))))
            s.commit()
        write(ROOT/'runs.json',{k:str(r.run_id) for k,r in records.items()})
    wire=login(state,email='summary-s2@example.test')
    assert wire.status_code==200,'S2 synthetic owner login failed'
    token=state[5].cookies.get('shelfcash_dev_session') or state[5].cookies.get('__Host-shelfcash_session')
    csrf=wire.json()['data']['session']['csrf_token']
    public=PublicPlanning(state[2],None)
    profile=SummaryProfile(enabled=True,model=MODEL,providers=('Google',),max_tokens=1200,
        timeout_seconds=30,deadline_seconds=35,version='summary_profile/4')
    service=PlanSummaries(public,profile,None,clock=state[2].clock)
    state[5].app.state.plan_summaries=service
    ids=json.loads((ROOT/'runs.json').read_text(encoding='utf8'))
    matrix={}
    for kind,ident in ids.items():
        record,view=public.read_record(token,UUID(ident),evidence_only=True)
        request=SummaryRequest(expected_evidence_version=view.response_version,option_id=None,locale='vi',detail_level='simple')
        evidence=service._evidence(token,record.run_id,request)
        expected=oracle(evidence,kind)
        fallback=render_narrative(evidence,request,SummaryDiagnostics(disposition='FALLBACK',reason='MODEL_DISABLED',requested_model=None))
        payload=payload_for(evidence,request,fallback,profile)
        matrix[kind]=dict(run_id=ident,request=request.model_dump(mode='json'),oracle=expected,
            evidence=evidence.model_dump(mode='json'),communication_plan=json.loads(payload),record=record.model_dump(mode='json'))
    fp,hashes=fingerprint()
    metadata=json.loads((ROOT/'provider-metadata.json').read_text(encoding='utf8'))
    required={'temperature','max_tokens','response_format','structured_outputs'}
    routes=[e for e in metadata['data']['endpoints'] if e['provider_name']=='Google'
        and required<=set(e['supported_parameters']) and Decimal(e['pricing']['prompt'])<=Decimal('.0000003')
        and Decimal(e['pricing']['completion'])<=Decimal('.0000025')
        and Decimal(e['pricing'].get('request','0'))==0]
    assert routes,'Pinned Google structured route unavailable within price ceiling'
    freeze=dict(fingerprint=fp,source_sha256=hashes,checkpoint=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        profile=profile.model_dump(mode='json'),versions=versions(profile),matrix=matrix,
        limits=dict(attempts=16,usd='.30',max_tokens=1200,reservation_usd=str(BOUND),pending_transport_attempts=3),
        route=dict(order=['Google'],allow_fallbacks=False,max_price=dict(prompt=.3,completion=2.5),reasoning=dict(enabled=False)),synthetic=True,
        metadata_sha256=hashlib.sha256((ROOT/'provider-metadata.json').read_bytes()).hexdigest())
    dest=ROOT/f'freeze-{fp}.json'
    if dest.exists():assert json.loads(dest.read_text(encoding='utf8'))==freeze
    else:
        write(dest,freeze)
        for name in hashes:
            target=ROOT/'source'/fp/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(name).read_bytes())
    return service,freeze,token,csrf,ORIGIN


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--prepare',action='store_true')
    p.add_argument('--allow-paid-s2-max-16-usd-0.30',dest='paid',action='store_true')
    p.add_argument('--case',choices=list('ABCDEF'))
    a=p.parse_args()
    if not a.prepare and not (a.paid and a.case):p.error('Explicit prepare or S2 paid opt-in + single case required')
    from tests.integration.test_auth_public import env
    gen=env.__wrapped__(settings());state=next(gen)
    try:
        service,freeze,token,csrf,origin=prepare(state)
        if a.prepare:
            print(json.dumps(dict(prepared=list(freeze['matrix']),fingerprint=freeze['fingerprint'],paid_attempts=len(ledger()[0]))));return
        from dotenv import dotenv_values
        from pydantic import SecretStr
        from app.infrastructure.plan_summary_provider import OpenRouterSummaryProvider
        values=dotenv_values(Path('../backend/.env'))
        key=values.get('OPENROUTER_API_KEY');values.clear()
        if not key:raise RuntimeError('Fill OPENROUTER_API_KEY in existing private ../backend/.env; no call made')
        transport=CappedTransport(a.case,freeze)
        service.provider=OpenRouterSummaryProvider(SecretStr(key),opener=transport);key=None
        case=freeze['matrix'][a.case]
        headers={'Origin':origin,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())}
        path=f"/api/v1/procurement-plans/{case['run_id']}/assistant/summary"
        started=time.monotonic()
        response=state[5].post(path,headers=headers,json=case['request'])
        assert response.status_code==200,f'AS01 HTTP{response.status_code}'
        data=response.json()['data'];n=transport.last
        assert n is not None,'No completion dispatched; inspect setup'
        folder=ROOT/f'attempt-{n:02d}'
        from app.application.contracts.plan_summary import SummaryRequest
        from app.application.summary_narrative import communication_plan,reconcile_narrative
        from app.application.contracts.summary_narrative import SummaryNarrative
        trace=dict(disposition=data['result']['diagnostics'],missing=[],rejected=[])
        raw=json.loads((folder/'raw.json').read_text(encoding='utf8')) if (folder/'raw.json').exists() else {}
        try:
            evidence=service._evidence(token,UUID(case['run_id']),SummaryRequest(**case['request']))
            plan=communication_plan(evidence,SummaryRequest(**case['request']))
            from app.application.contracts.summary_narrative import CompactNarrative
            from app.application.summary_narrative import expand_compact
            parsed=expand_compact(plan,CompactNarrative.model_validate_json(raw['choices'][0]['message']['content'])) if service.profile.version=='summary_profile/4' else SummaryNarrative.model_validate_json(raw['choices'][0]['message']['content'])
            seen={c.fact_id for s in parsed.sections() for c in s.clauses}
            trace['missing']=sorted({f.fact_id for f in plan}-seen)
            expected={f.fact_id:f for f in plan}
            trace['rejected']=[dict(fact_id=c.fact_id,text=c.text,reason='surface_or_binding_not_licensed')
                for s in parsed.sections() for c in s.clauses if c.fact_id not in expected or
                c.text not in expected[c.fact_id].surfaces or c.evidence_ids!=expected[c.fact_id].evidence_ids]
            reconcile_narrative(plan,parsed)
        except Exception as error:trace['error']=type(error).__name__+': '+str(error)[:400]
        write(folder/'validation.json',trace)
        from sqlalchemy.orm import Session
        from app.models.plan_summary import PlanSummaryGeneration
        from app.application.use_cases.plan_summary import decode_summary
        with Session(state[1]) as fresh:
            assert decode_summary(fresh.get(PlanSummaryGeneration,UUID(data['generation_id']))).result.model_dump(mode='json')==data['result']
        before=transport.calls
        assert state[5].get(path+'/'+data['generation_id']).json()['data']==data
        assert state[5].post(path,headers=headers,json=case['request']).json()['data']==data
        assert transport.calls==before==1
        write(folder/'final.json',dict(case=a.case,request=case['request'],idempotency_key=headers['Idempotency-Key'],response=data,source=freeze['fingerprint'],
            elapsed_seconds=time.monotonic()-started,fresh_session_equal=True,GET_equal=True,replay_equal=True,extra_provider_calls=0))
        rows,used=ledger()
        print(json.dumps(dict(case=a.case,attempt=n,source=data['result']['source'],reason=data['result']['diagnostics']['reason'],
            attempts=len(rows),charged_or_reserved_usd=str(used),remaining_usd=str(Decimal('.30')-used))))
    finally:
        try:next(gen)
        except StopIteration:pass


if __name__=='__main__':main()
