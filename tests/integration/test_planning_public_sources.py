"""S4.9 fee/source identity, partial scope, bounded retained-read measurements."""
from datetime import date
from uuid import uuid4,UUID
from time import perf_counter
from fractions import Fraction
from pathlib import Path
import json
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import event
from tests.integration.test_planning_public import flow,planning,config,env,submit,demand_and_offer,base
from tests.integration.test_readiness_context import declaration
from app.application.contracts import import_domains as d
from app.application.use_cases.operational_configuration import OperationalConfiguration
from app.models import SupplierTerm,Ingredient,RecipeLine,Product,Recipe,SalesDaily


@pytest.mark.parametrize('mode',['PER_OFFER','PER_SUPPLIER_ORDER','FOREIGN_SOURCE_SYSTEM','SUPPLIER_ALIASES','UNRESOLVED_COMPONENT'])
def test_actual_fee_coverage_basis_and_source_identity(flow,mode):
    c,ingredient,recipe,worker=flow;term=demand_and_offer(flow,system='other-system' if mode=='FOREIGN_SOURCE_SYSTEM' else 'synthetic')
    with Session(c[0][1]) as s:
        writer=OperationalConfiguration(s,c[1].store_id)
        supplier=s.get(SupplierTerm,term).supplier_id
        actual_mode='PER_SUPPLIER_ORDER' if mode=='SUPPLIER_ALIASES' else 'PER_OFFER' if mode in ('FOREIGN_SOURCE_SYSTEM','UNRESOLVED_COMPONENT') else mode
        if mode=='SUPPLIER_ALIASES':
            # Two source aliases resolve to the same canonical Supplier. They
            # are not two supplier orders or an ambiguous canonical identity.
            writer.supplier(d.SupplierSource(source_supplier_key='alias',name='Synthetic supplier',active=True),supplier,'synthetic',{},create=False)
        if actual_mode=='PER_SUPPLIER_ORDER':
            second=uuid4()
            s.add(Ingredient(id=second,store_id=c[1].store_id,name='Second ingredient',base_unit='ml',expiry_tracking=False,active=True));s.flush()
            s.add(RecipeLine(id=uuid4(),store_id=c[1].store_id,recipe_id=recipe,ingredient_id=second,quantity=1,unit='ml'));s.flush()
            writer.term(d.TermSource(source_term_key='second-offer',supplier_id=supplier,ingredient_id=second,effective_from=date(2026,10,1),effective_to=None,
                unit='ml',pack_size_base_quantity='5',pack_cost='2',currency='VND',minimum_order_packs=1,lead_time_days=0,shelf_life_days=None,
                active=True,maximum_order_base_quantity=None),uuid4(),'synthetic',{})
            declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=second,state='CONFIRMED_EMPTY',observed_at=c[0][4][0],
                covered_lot_ids=(),evidence_reference='second physical empty'),'second-inventory')
            declaration(s,c[1].store_id,d.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',effective_from=date(2026,10,10),effective_to=None,
                committed_inbound_state='CONFIRMED_NONE',no_additional_orders_state='CONFIRMED_NONE',capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),
                supplier_limit_state='EXPLICIT_NOT_CONFIGURED',supplier_limits=(),evidence_reference='fresh context'),'context')
        component=d.FeeComponent(component_key='payable',label='Generic payable fee',basis=actual_mode,
            source_term_key=('unresolved' if mode=='UNRESOLVED_COMPONENT' else 'offer') if actual_mode=='PER_OFFER' else None,source_supplier_key='supplier' if actual_mode=='PER_SUPPLIER_ORDER' else None,
            amount='5',condition='WHEN_ORDERED')
        components=(component,)
        if mode=='SUPPLIER_ALIASES':
            components+=(d.FeeComponent(component_key='additional',label='Another actual payable component',basis=actual_mode,
                source_term_key=None,source_supplier_key='alias',amount='2',condition='WHEN_ORDERED'),)
        writer.fee(d.FeeSource(source_fee_key='none',scope='STORE_PROCUREMENT',effective_from=date(2026,10,10),effective_to=None,
            mode=actual_mode,coverage='COMPLETE',currency='VND',components=components,covered_source_term_keys=('offer',) if actual_mode=='PER_OFFER' else (),
            covered_source_supplier_keys=('supplier','alias') if mode=='SUPPLIER_ALIASES' else ('supplier',) if actual_mode=='PER_SUPPLIER_ORDER' else (),evidence_reference='explicit full payable coverage',reason='new fee evidence'),uuid4(),'synthetic',{}, {})
        s.commit()
    from app.application.use_cases.readiness import ReadinessReads
    client=c[0][5]
    client.app.state.readiness=ReadinessReads(c[0][2],client.app.state.forecast_serving)
    readiness=client.get(base(c)+'/readiness',params={'actions':'planning','forecast_start_date':'2026-10-10'})
    assert readiness.status_code==200,readiness.text
    fee_unknown=any(b['code']=='PAYABLE_FEE_COVERAGE_UNKNOWN' for b in readiness.json()['data']['actions'][0]['blockers'])
    assert fee_unknown==(mode in ('FOREIGN_SOURCE_SYSTEM','UNRESOLVED_COMPONENT'))
    response=submit(c);record=worker.run_one()
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    result=read.json()['data']['result']
    if mode in ('FOREIGN_SOURCE_SYSTEM','UNRESOLVED_COMPONENT'):
        assert record.outcome=='computation_blocked' and result['winner_option_id'] is None
        assert any(p.code=='PAYABLE_FEE_COVERAGE_UNKNOWN' for p in record.capture.problems)
    else:
        assert record.outcome=='recommendation_available',record.error_code
        winner=next(o for o in result['options'] if o['option_id']==result['winner_option_id'])
        assert winner['costs']['payable_fees']['numerator']==('7' if mode=='SUPPLIER_ALIASES' else '5')
        assert winner['costs']['total']['numerator']==('35' if mode=='SUPPLIER_ALIASES' else '33' if mode=='PER_SUPPLIER_ORDER' else '19')
        assert winner['costs']['delivery_fees'] is None and winner['costs']['fee_classification']=='PAYABLE_FEE_TYPE_NOT_CAPTURED'
        assert any(w['code']=='DELIVERY_FEE_TAXONOMY_UNAVAILABLE' for w in winner['issues'])
        assert sum(len(p['payable_fee_components']) for p in winner['purchases'])==(0 if actual_mode=='PER_SUPPLIER_ORDER' else 1)
        assert len(winner['costs']['fee_components'])==1
    assert record.public_capture.operational_evidence.fees[0].payload.mode==actual_mode


