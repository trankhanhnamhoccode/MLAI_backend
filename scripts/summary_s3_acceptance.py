"""Offline S3 acceptance using this task's retained DB. No paid transport or key."""
from dataclasses import asdict
import hashlib,json,os
from pathlib import Path
from uuid import UUID,uuid4

ROOT=Path('runtime/s3-summary')
HISTORY=Path(__file__).resolve().parents[2]/'backend-plan-summary-narrative/runtime'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')


def fingerprint():
    paths=sorted([*Path('app').rglob('*.py'),Path('scripts/summary_s3_acceptance.py'),Path('scripts/summary_s3_verify.py'),
        Path('tests/summary_s3_cases.py'),Path('tests/unit/test_owner_summary_v2.py')])
    hashes={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),hashes


def ledger():
    # Read-only invariant, never opens a paid runner or alters a closed ledger.
    return {p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for name in ('s2-summary','s21-summary')
        for p in (HISTORY/name).glob('*.json') if p.name.startswith('attempt-') or p.name=='STOP.json'}


def settings():
    from sqlalchemy.engine import make_url
    from sqlalchemy import text
    from app.config import Settings
    from app.infrastructure.database.engine import create_database_engine
    from scripts.dev import validate_reset_target,inspect_database
    # Explicit already-owned S1/S2 target, never another agent's/test/demo DB.
    url=(HISTORY/'s1/private/test-url.txt').read_text(encoding='utf8')
    u=make_url(url)
    assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5443,'shelfcash_assistant_test','shelfcash_assistant_tester')
    value=Settings(_env_file=None,environment='test',database_url=url,test_database_url=url,
        chat_llm_enabled=False,summary_llm_enabled=False,auth_email_delivery_enabled=False,
        import_llm_suggestions_enabled=False,import_worker_enabled=False,planning_worker_enabled=False,
        pdf_export_worker_enabled=False,notification_worker_enabled=False)
    validate_reset_target(value);engine=create_database_engine(value)
    with engine.connect() as c:
        assert c.scalar(text('SELECT current_database()'))==u.database and c.scalar(text('SELECT current_user'))==u.username
        assert not any(c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one())
    engine.dispose();assert inspect_database(value)['at_head']
    os.environ.update(ENVIRONMENT='test',DATABASE_URL=url,TEST_DATABASE_URL=url,CHAT_LLM_ENABLED='false',SUMMARY_LLM_ENABLED='false',
        AUTH_EMAIL_DELIVERY_ENABLED='false',IMPORT_LLM_SUGGESTIONS_ENABLED='false')
    os.environ.pop('OPENROUTER_API_KEY',None)
    return value


def prepare(state):
    from tests.integration.test_auth_public import login,ORIGIN
    from tests.summary_s2_cases import oracle
    from tests.summary_s3_cases import persist_warning_case
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.plan_summary import PlanSummaries
    from app.application.contracts.plan_summary import SummaryRequest,SummaryDiagnostics
    from app.application.owner_summary_v2 import owner_plan,render_owner,OWNER_VERSIONS
    from app.infrastructure.plan_summary_provider import profile_from_settings,payload_for,PresentationResult
    from app.application.contracts.summary_narrative import CompactNarrative
    from sqlalchemy.orm import Session
    from app.models.plan_summary import PlanSummaryGeneration
    from app.application.use_cases.plan_summary import decode_summary
    wire=login(state,email='summary-s2@example.test');assert wire.status_code==200
    token=state[5].cookies.get('shelfcash_dev_session') or state[5].cookies.get('__Host-shelfcash_session')
    csrf=wire.json()['data']['session']['csrf_token']
    profile=profile_from_settings(state[0].model_copy(update={'summary_llm_enabled':True,'summary_model':'S3-SYNTHETIC-'+str(uuid4()),'summary_max_tokens':1200}))
    assert profile.version=='summary_profile/6'
    service=PlanSummaries(PublicPlanning(state[2],None),profile,None,clock=state[2].clock)
    state[5].app.state.plan_summaries=service
    runs=json.loads((HISTORY/'s2-summary/runs.json').read_text(encoding='utf8'))
    actor=service.planning.read_record(token,UUID(runs['A']),evidence_only=True)[0].actor_id
    warning=persist_warning_case(state[1],actor);runs['W']=str(warning.run_id)
    matrix={}
    for kind,ident in runs.items():
        run=UUID(ident);record,view=service.planning.read_record(token,run,evidence_only=True)
        request=SummaryRequest(expected_evidence_version=view.response_version,option_id=None,locale='vi',detail_level='simple')
        e=service._evidence(token,run,request);plan=owner_plan(e,request)
        expected=oracle(e,kind) if kind in 'ABCDEF' else dict(synthetic=True,warnings=[n.code for n in e.overview.explanation.warnings],
            forbidden=['warning_becomes_blocker','invented_causality','unknown_code_claims_no_risk'])
        fallback=render_owner(e,request,SummaryDiagnostics(disposition='FALLBACK',reason='MODEL_DISABLED',requested_model=None))
        payload=payload_for(e,request,fallback,profile)
        class Fake:
            calls=0
            def present(self,payload,profile):
                self.calls+=1;body=json.loads(payload)
                assert body['task']=='owner_summary/2'
                return PresentationResult(None,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',requested_model=profile.model,attempts=1),
                    compact=CompactNarrative(clauses=[dict(fact_id=f['fact_id'],text=f['examples'][0]) for f in body['facts'] if f['obligation']=='required']))
        fake=Fake();service.provider=fake;key=str(uuid4());path=f'/api/v1/procurement-plans/{run}/assistant/summary'
        body=request.model_dump(mode='json');headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':key}
        result=state[5].post(path,headers=headers,json=body);assert result.status_code==200,result.text
        data=result.json()['data'];assert data['result']['source']=='model_presentation'
        assert state[5].get(path+'/'+data['generation_id']).json()['data']==data
        assert state[5].post(path,headers=headers,json=body).json()['data']==data and fake.calls==1
        with Session(state[1]) as fresh:assert decode_summary(fresh.get(PlanSummaryGeneration,UUID(data['generation_id']))).result.model_dump(mode='json')==data['result']
        service.profile=profile.model_copy(update={'enabled':False})
        off=service.create(token,run,request,str(uuid4()),csrf)
        assert off.result.answer==fallback.answer and fake.calls==1
        if kind=='W':assert 'dự phòng' in off.result.answer and 'thông tin lưu ý' in off.result.answer
        service.profile=profile
        matrix[kind]=dict(run_id=ident,request=body,record=record.model_dump(mode='json'),evidence=e.model_dump(mode='json'),
            communication_plan=[asdict(f) for f in plan],provider_payload=json.loads(payload),oracle=expected,
            final=data,deterministic_fallback=off.model_dump(mode='json'),AS02_equal=True,fresh_session_equal=True,replay_no_extra_call=True)
    service.profile=profile
    fp,hashes=fingerprint();freeze=dict(fingerprint=fp,source_sha256=hashes,versions=OWNER_VERSIONS,matrix=matrix,mode='OFFLINE_FAKE_PROVIDER',live_calls=0)
    write(ROOT/f'acceptance-{fp}.json',freeze)
    return service,freeze,token,csrf,ORIGIN
