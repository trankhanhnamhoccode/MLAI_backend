"""Internal S4.8 baseline/reuse/capture seams with actual guarded PostgreSQL."""
from datetime import date
from dataclasses import replace
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_readiness_context import readiness,config,env,known_facts,configure_baseline
from tests.integration.test_auth_public import KEY
from app.application.use_cases.model_serving import ModelServingOperator
from app.application.contracts.model_serving import OperatorConfigurationCommand,ServingRecord,ServingPolicy
from app.application.contracts.auth import AuthError
from app.models import SalesDaily,Product,InventoryLot,ForecastRun,ForecastPrediction
from app.models.model_serving import ModelServingConfiguration,ForecastServingIdentity
from app.models.planning_configuration import PlanningConfigurationEvent
from app.infrastructure.storage.forecast_artifacts import ArtifactError
from app.application.forecast_serialization import RetainedInputError


def test_operator_explicit_config_cas_noop_and_no_automatic_selection(readiness):
    c=readiness;svc=c[0][5].app.state.forecast_serving
    with pytest.raises(AuthError,match='MODEL_CONFIGURATION_UNKNOWN'):svc.prepare(c[1].store_id,date(2026,10,10))
    operator=ModelServingOperator(c[0][1],c[0][0],lambda:c[0][4][0])
    command=OperatorConfigurationCommand(store_id=c[1].store_id,action='BASELINE',expected_version=None,evidence_reference='approved baseline')
    first=operator.configure(command,'support-test',KEY)
    with pytest.raises(AuthError,match='CONFIGURATION_VERSION_CHANGED'):operator.configure(command,'support-test',KEY)
    assert operator.configure(command.model_copy(update={'expected_version':first.version}),'support-test',KEY)==first
    with Session(c[0][1]) as s:
        assert s.get(ModelServingConfiguration,c[1].store_id).version==first.version
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationEvent))==1


def test_exact_reuse_keeps_identity_for_budget_stock_recipe_and_retail_price_changes(readiness):
    c=readiness;ingredient,recipe=known_facts(c);svc=c[0][5].app.state.forecast_serving
    prep=svc.prepare(c[1].store_id,date(2026,10,10));first=svc.serve(prep)
    assert not first.reused and len(first.run.predictions)==7
    assert all(p.p50==0 for p in first.run.predictions)
    from app.models import Recipe
    from app.models.planning_configuration import PlanningBudget
    with Session(c[0][1]) as s:
        s.get(Product,c[2]).price=99
        s.get(Recipe,recipe).effective_to=date(2026,10,13)
        s.get(PlanningBudget,c[1].store_id).amount='0'
        s.add(InventoryLot(id=uuid4(),store_id=c[1].store_id,ingredient_id=ingredient,received_date=None,expiry_date=None,on_hand_quantity=5,unit='ml'))
        s.commit()
    next_prep=svc.prepare(c[1].store_id,date(2026,10,10))
    second=svc.serve(next_prep)
    assert second.reused and second.run.id==first.run.id and second.identity==first.identity
    capture=svc.capture_operational_preparation(second,next_prep)
    assert capture.facts.cap.amount=='0' and capture.facts.snapshot['inventory_lots'][0]['on_hand_quantity']=='5'
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ForecastRun))==1
        assert s.scalar(select(func.count()).select_from(ForecastServingIdentity))==1


def test_sales_correction_and_model_version_break_reuse(readiness):
    c=readiness;known_facts(c);svc=c[0][5].app.state.forecast_serving
    first=svc.serve(svc.prepare(c[1].store_id,date(2026,10,10)))
    with Session(c[0][1]) as s:
        s.scalar(select(SalesDaily)).quantity=12;s.commit()
    second=svc.serve(svc.prepare(c[1].store_id,date(2026,10,10)))
    assert not second.reused and second.run.id!=first.run.id
    with Session(c[0][1]) as s:
        s.get(ModelServingConfiguration,c[1].store_id).version=str(uuid4());s.commit()
    third=svc.serve(svc.prepare(c[1].store_id,date(2026,10,10)))
    assert not third.reused and third.identity.prepared_digest==second.identity.prepared_digest
    assert third.identity.serving_version!=second.identity.serving_version


def test_retained_predictions_corrupt_not_reused_or_silently_replaced(readiness):
    c=readiness;known_facts(c);svc=c[0][5].app.state.forecast_serving
    prep=svc.prepare(c[1].store_id,date(2026,10,10));first=svc.serve(prep)
    with Session(c[0][1]) as s:
        row=s.scalar(select(ForecastPrediction).where(ForecastPrediction.forecast_run_id==first.run.id));s.delete(row);s.commit()
    with pytest.raises(ValueError):svc.serve(prep)
    with Session(c[0][1]) as s:assert s.scalar(select(func.count()).select_from(ForecastRun))==1


def test_recognized_absent_artifact_fallback_and_corrupt_artifact_failure(readiness,tmp_path):
    c=readiness;known_facts(c);svc=c[0][5].app.state.forecast_serving
    from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
    svc.execution.artifacts=ForecastArtifactStore(tmp_path)
    prep=svc.prepare(c[1].store_id,date(2026,10,10))
    candidate='a'*64
    policy=ServingPolicy(mode='TRAINED',artifact_identity=candidate,fallback_policy='ADR015_RECOGNIZED_ONLY',dependency_versions=())
    internal=replace(prep,serving=ServingRecord(version='internal-recognized-fallback-test',policy=policy))
    choice=svc.choice(internal.prepared,internal.serving)
    assert choice.artifact is None and choice.details.selection_reason=='ARTIFACT_MISSING'
    served=svc.serve(internal)
    assert served.run.model_type=='historical_quantile_baseline' and served.identity.candidate_artifact_identity==candidate
    directory=tmp_path/candidate;directory.mkdir();(directory/'manifest.json').write_text('{bad')
    assessment=svc.assess(internal.prepared,internal.serving)
    assert assessment.failure_kind=='ARTIFACT_INVALID'
    assert assessment.blockers[0].code=='MODEL_ARTIFACT_INVALID'
    with pytest.raises(ArtifactError):svc.serve(internal)


def test_real_source_change_between_prepare_capture_bounded_retry_and_sessions_closed(readiness,monkeypatch):
    c=readiness;known_facts(c);svc=c[0][5].app.state.forecast_serving
    attempts=[]
    def once(served,prep):
        assert c[0][1].pool.checkedout()==0
        attempts.append(served.run.id)
        if len(attempts)==1:
            with Session(c[0][1]) as s:s.scalar(select(SalesDaily)).quantity=3;s.commit()
        return svc.capture_operational_preparation(served,prep)
    served,captured=svc.prepare_serve_capture(c[1].store_id,date(2026,10,10),once)
    assert len(attempts)==2 and all(p.p50==3 for p in served.run.predictions)
    assert captured.prepared_digest==served.identity.prepared_digest
    count=[0]
    def forever(served,prep):
        count[0]+=1
        with Session(c[0][1]) as s:s.scalar(select(SalesDaily)).quantity=count[0]+10;s.commit()
        return svc.capture_operational_preparation(served,prep)
    with pytest.raises(AuthError,match='INPUT_CHANGED_DURING_CAPTURE'):
        svc.prepare_serve_capture(c[1].store_id,date(2026,10,10),forever)
    assert count[0]==3
