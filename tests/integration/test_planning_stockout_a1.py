"""A1 causal evidence survives public Planning and fresh retained reads."""
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.contracts import import_domains as d
from app.application.planning_serialization import canonical_bytes
from app.models import ForecastRunInput, InventoryLot, PlanningRun, SalesDaily
from tests.integration.test_planning_public import flow, config, env, submit
from tests.integration.test_readiness_context import declaration


def test_stockout_capture_2_retained_planning_keeps_evidence_after_correction(flow):
    c, ingredient, _, worker = flow
    lot = uuid4()
    with Session(c[0][1]) as s, s.begin():
        sale = s.scalar(select(SalesDaily).where(SalesDaily.product_id == c[2]))
        sale.quantity = 2
        sale.is_stockout = True
        s.add_all([SalesDaily(store_id=c[1].store_id, product_id=c[2],
            sales_date=date(2026, 10, day), quantity=quantity, is_stockout=False)
            for day, quantity in ((6, 10), (7, 20), (8, 30))])
        s.add(InventoryLot(id=lot, store_id=c[1].store_id, ingredient_id=ingredient,
            received_date=date(2026, 10, 9), expiry_date=None,
            on_hand_quantity=1000, unit='ml', unit_cost=1))
        s.flush()
        declaration(s, c[1].store_id, d.SalesDeclaration(kind='SALES_COVERAGE',
            product_ids=(c[2],), from_date=date(2026, 10, 6), to_date=date(2026, 10, 9),
            state='COMPLETE', evidence_reference='Synthetic complete four-day observed report'), 'sales')
        declaration(s, c[1].store_id, d.InventoryDeclaration(kind='INVENTORY',
            ingredient_id=ingredient, state='COMPLETE_CURRENT_LOTS', observed_at=c[0][4][0],
            covered_lot_ids=(lot,), evidence_reference='Synthetic observed stock'), 'inventory')
    response = submit(c)
    assert response.status_code == 202, response.text
    record = worker.run_one()
    assert record.status == 'completed', record.error_code
    assert record.outcome == 'recommendation_available'
    fact = record.capture.source.facts.forecast
    prepared = fact.retained
    assert prepared.schema_version == 2 and prepared.demand_policy == 'causal_stockout_v1'
    derived = prepared.demand_records[-1]
    assert derived.observed_quantity == 2 and derived.demand_quantity == 20
    assert derived.is_stockout is True
    assert derived.evidence_dates == tuple(date(2026, 10, day) for day in (6, 7, 8))
    original = canonical_bytes(record)
    public = c[0][5].get(response.headers['Location'])
    assert public.status_code == 200, public.text
    with Session(c[0][1]) as fresh:
        retained = fresh.get(ForecastRunInput, fact.id)
        assert retained.prepared_json['schema_version'] == 2
        assert retained.digest == fact.retained_digest
        saved = fresh.get(PlanningRun, record.run_id)
        assert saved.record_json['capture']['source']['facts']['forecast']['retained']['demand_records'][-1]['evidence_dates'] == ['2026-10-06', '2026-10-07', '2026-10-08']
    with Session(c[0][1]) as writer, writer.begin():
        for sale in writer.scalars(select(SalesDaily)):
            sale.quantity = 999
            sale.is_stockout = None
    fresh_record = c[0][5].app.state.planning_public.runs.read(c[1].store_id, record.run_id).record
    assert canonical_bytes(fresh_record) == original
    after = c[0][5].get(response.headers['Location'])
    assert after.status_code == 200 and after.json()['data'] == public.json()['data']
