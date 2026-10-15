"""D3 portable HTTP/PG acceptance, only on the guarded readiness test target."""
from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_planning_public import flow, config, env, demand_and_offer, submit
from app.models import PlanningRun, InventoryLot, InventoryMovement, SupplierTerm, Ingredient
from app.application.contracts import import_domains as d
from app.application.use_cases.operational_configuration import OperationalConfiguration
from tests.integration.test_readiness_context import declaration


def test_unbounded_zero_cost_offer_does_not_block_finite_alternative(flow):
    c, ingredient, _, worker = flow
    omitted = demand_and_offer(flow, cost='0', system='omitted-source')
    eligible = demand_and_offer(flow, cost='2', system='eligible-source')
    from tests.integration.test_contextual_readiness import contextual
    assert contextual(flow)['readiness']['can_generate']
    accepted = submit(c)
    assert accepted.status_code == 202, accepted.text
    record = worker.run_one()
    assert record.outcome == 'recommendation_available', [p.code for p in record.capture.problems]
    response = c[0][5].get(accepted.headers['Location'])
    assert response.status_code == 200, response.text
    result = response.json()['data']['result']
    winner = next(o for o in result['options'] if o['option_id'] == result['winner_option_id'])
    assert {p['supplier_term_id'] for p in winner['purchases']} == {str(eligible)}
    assert winner['costs']['total']['numerator'] == '14'
    warning=next(w for w in result['warnings'] if w['code']=='OFFER_OMITTED')
    assert warning['details']['entity_id']==str(omitted)
    assert warning['details']['classification']=='OFFER_BOUND_UNKNOWN'
    assert warning['details']['proof_scope']=='CAPTURED_ELIGIBLE_OFFERS_ONLY'
    assert warning['details']['source_reference']==f'SupplierTerm/{omitted}/version/1'
    assert warning['details']['source_version']==1
    assert warning['details']['suggested_action']
    detail=c[0][5].get(accepted.headers['Location']+'/ingredients/'+str(ingredient))
    assert detail.status_code==200,detail.text
    assert any(i['code']=='OFFER_OMITTED' and i['details']['entity_id']==str(omitted)
               for i in detail.json()['data']['issues'])
    explanation=c[0][5].get(accepted.headers['Location']+'/explanation')
    assert explanation.status_code==200,explanation.text
    assert len([w for w in explanation.json()['data']['warnings'] if w['code']=='OFFER_OMITTED'])==1
    with Session(c[0][1]) as fresh:
        row = fresh.scalar(select(PlanningRun))
        assert str(omitted) in str(row.record_json)
        assert row.record_json['public_acceptance']['offer_eligibility_policy']=='offer_eligibility/1'
        admission=row.record_json['declarations']['offer_admission']
        assert admission['proof_scope']=='CAPTURED_ELIGIBLE_OFFERS_ONLY'
        assert admission['omissions'][0]['term_id']==str(omitted)
        assert admission['omissions'][0]['version']==1
        assert {o['term_id'] for o in row.record_json['capture']['procurement_input']['offers']}=={str(eligible)}
        # Retain the exact Run while the live offer changes; read must never reclassify it.
        before=row.record_json
        fresh.get(SupplierTerm,omitted).pack_cost=99
        fresh.commit()
    assert c[0][5].get(accepted.headers['Location']).json()==response.json()
    assert c[0][5].get(accepted.headers['Location']+'/explanation').json()['data']==explanation.json()['data']
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(PlanningRun)).record_json==before


def physical_stock(flow, quantity):
    c,ingredient,_,_=flow
    lot=uuid4()
    with Session(c[0][1]) as s:
        s.add(InventoryLot(id=lot,store_id=c[1].store_id,ingredient_id=ingredient,
            received_date=date(2026,10,9),expiry_date=None,on_hand_quantity=quantity,unit='ml'))
        s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,
            state='COMPLETE_CURRENT_LOTS',observed_at=c[0][4][0],covered_lot_ids=(lot,),
            evidence_reference='synthetic observed current stock'),'inventory')
        s.commit()
    return lot


