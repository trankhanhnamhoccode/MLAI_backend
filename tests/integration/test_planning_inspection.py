"""S410 actual retained engine/HTTP/fresh-session evidence, guarded test DB."""
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow,config,env,submit,demand_and_offer
from app.models import PlanningRun,Ingredient,InventoryLot
from app.application.planning_serialization import digest


def test_retained_inspection_purchase_daily_and_current_catalog_independence(flow):
    c,ingredient,_,worker=flow;demand_and_offer(flow)
    response=submit(c);location=response.headers['Location']
    assert c[0][5].get(location+'/ingredients').status_code==409
    record=worker.run_one();assert record.status=='completed',record.error_code
    read=c[0][5].get(location).json()['data'];option=read['result']['winner_option_id']
    navigator=c[0][5].get(location+'/ingredients',params=[('ingredient_id',str(ingredient)),('ingredient_id',str(uuid4()))])
    assert navigator.status_code==200,navigator.text
    item=navigator.json()['data']['items'][0]
    assert item['purchase_quantity']['numerator']=='35' and item['purchase_line_count']==1
    assert item['name_availability']=='captured'
    detail=c[0][5].get(location+'/ingredients/'+str(ingredient));assert detail.status_code==200,detail.text
    value=detail.json()['data'];assert len(value['daily_balances'])==21
    assert [d['path'] for d in value['daily_balances']]==['LOW']*7+['BASE']*7+['HIGH']*7
    assert value['purchases']==read['result']['options'][0]['purchases']
    assert value['captured_stock']['lots']==[] and value['captured_stock']['scope_declaration']=='CONFIRMED_EMPTY'
    assert value['daily_balances'][0]['incoming_quantity']['numerator']=='35'
    assert len(value['related_products'][0]['fulfilled_contributions'])==21
    explanation=c[0][5].get(location+'/explanation',params={'option_id':option});assert explanation.status_code==200,explanation.text
    assert explanation.json()['data']['result_digest']==value['result_digest']==record.result_digest
    assert len(explanation.json()['data']['options'][0]['evidence'])==3
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,record.run_id);prior=row.record_digest
        s.get(Ingredient,ingredient).name='Changed after capture';s.commit()
    assert c[0][5].get(location+'/ingredients/'+str(ingredient)).json()['data']==value
    with Session(c[0][1]) as s:assert s.get(PlanningRun,record.run_id).record_digest==prior
    for suffix in ('/ingredients','/ingredients/'+str(ingredient),'/explanation'):
        assert c[0][5].get(location+suffix,params={'option_id':'unknown'}).status_code==404
    assert c[0][5].get(location+'/ingredients/'+str(uuid4())).json()['error']['code']=='INGREDIENT_NOT_IN_RUN'
    out=Path('runtime/s410');out.mkdir(parents=True,exist_ok=True)
    for name,result in [('c04',navigator),('c05',detail),('c08',explanation)]:
        (out/(name+'_actual.json')).write_text(result.text,encoding='utf-8')


def test_failed_after_capture_null_digest_preserves_snapshot(flow,monkeypatch):
    c,ingredient,_,worker=flow
    from app.application.use_cases import planning_worker
    def fail(*args,**kwargs):raise RuntimeError('INJECTED after actual retained capture')
    monkeypatch.setattr(planning_worker,'execute_captured_pipeline_v2',fail)
    response=submit(c);record=worker.run_one()
    assert record.status=='failed' and record.capture.prepared and record.result_digest is None
    location=response.headers['Location']
    navigator=c[0][5].get(location+'/ingredients');assert navigator.status_code==200,navigator.text
    detail=c[0][5].get(location+'/ingredients/'+str(ingredient));assert detail.status_code==200,detail.text
    for result in (navigator,detail):
        assert result.json()['data']['result_digest'] is None and result.json()['meta']['result_digest'] is None
        assert result.json()['data']['selection_status']=='not_selected'
    assert navigator.json()['data']['items'][0]['purchase_quantity'] is None
    assert detail.json()['data']['purchases'] is None and detail.json()['data']['daily_balances'] is None
    assert detail.json()['data']['evidence_availability']=='not_evaluated'
    assert detail.json()['data']['captured_stock']['scope_declaration']=='CONFIRMED_EMPTY'
    reasons=c[0][5].get(location+'/explanation').json()['data']
    assert reasons['availability']=='unavailable' and reasons['winner']['reason_code']=='NOT_EVALUATED'
    assert reasons['options']==[] and reasons['blockers'][0]['code']=='EXECUTION_ERROR'
    out=Path('runtime/s410')
    (out/'c04_null_digest_actual.json').write_text(navigator.text,encoding='utf-8')
    (out/'c05_null_digest_actual.json').write_text(detail.text,encoding='utf-8')
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,record.run_id)
        assert row.record_json['result_digest'] is None and row.record_json['input_digest']==record.input_digest


