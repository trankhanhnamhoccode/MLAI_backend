"""L5 combined-source migration and actual host/retained native evidence acceptance."""
from pathlib import Path
from uuid import uuid4
import json
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select,text,inspect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import migration_config,validate_reset_target
from tests.integration.test_planning_public import flow,submit,demand_and_offer
from tests.integration.test_planning_configuration_public import config,base
from tests.integration.test_auth_public import env,setup,login
from tests.integration.test_assistant_summary import assistant

HEAD='l5_20261016_assistant_f4'
ROOT=Path('runtime/assistant-integration')


def versions(engine):
    with engine.connect() as c:return set(c.scalars(text('SELECT version_num FROM alembic_version')))


@pytest.mark.parametrize('parent',['0030_conversational_chat','f4_20261016_metadata_v2'])
def test_upgrade_from_either_parent_and_empty_roundtrip(database_settings,parent):
    validate_reset_target(database_settings)
    engine=create_database_engine(database_settings)
    try:
        command.downgrade(migration_config(),'base')
        assert set(inspect(engine).get_table_names())=={'alembic_version'}
        command.upgrade(migration_config(),parent);assert versions(engine)=={parent}
        command.upgrade(migration_config(),'head');assert versions(engine)=={HEAD}
        with engine.connect() as c:
            assert compare_metadata(MigrationContext.configure(c,opts={'compare_server_default':True}),Base.metadata)==[]
        assert len(inspect(engine).get_table_names())==76
        command.downgrade(migration_config(),'base');command.upgrade(migration_config(),'head')
        assert versions(engine)=={HEAD}
    finally:engine.dispose()


def no_compute(monkeypatch,app):
    def forbidden(*a,**k):raise AssertionError('Assistant must use retained evidence, not engines/artifacts/provider network')
    from app.application.use_cases import bom,procurement_v2,serving
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    monkeypatch.setattr(bom,'expand_bom',forbidden)
    monkeypatch.setattr(procurement_v2,'_evaluate',forbidden)
    monkeypatch.setattr(NativeProductSearch,'solve',forbidden)
    for name in ('prepare','serve','prepare_serve_capture'):
        monkeypatch.setattr(app.state.forecast_serving,name,forbidden)
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)


def summary_chat(state,record,headers,monkeypatch):
    from tests.assistant_cases import row_for
    from app.application.planning_retained_reads import VerifiedPlanningReads
    from app.application.use_cases.assistant_chat import AssistantChat
    from app.application.use_cases.plan_summary import PlanSummaries
    public=state[5].app.state.planning_public
    public.retained=VerifiedPlanningReads()
    old_summary=state[5].app.state.plan_summaries
    old_chat=state[5].app.state.assistant_chat
    assert old_chat.presentation_version==6
    state[5].app.state.plan_summaries=PlanSummaries(public,old_summary.profile,old_summary.provider,clock=state[2].clock)
    state[5].app.state.assistant_chat=AssistantChat(public,old_chat.profile,old_chat.provider)
    no_compute(monkeypatch,state[5].app)
    digest=row_for(record).record_digest
    path=f'/api/v1/procurement-plans/{record.run_id}/assistant'
    body=dict(expected_evidence_version=digest,option_id=None,locale='vi',detail_level='simple')
    summary=state[5].post(path+'/summary',headers={**headers,'Idempotency-Key':str(uuid4())},json=body)
    assert summary.status_code==200,summary.text
    assert summary.json()['data']['result']['source']=='deterministic_fallback'
    assert state[5].get(summary.headers['Location']).json()['data']==summary.json()['data']
    assert state[5].app.state.assistant_chat.presentation_version==6
    request={**body,'question':'Chi phí và ngân sách?','ingredient_id':None,'history':[]}
    key={**headers,'Idempotency-Key':str(uuid4())}
    response=state[5].post(path+'/messages',headers=key,json=request)
    assert response.status_code==200,response.text
    assert state[5].post(path+'/messages',headers=key,json=request).json()['data']==response.json()['data']
    from app.models import AssistantMessage,PlanSummaryGeneration
    with Session(state[1]) as fresh:
        assert fresh.scalar(select(AssistantMessage)).record_json['response']==response.json()['data']
        assert fresh.scalar(select(PlanSummaryGeneration)).status=='completed'
    return dict(summary=summary.json(),message=response.json(),fresh_session_equal=True,replay_zero_compute=True)


def test_actual_host_worker_then_cold_assistant_default_v6(flow,monkeypatch):
    c,ingredient,recipe,worker=flow
    demand_and_offer(flow,maximum='100')
    accepted=submit(c);assert accepted.status_code==202,accepted.text
    record=worker.run_one();assert record.status=='completed',record.error_code
    assert record.public_capture.forecast.model_type=='historical_quantile_baseline'
    proof=summary_chat(c[0],record,c[3],monkeypatch)
    (ROOT/'host-worker-assistant.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')


