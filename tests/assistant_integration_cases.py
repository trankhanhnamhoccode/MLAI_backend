"""Saved synthetic native forecast -> new host engine/capture/persistence fixture.

No forecast inference/artifact load/training; output predictions remain verbatim.
Only new synthetic operational recipe/stock scope is authored for this Run.
"""
from datetime import date,datetime,timedelta
import json
from pathlib import Path
from uuid import UUID,uuid4
from scripts.planning_verification_cases import small_case
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.decision_capture_v2 import OperationalFactsV2
from app.application.forecast_serialization import serialize_prepared
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import prepare_planning_pipeline
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
from app.application.use_cases.planning_run import PlanningRunUseCases
from app.infrastructure.procurement_milp_v2 import NativeProductSearch


def challenger_case():
    fixture=json.loads(Path('tests/fixtures/assistant_integration/retained-challenger.json').read_text(encoding='utf8'))
    value,output=fixture['input'],fixture['output']
    prepared=PreparedForecastInput(schema_version=3,demand_policy='engine_native_reconstruction_v1',request=value['request'],
        timezone=value['timezone'],products=value['products'],forecast_dates=value['forecast_dates'],
        observations=tuple({k:v for k,v in o.items() if k not in ('source','available_at')} for o in value['observations']))
    encoded=serialize_prepared(prepared)
    details=ExecutionDetails(schema_version=2,selection_reason='CHALLENGER_TEST_SELECTED',
        candidate_artifact_identity=value['artifact_identity'],challenger_evidence=dict(input=value,output=output,
            cache_identity=challenger_digest('cache',dict(input=value,runtime=output['runtime']))))
    request,config,declarations,source=small_case('stock')
    config=json.loads(json.dumps(config,default=lambda o:o.model_dump(mode='json') if hasattr(o,'model_dump') else str(o)))
    data=source.model_dump(mode='json');decl=declarations.model_dump(mode='json')
    store=value['request']['store_id'];product=value['products'][0]['product_id']
    start=date.fromisoformat(value['forecast_dates'][0]);shift=start-date(2026,10,8)
    def bind(v):
        if isinstance(v,dict):return {k:bind(x) for k,x in v.items()}
        if isinstance(v,list):return [bind(x) for x in v]
        if isinstance(v,str):
            if v=='00000000-0000-0000-0000-000000000001':return store
            if v=='00000000-0000-0000-0000-000000000064':return product
            try:
                if len(v)==10:return (date.fromisoformat(v)+shift).isoformat()
                if v.startswith('2026-10-'):return (datetime.fromisoformat(v.replace('Z','+00:00'))+shift).isoformat()
            except ValueError:pass
        return v
    config,data,decl=bind(config),bind(data),bind(decl)
    # One Product and matching recipe; ingredients/stock remain explicit synthetic facts.
    config['products']=config['products'][:1];config['timezone']=value['timezone']
    data['catalog']=data['catalog'][:1];data['facts']['products']=data['facts']['products'][:1]
    data['facts']['recipes']=data['facts']['recipes'][:1]
    at=datetime.fromisoformat(value['inference_at'].replace('Z','+00:00'))+timedelta(seconds=1)
    data['facts']['captured_at']=at.isoformat();data['facts']['store']['timezone']=value['timezone']
    run=UUID(int=2);forecast=output['forecast']
    data['facts']['forecast']=dict(id=str(run),store_id=store,status='COMPLETED',
        training_start_date=value['request']['history_start_date'],training_end_date=value['request']['cutoff_date'],
        forecast_start_date=value['forecast_dates'][0],forecast_end_date=value['forecast_dates'][-1],
        input_fingerprint=encoded.digest,retained_digest=encoded.digest,retained=prepared.model_dump(mode='json'),
        model_type=forecast['model_type'],model_version=forecast['model_version'],artifact_key=forecast['artifact_identity'],
        completed_at=value['inference_at'],execution=details.model_dump(mode='json'),
        predictions=[{**p,'id':str(uuid4()),'store_id':store,'forecast_run_id':str(run)} for p in forecast['predictions']])
    request['forecast_start_date']=start.isoformat()
    facts=OperationalFactsV2.model_validate(data)
    resolved=resolve_planning_setup(request,config);assert resolved.status=='RESOLVED'
    # Retain the original typed declarations class, with unchanged explicit source policy.
    declarations=type(declarations).model_validate(decl)
    return request,resolved.resolution,declarations,SyntheticSnapshotSourceV2(facts),fixture


def create_challenger_run(engine,actor_id):
    request,resolution,declarations,source,fixture=challenger_case()
    at=source.facts.facts.captured_at;service=PlanningRunUseCases(engine,clock=lambda:at)
    from tests.assistant_cases import realistic_record
    from app.application.contracts.planning_public import ForecastView
    from app.application.contracts.planning_public_evidence import PublicPlanningAcceptance
    from app.application.contracts.model_serving import ForecastIdentity
    from app.application.contracts.planning_challenger import ChallengerTestPin
    from app.application.import_identity import content_digest
    metadata=realistic_record(actor_id=actor_id)
    pin=ChallengerTestPin.model_validate(fixture['acceptance_pin'])
    acceptance=PublicPlanningAcceptance(schema_version='planning_public_acceptance/2',challenger_test=pin,
        session_digest='0'*64,authorization_version='L5-synthetic-archival-capture',
        serving=metadata.public_acceptance.serving,receipt_warnings=())
    forecast_view=ForecastView.model_validate({**fixture['forecast_view'],
        'forecast_run_id':str(source.facts.facts.forecast.id),
        'input_digest':source.facts.facts.forecast.retained_digest})
    fact=source.facts.facts.forecast
    identity=ForecastIdentity(prepared_digest=fact.retained_digest,source_digest=challenger_digest('input',pin.input),
        serving_version=content_digest(pin.model_dump(mode='json')),model_type=fact.model_type,model_version=fact.model_version,
        artifact_identity=fact.artifact_key,candidate_artifact_identity=fact.artifact_key,selection_reason='CHALLENGER_TEST_SELECTED',
        features_version=1,postprocessing_version=1,dependency_versions=(),configuration_dependency_versions=(),
        training_start_date=forecast_view.training_start_date,training_end_date=forecast_view.training_end_date)
    public_capture=metadata.public_capture.model_copy(update={'forecast':forecast_view,'identity':identity,'ingredient_labels':None})
    record=service.accept(actor_id,resolution.configuration.store_id,str(uuid4()),request,resolution,
        public_metadata=lambda session,resolved:acceptance)
    claimed=service.claim(record.store_id,record.run_id)
    capture=capture_decision_v2(prepare_planning_pipeline(resolution,declarations),source,lambda:at)
    assert capture.prepared is not None,capture
    record=service.retain(record.store_id,record.run_id,claimed.claim,declarations,capture,public_capture=public_capture)
    result=execute_captured_pipeline_v2(capture,NativeProductSearch)
    record=service.finalize(record.store_id,record.run_id,claimed.claim,result)
    assert record.status=='completed'
    return service.read(record.store_id,record.run_id).record