def test_known_zero_and_historical_missing_labels_and_warm_corruption(flow):
    c,ingredient,_,worker=flow;response=submit(c);record=worker.run_one()
    assert record.status=='completed',record.error_code
    location=response.headers['Location']
    value=c[0][5].get(location+'/ingredients').json()['data']['items'][0]
    assert value['purchase_quantity']['numerator']=='0' and value['purchase_line_count']==0
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,record.run_id)
        raw=dict(row.record_json);public=dict(raw['public_capture']);public.pop('ingredient_labels');raw['public_capture']=public
        row.record_json=raw;row.record_digest=digest('aggregate',raw);row.revision+=1;s.commit()
    old=c[0][5].get(location+'/ingredients');assert old.status_code==200,old.text
    assert old.json()['data']['items'][0]['display_name'] is None
    assert old.json()['data']['items'][0]['issues'][0]['code']=='LABEL_NOT_CAPTURED'
    with Session(c[0][1]) as s:
        row=s.get(PlanningRun,record.run_id);raw=dict(row.record_json);raw['outcome']='execution_error'
        row.record_json=raw;row.record_digest=digest('aggregate',raw);s.commit()
    assert c[0][5].get(location+'/ingredients').json()['error']['code']=='RESULT_INTEGRITY_UNAVAILABLE'


def test_physical_expired_future_lots_scoped_engine_warning_and_global_filter_parity(flow):
    from datetime import date
    from tests.integration.test_readiness_context import declaration
    from app.application.contracts import import_domains as d
    c,ingredient,_,worker=flow;expired,future=uuid4(),uuid4()
    with Session(c[0][1]) as s:
        s.add_all([InventoryLot(id=expired,store_id=c[1].store_id,ingredient_id=ingredient,received_date=date(2026,10,8),
            expiry_date=date(2026,10,9),on_hand_quantity=5,unit='ml',unit_cost=0),
            InventoryLot(id=future,store_id=c[1].store_id,ingredient_id=ingredient,received_date=date(2026,10,12),
            expiry_date=None,on_hand_quantity=12,unit='ml',unit_cost=None)]);s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,state='COMPLETE_CURRENT_LOTS',
            observed_at=c[0][4][0],covered_lot_ids=(expired,future),evidence_reference='synthetic physical source includes expired/future-date anomaly'),'inventory')
        s.commit()
    response=submit(c);record=worker.run_one();assert record.outcome=='recommendation_available',[(p.code,p.detail) for p in record.capture.problems]
    location=response.headers['Location'];detail=c[0][5].get(location+'/ingredients/'+str(ingredient));assert detail.status_code==200,detail.text
    lots={l['lot_id']:l for l in detail.json()['data']['captured_stock']['lots']}
    assert lots[str(expired)]['quantity']['numerator']=='5' and lots[str(expired)]['unit_cost']=='0'
    assert lots[str(future)]['quantity']['numerator']=='12' and lots[str(future)]['unit_cost'] is None
    warning=next(i for i in detail.json()['data']['issues'] if i['code']=='FUTURE_RECEIPT_NOT_INBOUND')
    assert warning['details']['entity']=='inventory_lot' and warning['details']['entity_id']==str(future)
    unfiltered=c[0][5].get(location+'/explanation').json()['data']
    filtered=c[0][5].get(location+'/explanation',params={'option_id':record.result.selection.winner_token}).json()['data']
    assert unfiltered['warnings']==filtered['warnings'] and unfiltered['blockers']==filtered['blockers']
    assert any(w['code']=='FUTURE_RECEIPT_NOT_INBOUND' for w in filtered['warnings'])
    assert all(row['incoming_quantity']['numerator']=='0' for row in detail.json()['data']['daily_balances'])


def test_ingredient_signed_pagination_live_changes_do_not_repin_snapshot(flow):
    from datetime import date
    from app.models import RecipeLine
    from tests.integration.test_readiness_context import declaration
    from app.application.contracts import import_domains as d
    c,ingredient,recipe,worker=flow;second=uuid4()
    with Session(c[0][1]) as s:
        s.add(Ingredient(id=second,store_id=c[1].store_id,name='Second captured ingredient',base_unit='ml',expiry_tracking=False,active=True));s.flush()
        s.add(RecipeLine(id=uuid4(),store_id=c[1].store_id,recipe_id=recipe,ingredient_id=second,quantity=1,unit='ml'));s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=second,state='CONFIRMED_EMPTY',observed_at=c[0][4][0],
            covered_lot_ids=(),evidence_reference='physical second empty'),'inventory-second')
        declaration(s,c[1].store_id,d.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',effective_from=date(2026,10,10),effective_to=None,
            committed_inbound_state='CONFIRMED_NONE',no_additional_orders_state='CONFIRMED_NONE',capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),
            supplier_limit_state='EXPLICIT_NOT_CONFIGURED',supplier_limits=(),evidence_reference='updated two-ingredient context'),'context')
        s.commit()
    response=submit(c);record=worker.run_one();assert record.outcome=='recommendation_available',[(p.code,p.detail) for p in record.capture.problems]
    location=response.headers['Location'];first=c[0][5].get(location+'/ingredients',params={'limit':1})
    assert first.status_code==200 and first.json()['meta']['pagination']['total_count']==2
    cursor=first.json()['meta']['pagination']['next_cursor'];assert cursor
    with Session(c[0][1]) as s:s.get(Ingredient,second).name='Changed live label';s.commit()
    next_page=c[0][5].get(location+'/ingredients',params={'limit':1,'cursor':cursor});assert next_page.status_code==200,next_page.text
    assert next_page.json()['meta']['response_version']==first.json()['meta']['response_version']
    ids=[first.json()['data']['items'][0]['ingredient_id'],next_page.json()['data']['items'][0]['ingredient_id']]
    assert ids==sorted([str(ingredient),str(second)])
    tampered=c[0][5].get(location+'/ingredients',params={'limit':1,'cursor':cursor[:-1]+('0' if cursor[-1]!='0' else '1')})
    assert tampered.json()['error']['code']=='INVALID_CURSOR'