def test_retained_schema3_metadata2_cold_assistant_and_migration_guard(env,monkeypatch):
    from tests.assistant_integration_cases import challenger_case,create_challenger_run
    from app.models import Store,StoreMembership,ForecastRun,ForecastExecutionMetadata,ForecastRunInput,ForecastPrediction,Product
    from app.application.forecast_serialization import serialize_prepared
    command.downgrade(migration_config(),'base')
    command.upgrade(migration_config(),'f4_20261016_metadata_v2')
    owner=setup(env);_,resolution,_,source,_=challenger_case();forecast=source.facts.facts.forecast
    from app.application.use_cases.planning_public import PublicPlanning
    env[5].app.state.planning_public=PublicPlanning(env[2],env[5].app.state.forecast_serving)
    encoded=serialize_prepared(forecast.retained)
    with Session(env[1]) as s:
        s.add(Store(id=resolution.configuration.store_id,name='Saved synthetic native fixture',timezone=forecast.retained.timezone,currency='VND',active=True));s.flush()
        s.add(StoreMembership(store_id=resolution.configuration.store_id,user_id=owner.user_id,role='OWNER',active=True))
        s.add_all(Product(id=p.product_id,store_id=forecast.store_id,name='Saved synthetic native Product',selling_unit=p.selling_unit,active=True) for p in forecast.retained.products)
        s.flush()
        s.add(ForecastRun(id=forecast.id,store_id=forecast.store_id,status='COMPLETED',
            training_start_date=forecast.training_start_date,training_end_date=forecast.training_end_date,
            forecast_start_date=forecast.forecast_start_date,forecast_end_date=forecast.forecast_end_date,
            model_type=forecast.model_type,model_version=forecast.model_version,artifact_key=forecast.artifact_key,
            input_fingerprint=encoded.digest,started_at=forecast.completed_at,completed_at=forecast.completed_at));s.flush()
        s.add(ForecastExecutionMetadata(forecast_run_id=forecast.id,store_id=forecast.store_id,details_json=forecast.execution.model_dump(mode='json')))
        s.add(ForecastRunInput(forecast_run_id=forecast.id,store_id=forecast.store_id,serialization_version=1,digest=encoded.digest,prepared_json=json.loads(encoded.canonical_json)))
        s.add_all(ForecastPrediction(**p.model_dump()) for p in forecast.predictions)
        s.commit()
    with Session(env[1]) as s:native_before=s.scalar(select(ForecastExecutionMetadata)).details_json
    command.upgrade(migration_config(),'head')
    with Session(env[1]) as s:assert s.scalar(select(ForecastExecutionMetadata)).details_json==native_before
    with pytest.raises(RuntimeError,match='Retain metadata/2 history'):
        command.downgrade(migration_config(),'0027_self_service_stores')
    assert versions(env[1])=={HEAD}
    record=create_challenger_run(env[1],owner.user_id)
    assert record.capture.forecast_provenance.execution.schema_version==2
    assert record.capture.source.facts.forecast.retained.schema_version==3
    wire=login(env).json()['data'];headers={'Origin':'https://fe.example.test','X-CSRF-Token':wire['session']['csrf_token']}
    proof=summary_chat(env,record,headers,monkeypatch)
    with Session(env[1]) as s:
        before=s.scalar(select(ForecastExecutionMetadata)).details_json
    def assistant_rows():
        with env[1].connect() as c:
            return {table:list(c.execute(text('SELECT * FROM '+table))) for table in
                ('plan_summary_generations','plan_summary_receipts','assistant_messages','chat_generations')}
    receipts=assistant_rows()
    # Traverse only the merge revision to the two original heads, preserving rows.
    command.downgrade(migration_config(),'0030_conversational_chat')
    assert versions(env[1])=={'0030_conversational_chat','f4_20261016_metadata_v2'}
    command.upgrade(migration_config(),'head')
    with Session(env[1]) as s:assert s.scalar(select(ForecastExecutionMetadata)).details_json==before
    assert assistant_rows()==receipts
    with pytest.raises((RuntimeError,DBAPIError),match='Retain metadata/2|Retained|retained|evidence|history'):
        command.downgrade(migration_config(),'0027_self_service_stores')
    assert versions(env[1])=={HEAD}
    assert assistant_rows()==receipts
    proof.update(mode='SAVED_NATIVE_FORECAST_NEW_SYNTHETIC_HOST_PLANNING_NO_NATIVE_INFERENCE',metadata2_preserved=True,schema3_preserved=True,migration_guard_rejected=True)
    (ROOT/'metadata2-assistant.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')


def test_assistant_parent_upgrade_preserves_real_receipts(env):
    command.downgrade(migration_config(),'base')
    command.upgrade(migration_config(),'0030_conversational_chat')
    state,record,summary,headers,body,path=assistant.__wrapped__(env)
    response=state[5].post(path,headers=headers,json=body)
    assert response.status_code==200,response.text
    from app.application.use_cases.assistant_chat import AssistantChat
    state[5].app.state.assistant_chat=AssistantChat(summary.planning)
    key={**headers,'Idempotency-Key':str(uuid4())}
    request={**body,'question':'Chi phí?','ingredient_id':None,'history':[]}
    message_path=path.rsplit('/',1)[0]+'/messages'
    message=state[5].post(message_path,headers=key,json=request)
    assert message.status_code==200,message.text
    with state[1].connect() as c:
        before={t:list(c.execute(text('SELECT * FROM '+t))) for t in
            ('plan_summary_generations','plan_summary_receipts','assistant_messages','chat_generations')}
    command.upgrade(migration_config(),'head');assert versions(state[1])=={HEAD}
    with state[1].connect() as c:
        assert all(list(c.execute(text('SELECT * FROM '+t)))==rows for t,rows in before.items())
    assert state[5].post(path,headers=headers,json=body).json()['data']==response.json()['data']
    assert state[5].post(message_path,headers=key,json=request).json()['data']==message.json()['data']