def test_partial_scope_keeps_excluded_override_not_evaluated(flow):
    c,_,_,worker=flow;missing=uuid4()
    with Session(c[0][1]) as s:
        s.add(Product(id=missing,store_id=c[1].store_id,name='No history or recipe',selling_unit='portion',active=True));s.commit()
    body=dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='95',
        product_overrides=[dict(product_id=str(missing),min_fill_rate_percent='100')])],budget_limit=None))
    response=submit(c,body=body);record=worker.run_one()
    assert record.outcome=='recommendation_available',record.error_code
    read=c[0][5].get(response.headers['Location']);assert read.status_code==200,read.text
    data=read.json()['data']
    assert data['scope']['coverage_status']=='partial' and data['scope']['computed_count']==1
    assert data['scope']['excluded_products'][0]['requirement_overrides'][0]['status']=='NOT_EVALUATED'
    for option in data['result']['options']:
        excluded=next(a for a in option['requirements_assessment'] if a['product_id']==str(missing))
        assert excluded['status']=='NOT_EVALUATED' and excluded['shortfall'] is None
    assert data['result']['completeness']=='partial'


def test_retained_read_at_active_product_bound_with_actual_pipeline(flow):
    c,ingredient,_,worker=flow
    with Session(c[0][1]) as s:
        for i in range(49):
            product,recipe=uuid4(),uuid4()
            s.add(Product(id=product,store_id=c[1].store_id,name='Bounded Product '+str(i),selling_unit='cup',active=True));s.flush()
            s.add(Recipe(id=recipe,store_id=c[1].store_id,product_id=product,version=1,effective_from=date(2026,10,1),effective_to=None,
                yield_quantity=1,process_loss_rate=0));s.flush()
            s.add(RecipeLine(id=uuid4(),store_id=c[1].store_id,recipe_id=recipe,ingredient_id=ingredient,quantity=1,unit='ml'))
            s.add(SalesDaily(id=uuid4(),store_id=c[1].store_id,product_id=product,sales_date=date(2026,10,9),quantity=0))
        s.commit()
    response=submit(c);assert response.status_code==202,response.text
    started=perf_counter();record=worker.run_one();worker_seconds=perf_counter()-started
    assert record.status=='completed' and record.outcome=='recommendation_available',record.error_code
    assert len(record.capture.computed_product_ids)==50
    queries=[]
    def count(conn,cursor,statement,parameters,context,executemany):queries.append(statement)
    engine=c[0][5].app.state.planning_public.engine
    event.listen(engine,'before_cursor_execute',count);started=perf_counter()
    try:read=c[0][5].get(response.headers['Location'])
    finally:event.remove(engine,'before_cursor_execute',count)
    elapsed=perf_counter()-started
    assert read.status_code==200,read.text
    assert len(queries)<=12 and len(read.content)<1000000
    assert read.json()['data']['scope']['computed_count']==50
    assert len(read.json()['data']['result']['options'][0]['product_services'])==150
    path=Path('runtime/s49/retained_read_bound_measurement.json')
    path.write_text(json.dumps(dict(active_products=50,ingredients=1,offers=0,lots=0,queries=len(queries),bytes=len(read.content),
        http_seconds=elapsed,worker_seconds=worker_seconds,fixture='actual observed zeros; max Product count, not simultaneous maximum lots/offers or a latency SLA')),encoding='utf-8')