@pytest.mark.parametrize('stock,expected', [(100,'recommendation_available'),(0,'no_eligible_candidate')])
def test_no_eligible_offer_does_not_prove_no_service_or_market_infeasibility(flow,stock,expected):
    c,_,_,worker=flow
    term=demand_and_offer(flow,cost='0')
    lot=physical_stock(flow,stock)
    from tests.integration.test_contextual_readiness import contextual
    assert contextual(flow)['readiness']['can_generate']  # Execution admissible, winner unassessed.
    accepted=submit(c);record=worker.run_one()
    assert record.status=='completed' and record.outcome==expected,record.error_code
    assert record.capture.computed_product_ids==(c[2],)
    assert record.capture.prepared.supplier_terms==() and record.capture.procurement_input.offers==()
    assert record.declarations.offer_admission.omissions[0].term_id==term
    assert all(s.proof_scope=='CAPTURED_FINITE_DOMAIN_ONLY' for s in record.result.procurement.strategies)
    response=c[0][5].get(accepted.headers['Location'])
    assert response.status_code==200,response.text
    result=response.json()['data']['result']
    assert 'OFFER_OMITTED' in {w['code'] for w in result['warnings']}
    if stock:
        winner=next(o for o in result['options'] if o['option_id']==result['winner_option_id'])
        assert winner['purchases']==[] and winner['costs']['total']['numerator']=='0'
    else:
        assert result['winner_option_id'] is None
        assert all(s['customer_feasibility']=='UNKNOWN' and s['proof']=='UNPROVEN' for s in result['strategies'])
    with Session(c[0][1]) as fresh:
        assert fresh.get(InventoryLot,lot).on_hand_quantity==stock
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==0


@pytest.mark.parametrize('kind',['coverage','binding','currency','horizon','multiple'])
def test_omission_does_not_hide_shared_fee_unknown_or_conflict(flow,kind):
    c,_,_,worker=flow
    demand_and_offer(flow,cost='0',system='omitted')
    demand_and_offer(flow,system='eligible')
    with Session(c[0][1]) as s:
        fee=d.FeeSource(source_fee_key='none' if kind!='multiple' else 'second-coverage',scope='STORE_PROCUREMENT',
            effective_from=date(2026,10,10),effective_to=date(2026,10,12) if kind=='horizon' else None,
            mode='PER_OFFER' if kind in ('binding','coverage') else 'NONE',coverage='UNKNOWN' if kind=='coverage' else 'COMPLETE',
            currency='USD' if kind=='currency' else 'VND',components=(),covered_source_term_keys=(),
            covered_source_supplier_keys=(),evidence_reference='explicit scoped fee evidence',reason='synthetic D3')
        OperationalConfiguration(s,c[1].store_id).fee(fee,uuid4(),'synthetic',{}, {})
        s.commit()
    from tests.integration.test_contextual_readiness import contextual
    current=contextual(flow)['readiness']
    assert not current['can_generate'] and 'PAYABLE_FEE_COVERAGE_UNKNOWN' in current['reason_codes']
    assert submit(c).status_code==202
    record=worker.run_one()
    assert record.outcome=='computation_blocked'
    assert record.result.selection is None
    assert 'PAYABLE_FEE_COVERAGE_UNKNOWN' in {p.code for p in record.capture.problems}


def test_missing_conditional_shelf_life_uses_complete_alternative(flow):
    c,ingredient,_,worker=flow
    with Session(c[0][1]) as s:
        s.get(Ingredient,ingredient).expiry_tracking=True;s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,
            state='CONFIRMED_EMPTY',observed_at=c[0][4][0],covered_lot_ids=(),
            evidence_reference='confirmed empty after catalog change'),'inventory')
        s.commit()
    missing=demand_and_offer(flow,system='missing-shelf')
    alternative=demand_and_offer(flow,system='known-shelf',shelf=7)
    assert submit(c).status_code==202
    record=worker.run_one()
    assert record.outcome=='recommendation_available',[(p.code,p.detail) for p in record.capture.problems]
    omission=record.declarations.offer_admission.omissions[0]
    assert omission.term_id==missing and omission.missing_fields==('shelf_life_days',)
    assert {t.id for t in record.capture.prepared.supplier_terms}=={alternative}
    assert record.capture.exclusions==()


