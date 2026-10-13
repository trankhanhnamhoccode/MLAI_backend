"""Disposable PostgreSQL evidence: scoped read-only MVCC and detached pipeline."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError

from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.database.decision_capture import PostgresDecisionSnapshotSource
from app.application.contracts.decision_capture import OperationalDecisionInput
from app.application.use_cases.decision_capture import capture_decision
from app.application.use_cases.decision_pipeline import execute_operational_pipeline
from app.application.forecast_serialization import serialize_prepared
from app.infrastructure.procurement_milp import NativeSearch
from app.models import (
    Store, Product, Ingredient, Recipe, RecipeLine, InventoryLot, Supplier, SupplierTerm,
    ForecastRun, ForecastPrediction, ForecastRunInput, ForecastExecutionMetadata, BusinessConstraint, DecisionRun,
)
from scripts.decision_capture_demo_cases import synthetic_case


@pytest.fixture
def setup(database_settings):
    engine = create_database_engine(database_settings)
    request, facts = synthetic_case()
    with Session(engine) as session, session.begin():
        session.add(Store(id=request.store_id, name='S352 SYNTHETIC', timezone='UTC', currency='VND'))
        session.flush()
        session.add_all([Product(id=p.product_id,store_id=p.store_id,name='Synthetic product',
            sku=p.sku,selling_unit=p.selling_unit) for p in facts.products])
        session.add_all([Ingredient(id=i.ingredient_id,store_id=i.store_id,name='Synthetic ingredient',
            base_unit=i.unit,expiry_tracking=i.expiry_tracking) for i in facts.ingredients])
        session.add_all([Supplier(id=s,store_id=request.store_id,name='Synthetic supplier') for s in
                        {t.supplier_id for t in facts.supplier_terms}])
        session.flush()
        for recipe in facts.recipes:
            session.add(Recipe(**recipe.model_dump(exclude={'lines'})))
            session.flush()
            session.add_all([RecipeLine(id=uuid4(),store_id=request.store_id,recipe_id=recipe.id,
                **line.model_dump()) for line in recipe.lines])
        session.add_all([SupplierTerm(**t.model_dump()) for t in facts.supplier_terms])
        session.add_all([InventoryLot(**l.model_dump()) for l in facts.lots])
        f=facts.forecast
        session.add(ForecastRun(id=f.id,store_id=f.store_id,status=f.status,training_start_date=f.training_start_date,
            training_end_date=f.training_end_date,forecast_start_date=f.forecast_start_date,
            forecast_end_date=f.forecast_end_date,model_type=f.model_type,model_version=f.model_version,
            started_at=f.completed_at-timedelta(hours=1),completed_at=f.completed_at,input_fingerprint=f.input_fingerprint))
        session.flush()
        encoded=serialize_prepared(f.retained)
        import json
        session.add(ForecastRunInput(forecast_run_id=f.id,store_id=f.store_id,prepared_json=json.loads(encoded.canonical_json),
            serialization_version=encoded.serialization_version,digest=encoded.digest))
        session.add_all([ForecastPrediction(**p.model_dump()) for p in f.predictions])
    try:
        yield engine,request,facts
    finally:
        engine.dispose()


def codes(result): return {p.code for p in result.problems}


def test_real_repositories_pipeline_and_fresh_session_state(setup):
    engine,request,facts=setup
    # Real PostgreSQL metadata capture: synthetic persisted diagnostics, not a
    # claim that the forecasting producer selected a superior model.
    with Session(engine) as writer, writer.begin():
        writer.add(ForecastExecutionMetadata(forecast_run_id=request.forecast_run_id,store_id=request.store_id,
            details_json=dict(schema_version=1,selection_reason='BASELINE_SELECTED',warnings=[
                dict(code='BASELINE_FALLBACK',severity='WARNING',field='model_type',entity='forecast_run',
                     impact='SYNTHETIC comparison has not proven trained superiority')])))
    calls=[]
    def factory(*args):
        assert engine.pool.checkedout()==0
        calls.append(True)
        return NativeSearch(*args)
    result=execute_operational_pipeline(request,PostgresDecisionSnapshotSource(engine),factory,lambda:facts.captured_at)
    assert result.status=='COMPUTED' and len(calls)==3
    assert result.procurement.strategies[0].best_target_met.counts==(1,)
    assert result.comparison.options[0].outlay.total.decimal_view==Decimal('.1')
    assert result.capture.prepared.forecast.input_fingerprint==facts.forecast.input_fingerprint
    assert result.capture.forecast_provenance.retained_input_digest==facts.forecast.retained_digest
    assert result.capture.forecast_provenance.execution.selection_reason=='BASELINE_SELECTED'
    assert result.capture.prepared.forecast.warnings[0].code=='BASELINE_FALLBACK'
    assert result.procurement.input.prepared.forecast.warnings==result.capture.prepared.forecast.warnings
    assert result.capture.request.procurement.provenance==request.procurement.provenance
    assert any(r.entity=='forecast_run' and r.entity_id==request.forecast_run_id
               for r in result.comparison.options[0].provenance)
    assert result.decision_readiness=='NOT_ASSESSED'
    assert any(t.entity=='inventory_lot' and t.kind=='ROW_UPDATED_AT' for t in result.capture.source_times)
    assert engine.pool.checkedout()==0
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==1
        assert fresh.get(ForecastRun,request.forecast_run_id).status=='COMPLETED'
        assert not fresh.scalars(select(DecisionRun)).all()
        assert len(fresh.scalars(select(ForecastPrediction)).all())==7


def test_one_repeatable_read_snapshot_under_concurrent_changes(setup):
    engine,request,facts=setup
    fired=False
    def mutate_after_first_read(connection,cursor,statement,parameters,context,executemany):
        nonlocal fired
        if not fired and statement.lstrip().startswith('SELECT stores.'):
            fired=True
            assert connection.scalar(text('SHOW transaction_isolation'))=='repeatable read'
            assert connection.scalar(text('SHOW transaction_read_only'))=='on'
            with Session(engine) as writer, writer.begin():
                lot=writer.get(InventoryLot,facts.lots[0].id)
                lot.on_hand_quantity=Decimal(99)
                writer.get(Product,facts.products[0].product_id).selling_unit='changed-unit'
    event.listen(engine,'after_cursor_execute',mutate_after_first_read)
    try:
        capture=capture_decision(request,PostgresDecisionSnapshotSource(engine),lambda:facts.captured_at)
    finally:
        event.remove(engine,'after_cursor_execute',mutate_after_first_read)
    assert fired and capture.status=='CAPTURED'
    assert capture.prepared.lots[0].on_hand_quantity==1
    assert capture.prepared.products[0].selling_unit=='cup'
    assert engine.pool.checkedout()==0
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==99
        assert fresh.get(Product,facts.products[0].product_id).selling_unit=='changed-unit'
    saved=capture.model_dump()
    with Session(engine) as after_capture, after_capture.begin():
        after_capture.get(InventoryLot,facts.lots[0].id).on_hand_quantity=77
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==77
    assert capture.model_dump()==saved
    assert capture.prepared.lots[0].on_hand_quantity==1


def test_capture_readonly_and_does_not_touch_caller_transaction(setup):
    engine,request,facts=setup
    source=PostgresDecisionSnapshotSource(engine)
    from app.repositories.catalog import CatalogRepository
    original=CatalogRepository.list_ingredients
    def attempt_write(repo,store_id):
        repo._session.execute(text("UPDATE stores SET name='forbidden' WHERE id=:id"),{'id':store_id})
        return original(repo,store_id)
    with Session(engine) as caller:
        caller.begin()
        caller.get(Store,request.store_id).name='caller uncommitted'
        success=capture_decision(request,source,lambda:facts.captured_at)
        assert success.status=='CAPTURED'
        assert caller.in_transaction() and caller.dirty
        # Only the caller's own checked-out connection remains, not the capture's.
        assert engine.pool.checkedout()==1
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(CatalogRepository,'list_ingredients',attempt_write)
            with pytest.raises(DBAPIError) as caught:
                capture_decision(request,source,lambda:facts.captured_at)
        assert caught.value.orig.sqlstate=='25006'
        assert caller.in_transaction() and caller.dirty
        caller.rollback()
    assert engine.pool.checkedout()==0
    with Session(engine) as fresh:
        assert fresh.get(Store,request.store_id).name=='S352 SYNTHETIC'


def test_actual_cross_store_uuid_and_forecast_lifecycle(setup):
    engine,request,facts=setup
    other,other_product=uuid4(),uuid4()
    other_ingredient,other_supplier,other_recipe,other_term,other_lot=(uuid4() for _ in range(5))
    with Session(engine) as writer,writer.begin():
        writer.add(Store(id=other,name='Other Store'));writer.flush()
        writer.add(Product(id=other_product,store_id=other,name='Other Product',selling_unit='cup'))
        writer.add(Ingredient(id=other_ingredient,store_id=other,name='Other Ingredient',base_unit='g'))
        writer.add(Supplier(id=other_supplier,store_id=other,name='Other Supplier'));writer.flush()
        writer.add(Recipe(id=other_recipe,store_id=other,product_id=other_product,version=1,
            effective_from=request.cutoff_date,yield_quantity=1));writer.flush()
        writer.add(RecipeLine(store_id=other,recipe_id=other_recipe,ingredient_id=other_ingredient,quantity=99,unit='g'))
        writer.add(SupplierTerm(id=other_term,store_id=other,supplier_id=other_supplier,ingredient_id=other_ingredient,
            unit='g',version=1,effective_from=request.cutoff_date,pack_size_base_quantity=99,minimum_order_packs=1,
            pack_cost=99,lead_time_days=0))
        writer.add(InventoryLot(id=other_lot,store_id=other,ingredient_id=other_ingredient,supplier_id=other_supplier,
            unit='g',on_hand_quantity=999,received_date=request.cutoff_date,unit_cost=1))
        writer.add(BusinessConstraint(store_id=other,scope_type='STORE',scope_id=None,constraint_type='BUDGET_LIMIT',
            numeric_value=777,unit='VND',version=1,effective_from=request.cutoff_date))
    source=PostgresDecisionSnapshotSource(engine)
    own=capture_decision(request,source,lambda:facts.captured_at)
    assert own.status=='CAPTURED'
    assert {i.ingredient_id for i in own.prepared.ingredients}=={facts.ingredients[0].ingredient_id}
    assert {l.id for l in own.prepared.lots}=={facts.lots[0].id}
    assert {t.id for t in own.prepared.supplier_terms}=={facts.supplier_terms[0].id}
    assert {r.id for r in own.prepared.recipes}=={facts.recipes[0].id}
    assert own.prepared.constraints==()  # Foreign budget cannot replace explicit local budget.
    foreign_offer=request.model_dump()
    foreign_offer['procurement']['offers'][0]['term_id']=other_term
    def forbidden(*args):
        pytest.fail('Cross-store SupplierTerm reference reached solver')
    blocked=execute_operational_pipeline(OperationalDecisionInput.model_validate(foreign_offer),source,forbidden,
                                         lambda:facts.captured_at)
    assert blocked.status=='COMPUTATION_BLOCKED' and blocked.capture.status=='CAPTURED'
    assert blocked.problems[0].code=='PROCUREMENT_CONFIGURATION_CONFLICT'
    wrong=OperationalDecisionInput.model_validate(request.model_dump()|{'product_ids':(other_product,)})
    assert 'PRODUCT_SCOPE_MISSING' in codes(capture_decision(wrong,source,lambda:facts.captured_at))
    wrong=OperationalDecisionInput.model_validate(request.model_dump()|{'store_id':other})
    assert 'FORECAST_NOT_FOUND_IN_SCOPE' in codes(capture_decision(wrong,source,lambda:facts.captured_at))
    with Session(engine) as writer,writer.begin():
        row=writer.get(ForecastRun,request.forecast_run_id)
        row.status='RUNNING';row.completed_at=None;row.input_fingerprint=None
    assert 'FORECAST_NOT_COMPLETED' in codes(capture_decision(request,source,lambda:facts.captured_at))


def test_dated_recipe_budget_capture_and_missing_balance(setup):
    engine,request,facts=setup
    switch=request.cutoff_date+timedelta(days=4)
    second_id=uuid4();budget_id=uuid4()
    with Session(engine) as writer,writer.begin():
        writer.get(Recipe,facts.recipes[0].id).effective_to=switch-timedelta(days=1)
        writer.flush()
        writer.add(Recipe(id=second_id,store_id=request.store_id,product_id=facts.products[0].product_id,
            version=2,effective_from=switch,yield_quantity=2,process_loss_rate=Decimal('.2')))
        writer.flush()
        writer.add(RecipeLine(store_id=request.store_id,recipe_id=second_id,ingredient_id=facts.ingredients[0].ingredient_id,
            quantity=4,unit='g'))
        writer.add(BusinessConstraint(id=budget_id,store_id=request.store_id,scope_type='STORE',scope_id=None,
            constraint_type='BUDGET_LIMIT',numeric_value=Decimal('5'),unit='VND',version=1,effective_from=request.cutoff_date))
        writer.get(InventoryLot,facts.lots[0].id).on_hand_quantity=0
    source=PostgresDecisionSnapshotSource(engine)
    r=request.model_dump();r['procurement']['budget']=None
    configured=OperationalDecisionInput.model_validate(r)
    result=execute_operational_pipeline(configured,source,NativeSearch,lambda:facts.captured_at)
    assert result.status=='COMPUTED' and len(result.capture.prepared.recipes)==2
    assert result.capture.prepared.lots[0].on_hand_quantity==0
    assert result.procurement.input.budget.provenance==f'DB business_constraints/{budget_id}/v1'
    assert result.bom.contributions[3].recipe_id==second_id
    with Session(engine) as writer,writer.begin():
        writer.delete(writer.get(InventoryLot,facts.lots[0].id))
    def forbidden(*args):
        pytest.fail('PostgreSQL missing-balance blocker reached solver')
    blocked=execute_operational_pipeline(configured,source,forbidden,lambda:facts.captured_at)
    assert blocked.status=='DATA_BLOCKED' and 'INVENTORY_BALANCE_MISSING' in codes(blocked.capture)
    assert blocked.procurement is None and blocked.comparison is None
    assert engine.pool.checkedout()==0


def test_missing_predictions_and_corrupted_retained_input_block(setup):
    engine,request,facts=setup;source=PostgresDecisionSnapshotSource(engine)
    with Session(engine) as writer,writer.begin():
        writer.delete(writer.get(ForecastPrediction,facts.forecast.predictions[0].id))
    assert 'FORECAST_COVERAGE_INVALID' in codes(capture_decision(request,source,lambda:facts.captured_at))
    with Session(engine) as writer,writer.begin():
        writer.get(ForecastRunInput,request.forecast_run_id).digest='0'*64
    result=capture_decision(request,source,lambda:facts.captured_at)
    assert result.status=='DATA_BLOCKED' and 'FORECAST_RETAINED_INTEGRITY_INVALID' in codes(result)
    def forbidden(*args):
        pytest.fail('PostgreSQL integrity blocker reached solver')
    pipeline=execute_operational_pipeline(request,source,forbidden,lambda:facts.captured_at)
    assert pipeline.status=='DATA_BLOCKED' and pipeline.capture.problems==result.problems
    assert pipeline.bom is None and pipeline.procurement is None
    assert engine.pool.checkedout()==0
