"""Real disposable PostgreSQL acceptance for /2; never SQLite/unit replacements."""
from sqlalchemy.engine import make_url
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import event, text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from tests.integration.test_decision_operational_capture import setup
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2
from app.infrastructure.database.decision_capture_v2 import PostgresDecisionSnapshotSourceV2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_operational_pipeline_v2
from app.models import Store,Product,InventoryLot,ForecastRun,ForecastRunInput,DecisionRun


def request():return synthetic_case_v2()[0]


def test_pg_v2_retained_forecast_to_winner_release_and_fresh_session(setup,monkeypatch, test_database_url):
    engine,old,facts=setup;r=request();checks=[]
    from app.application.use_cases import decision_pipeline_v2 as module
    original=module.expand_bom
    def bom(snapshot):
        assert engine.pool.checkedout()==0;checks.append('BOM');return original(snapshot)
    monkeypatch.setattr(module,'expand_bom',bom)
    def factory(*a):
        assert engine.pool.checkedout()==0;checks.append('solver');return NativeProductSearch(*a)
    result=execute_operational_pipeline_v2(r,PostgresDecisionSnapshotSourceV2(engine),factory,lambda:facts.captured_at)
    assert result.outcome=='RECOMMENDATION_AVAILABLE' and result.selection.winner_token
    assert result.capture.forecast_provenance.retained_input_digest==facts.forecast.retained_digest
    assert checks[0]=='BOM' and checks.count('solver')==3 and engine.pool.checkedout()==0
    with Session(engine) as fresh:
        assert fresh.scalar(text('select current_database()')) == make_url(test_database_url).database
        assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==1
        assert fresh.get(ForecastRun,r.forecast_run_id).status=='COMPLETED'
        assert not fresh.scalars(select(DecisionRun)).all()


def test_pg_v2_same_readonly_snapshot_under_second_connection_update(setup):
    engine,old,facts=setup;fired=False
    def change(conn,cursor,statement,params,context,many):
        nonlocal fired
        if not fired and statement.lstrip().startswith('SELECT stores.'):
            fired=True
            assert conn.scalar(text('SHOW transaction_isolation'))=='repeatable read'
            assert conn.scalar(text('SHOW transaction_read_only'))=='on'
            with Session(engine) as writer,writer.begin():
                writer.get(InventoryLot,facts.lots[0].id).on_hand_quantity=99
                writer.get(Product,facts.products[0].product_id).name='Changed after first read'
    event.listen(engine,'after_cursor_execute',change)
    try:c=capture_decision_v2(request(),PostgresDecisionSnapshotSourceV2(engine),lambda:facts.captured_at)
    finally:event.remove(engine,'after_cursor_execute',change)
    assert fired and c.status=='CAPTURED' and c.prepared.lots[0].on_hand_quantity==1
    assert c.menu[0].name=='Synthetic product'
    assert engine.pool.checkedout()==0
    with Session(engine) as fresh:
        assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==99
        assert fresh.get(Product,facts.products[0].product_id).name=='Changed after first read'


def test_pg_v2_owned_session_keeps_caller_and_forbids_write(setup,monkeypatch):
    engine,old,facts=setup
    from app.repositories.catalog import CatalogRepository
    original=CatalogRepository.list_products
    def illegal(repo,store):
        repo._session.execute(text("UPDATE stores SET name='forbidden' WHERE id=:id"),{'id':store})
        return original(repo,store)
    with Session(engine) as caller:
        caller.begin();caller.get(Store,old.store_id).name='caller WIP'
        c=capture_decision_v2(request(),PostgresDecisionSnapshotSourceV2(engine),lambda:facts.captured_at)
        assert c.status=='CAPTURED' and caller.in_transaction() and caller.dirty
        assert engine.pool.checkedout()==1
        monkeypatch.setattr(CatalogRepository,'list_products',illegal)
        with pytest.raises(DBAPIError) as error:
            capture_decision_v2(request(),PostgresDecisionSnapshotSourceV2(engine),lambda:facts.captured_at)
        assert error.value.orig.sqlstate=='25006' and caller.in_transaction() and caller.dirty
        caller.rollback()
    assert engine.pool.checkedout()==0
    with Session(engine) as fresh:assert fresh.get(Store,old.store_id).name=='S352 SYNTHETIC'


def test_pg_v2_menu_partial_scope_and_foreign_override_rejection(setup):
    engine,old,facts=setup;extra=uuid4();other=uuid4();foreign=uuid4()
    with Session(engine) as writer,writer.begin():
        writer.add(Store(id=other,name='Other Store'));writer.flush()
        writer.add(Product(id=extra,store_id=old.store_id,name='Active without recipe/forecast',selling_unit='piece'))
        writer.add(Product(id=foreign,store_id=other,name='Foreign',selling_unit='cup'))
    r=request().model_dump();r['requirements']['paths'][0]['overrides']=[dict(product_id=extra,target='1')]
    result=execute_operational_pipeline_v2(OperationalDecisionInputV2.model_validate(r),PostgresDecisionSnapshotSourceV2(engine),NativeProductSearch,lambda:facts.captured_at)
    assert result.outcome=='RECOMMENDATION_AVAILABLE' and len(result.capture.menu)==2
    assert result.capture.exclusions[0].product_id==extra
    assert result.capture.override_assessments[0].status=='NOT_EVALUATED'
    assert foreign not in {p.product_id for p in result.capture.menu}
    r['requirements']['paths'][0]['overrides'][0]['product_id']=foreign
    with pytest.raises(ValueError,match='override'):
        capture_decision_v2(OperationalDecisionInputV2.model_validate(r),PostgresDecisionSnapshotSourceV2(engine),lambda:facts.captured_at)
    assert engine.pool.checkedout()==0


def test_pg_v2_post_capture_mutation_does_not_change_detached_computation(setup):
    engine,old,facts=setup;source=PostgresDecisionSnapshotSourceV2(engine);captured=[]
    class MutateAfterRead:
        def read(self,r,clock):
            value=source.read(r,clock);assert engine.pool.checkedout()==0;captured.append(value.model_dump())
            with Session(engine) as writer,writer.begin():
                writer.get(InventoryLot,facts.lots[0].id).on_hand_quantity=Decimal(100)
            return value
    result=execute_operational_pipeline_v2(request(),MutateAfterRead(),NativeProductSearch,lambda:facts.captured_at)
    assert result.capture.source.model_dump()==captured[0]
    assert result.capture.prepared.lots[0].on_hand_quantity==1
    assert result.outcome=='RECOMMENDATION_AVAILABLE' and engine.pool.checkedout()==0
    with Session(engine) as fresh:assert fresh.get(InventoryLot,facts.lots[0].id).on_hand_quantity==100


def test_pg_v2_corrupted_retained_integrity_keeps_blocker_and_releases(setup):
    engine,old,facts=setup
    with Session(engine) as writer,writer.begin():
        writer.get(ForecastRunInput,old.forecast_run_id).digest='0'*64
    result=execute_operational_pipeline_v2(request(),PostgresDecisionSnapshotSourceV2(engine),lambda *a:pytest.fail('must not solve'),lambda:facts.captured_at)
    assert result.outcome=='CAPTURE_BLOCKED' and result.capture.captured_at==facts.captured_at
    assert 'FORECAST_RETAINED_INTEGRITY_INVALID' in {p.code for p in result.problems}
    assert result.bom is None and result.selection is None and engine.pool.checkedout()==0