def test_remaining_offer_fee_bindings_are_rechecked_without_charging_omitted_offer(flow,record_property):
    c,ingredient,_,worker=flow
    omitted=demand_and_offer(flow,cost='0')
    supplier,eligible=uuid4(),uuid4()
    with Session(c[0][1]) as s:
        writer=OperationalConfiguration(s,c[1].store_id)
        writer.supplier(d.SupplierSource(source_supplier_key='eligible-supplier',name='Eligible supplier',active=True),
            supplier,'synthetic',{},create=True)
        writer.term(d.TermSource(source_term_key='eligible-offer',supplier_id=supplier,ingredient_id=ingredient,
            effective_from=date(2026,10,1),effective_to=None,unit='ml',pack_size_base_quantity='5',pack_cost='2',
            currency='VND',minimum_order_packs=1,lead_time_days=0,shelf_life_days=None,
            active=True,maximum_order_base_quantity=None),eligible,'synthetic',{})
        declaration(s,c[1].store_id,d.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',effective_from=date(2026,10,10),
            effective_to=None,committed_inbound_state='CONFIRMED_NONE',no_additional_orders_state='CONFIRMED_NONE',
            capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),supplier_limit_state='EXPLICIT_NOT_CONFIGURED',
            supplier_limits=(),evidence_reference='exact current suppliers'),'context')
        writer.fee(d.FeeSource(source_fee_key='none',scope='STORE_PROCUREMENT',effective_from=date(2026,10,10),effective_to=None,
            mode='PER_OFFER',coverage='COMPLETE',currency='VND',components=(d.FeeComponent(component_key='fee',label='Payable',
            basis='PER_OFFER',source_term_key='eligible-offer',source_supplier_key=None,amount='3',condition='WHEN_ORDERED'),),
            covered_source_term_keys=('eligible-offer',),covered_source_supplier_keys=(),evidence_reference='complete eligible fee',
            reason='D3 captured eligible domain'),uuid4(),'synthetic',{}, {})
        s.commit()
    assert submit(c).status_code==202
    record=worker.run_one()
    record_property('stage_seconds',record.public_execution.elapsed_seconds)
    record_property('engine_seconds',record.public_execution.engine_seconds)
    record_property('stage_overrun_seconds',record.public_execution.stage_overrun_seconds)
    assert record.outcome=='recommendation_available',(record.error_code,record.public_execution)
    assert record.declarations.offer_admission.omissions[0].term_id==omitted
    winner=next(o for o in record.result.comparison.options if o.token==record.result.selection.winner_token)
    assert {b.term_id for b in winner.basket}=={eligible}
    assert winner.outlay.total.numerator=='17'


@pytest.mark.parametrize('kind',['stale','multiple'])
def test_current_inventory_proof_must_be_unique_and_dependency_bound(flow,kind):
    c,ingredient,_,worker=flow
    demand_and_offer(flow,cost='0',system='omit')
    demand_and_offer(flow,system='valid')
    lot=physical_stock(flow,100)
    with Session(c[0][1]) as s:
        if kind=='stale':
            s.get(InventoryLot,lot).on_hand_quantity=99
        else:
            declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,
                state='COMPLETE_CURRENT_LOTS',observed_at=c[0][4][0],covered_lot_ids=(lot,),
                evidence_reference='second unresolved current proof'),'conflicting-inventory')
        s.commit()
    assert submit(c).status_code==202
    record=worker.run_one()
    assert record.outcome=='no_computable_products'
    assert 'INVENTORY_BALANCE_MISSING' in {p.code for p in record.capture.exclusions[0].reasons}


def test_legacy_accepted_run_does_not_acquire_new_omission_policy(flow):
    from app.application.use_cases.planning_run import decode_row
    from app.application.planning_serialization import digest,exact_json
    c,_,_,worker=flow
    demand_and_offer(flow,cost='0')
    assert submit(c).status_code==202
    # Emulate a pre-D3 queued record, with its original policy absence and verified digest.
    with Session(c[0][1]) as s:
        row=s.scalar(select(PlanningRun));data=dict(row.record_json)
        data['public_acceptance']=dict(data['public_acceptance'])
        data['public_acceptance'].pop('offer_eligibility_policy')
        from app.application.contracts.planning_run import PlanningRunRecord
        legacy=PlanningRunRecord.model_validate(data)
        row.record_json=exact_json(legacy);row.record_digest=digest('aggregate',legacy)
        s.commit()
        assert decode_row(row).public_acceptance.offer_eligibility_policy is None
    record=worker.run_one()
    assert record.outcome=='computation_blocked'
    assert record.declarations.offer_admission is None
    assert 'OFFER_BOUND_UNKNOWN' in {p.code for p in record.capture.problems}
