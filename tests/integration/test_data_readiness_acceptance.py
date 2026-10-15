"""D5 public setup -> contextual GET -> actual workers -> immutable PG oracle."""
from datetime import datetime,timezone,timedelta
from fractions import Fraction
from uuid import uuid4
import json

from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_import_setup_stock import (
    env,fresh_store,prepare_public_planning,review_batch,complete,analyzed_files,csv_source)
from app.application.use_cases.planning_worker import PlanningExecution
from app.models import SupplierTerm,PlanningRun,InventoryLot,InventoryMovement
from tests.integration.test_planning_public import flow,config,demand_and_offer,submit


def exact(value):
    return Fraction(int(value['numerator']),int(value['denominator']))


def test_public_setup_custom_oracle_omission_stock_fees_and_revalidation(fresh_store,monkeypatch):
    c=fresh_store;setup=prepare_public_planning(c,monkeypatch,omitted_offer=True)
    client=c[0][5];base=f'/api/v1/stores/{c[1].store_id}'
    from app.application.use_cases import forecast_trained_execution
    monkeypatch.setattr(forecast_trained_execution,'_now',lambda:c[0][4][0])
    request=dict(requirements_mode='custom',forecast_start_date=setup.today.isoformat(),requirements=dict(
        paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])],budget_limit='100'))
    params={'planning_request':json.dumps(request)}

    def assessed():
        ctx=client.get(base+'/planning-context',params=params)
        r01=client.get(base+'/readiness',params={**params,'actions':'planning'})
        assert ctx.status_code==r01.status_code==200,(ctx.text,r01.text)
        assert ctx.json()['data']['readiness']['assessment']==r01.json()['data']['planning_assessment']
        return ctx.json()['data']['readiness']

    def accept(key=None):
        return client.post(base+'/procurement-plans',json=request,
            headers={**c[3],'Idempotency-Key':key or str(uuid4())})

    def views(response):
        r=client.get(response.headers['Location']);e=client.get(response.headers['Location']+'/explanation')
        assert r.status_code==e.status_code==200,(r.text,e.text)
        return r.json()['data'],e.json()['data']

    default=client.get(base+'/planning-context').json()['data']['readiness']
    assert not default['can_generate'] and default['assessment']['input_scope']=='DEFAULT_CONFIGURATION'
    assert 'DEFAULT_CONFIGURATION_UNAVAILABLE' in default['reason_codes']
    assessment=assessed();assert assessment['can_generate'],assessment
    assert assessment['assessment']['requirements_mode']=='custom'
    with Session(c[0][1]) as fresh:
        terms=fresh.scalars(select(SupplierTerm).where(SupplierTerm.store_id==c[1].store_id)).all()
        omitted=next(t.id for t in terms if t.pack_cost==0)
        eligible=next(t.id for t in terms if t.pack_cost==10)
        assert fresh.scalar(select(func.count()).select_from(PlanningRun))==0
    warning=next(w for w in assessment['assessment']['warnings'] if w['code']=='OFFER_OMITTED')
    assert warning['details']['entity_id']==str(omitted) and warning['details']['version']==1
    assert warning['details']['classification']=='OFFER_BOUND_UNKNOWN'
    key=str(uuid4());accepted=accept(key);assert accepted.status_code==202,accepted.text
    worker=PlanningExecution(c[0][2],client.app.state.forecast_serving)
    record=worker.run_one()
    assert record.status=='completed' and record.outcome=='recommendation_available',(record.error_code,record.public_execution)
    first,explanation=views(accepted)
    assert first['configuration']['requirements_mode']=='custom' and first['configuration']['default_version'] is None
    assert first['configuration']['budget']['limit']=='100'
    result=first['result'];winner=next(o for o in result['options'] if o['option_id']==result['winner_option_id'])
    # Independent bounded oracle: 14 units demanded, stock12, pack4/cost10, cap100.
    # One explicit Product, zero fees/lead/loss, no expiry/capacity; do not call solver
    # or production projections to enumerate purchase feasibility/outlay.
    expected=min((10*p,p) for p in range(11) if min(14,12+4*p)>=Fraction(95,100)*14)
    assert expected==(10,1)
    purchase,=winner['purchases']
    assert purchase['supplier_term_id']==str(eligible) and purchase['packs']==expected[1]
    assert exact(purchase['quantity'])==4 and exact(winner['costs']['total'])==expected[0]
    assert exact(winner['costs']['payable_fees'])==0
    service=next(s for s in winner['product_services'] if s['path']=='BASE')
    assert exact(service['requested'])==exact(service['fulfilled'])==14
    assert exact(service['service'])==1
    assert first['forecast']['quality_status']=='not_evaluated'
    assert 'RECEIPT_DATE_UNKNOWN' in {w['code'] for w in result['warnings']}
    assert any(w['code']=='OFFER_OMITTED' and w['details']['source_version']==1 for w in explanation['warnings'])
    assert all(s['proof_scope']=='CAPTURED_FINITE_DOMAIN_ONLY' for s in result['strategies'])
    with Session(c[0][1]) as fresh:
        original=fresh.get(PlanningRun,record.run_id).record_json
        assert original['request']==request and original['declarations']['offer_admission']['omissions'][0]['term_id']==str(omitted)
        assert original['input_digest'] and original['result_digest']
        proof=next(p for p in record.public_capture.operational_evidence.confirmations if p.entity_id==omitted)
        assert proof.actor_id==c[1].user_id and proof.audit_id is not None and proof.confirmed_at is not None
        assert fresh.get(InventoryLot,setup.lot).on_hand_quantity==12
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==1

    # Explicit new observation + refreshed completeness, entirely through Import.
    c[0][4][0]=datetime.now(timezone.utc)
    ident=analyzed_files(c,[('count.csv',csv_source('inventory_count',[dict(ingredient_id='MILK',lot_id='LOT-1',
        on_hand='20',unit='l',observed_at=c[0][4][0].isoformat(),reason='Synthetic actual stock observation')])),
        ('scope.csv',csv_source('scope_declarations',[dict(source_declaration_key='stock',declaration=dict(kind='INVENTORY',
            ingredient_id='MILK',state='COMPLETE_CURRENT_LOTS',observed_at=c[0][4][0].isoformat(),covered_lot_ids=['LOT-1'],
            evidence_reference='Synthetic complete observed stock20'))]))])
    review_batch(c,ident,bindings={'MILK':setup.ingredient,'LOT-1':setup.lot});complete(c,ident)
    assert assessed()['can_generate']
    zero=accept();assert zero.status_code==202,zero.text
    zero_record=worker.run_one();assert zero_record.outcome=='recommendation_available',zero_record.error_code
    second,_=views(zero)
    zero_winner=next(o for o in second['result']['options'] if o['option_id']==second['result']['winner_option_id'])
    assert zero_winner['purchases']==[] and exact(zero_winner['costs']['total'])==0

    # Readiness is not a reservation; new acceptance revalidates current ceiling,
    # while successful idempotency replay returns the already retained acceptance.
    changed=client.put(base+'/planning-budget',headers={**c[3],'Idempotency-Key':str(uuid4()),'If-Match':setup.budget_etag},json={'amount':'5'})
    assert changed.status_code==200,changed.text
    assert 'BUDGET_LIMIT_EXCEEDS_CEILING' in assessed()['reason_codes']
    replay=accept(key)
    assert replay.status_code==200,replay.text
    assert replay.json()['data']=={**accepted.json()['data'],'status':'completed'}
    assert replay.json()['meta']==dict(warnings=[],poll_after_ms=0)
    rejected=accept();assert rejected.status_code==422,rejected.text
    assert worker.run_one() is None
    restored=client.put(base+'/planning-budget',headers={**c[3],'Idempotency-Key':str(uuid4()),'If-Match':changed.headers['ETag']},json={'amount':'100'})
    assert restored.status_code==200,restored.text

    # Use the accepted future-only amendment workflow; never rewrite today's fee.
    from sqlalchemy import text
    from app.models.operational_import import PayableFeeRecord
    with Session(c[0][1]) as fresh:
        old_fee,version=fresh.execute(select(PayableFeeRecord,text('xmin::text'))).one()
        amendment=dict(fee_id=str(old_fee.id),expected_version=version,effective_to=setup.today.isoformat(),reason='Synthetic reviewed future coverage')
    future=setup.today+timedelta(days=1)
    fee=dict(source_fee_key='F1',scope='STORE_PROCUREMENT',effective_from=future.isoformat(),effective_to=None,
        mode='PER_OFFER',coverage='UNKNOWN',currency='VND',components=[],covered_source_term_keys=[],covered_source_supplier_keys=[],
        evidence_reference='Synthetic fee coverage has not been confirmed',reason='Unknown is not free')
    ident=analyzed_files(c,[('fees-future.csv',csv_source('payable_fees',[dict(reversed(list(fee.items())))]))])
    review_batch(c,ident,source_context={'fee_period_amendments':[amendment]})
    from tests.integration.test_import_staging import previewed,post
    from tests.integration.test_import_commit import confirm,finished
    preview=previewed(c,ident);assert not preview['preview']['summary']['blockers'],preview['preview']['summary']
    confirmation=confirm(c,ident,preview);assert confirmation.status_code==200,confirmation.text
    accepted_change=post(c,f'/imports/{ident}/process',dict(phase='commit',preview_id=preview['preview']['summary']['preview_id'],
        preview_digest=preview['preview']['summary']['digest'],confirm=True,reason='Reviewed future-only fee coverage',resolutions=[],
        supplier_changes=[dict(action_id=row['row_id'],reason='Explicit reviewed amendment') for row in preview['preview']['rows'] if row['confirmation_required']]),
        match=confirmation.json()['data']['import_revision'])
    finished(c,ident,accepted_change)
    request['forecast_start_date']=future.isoformat();params['planning_request']=json.dumps(request)
    blocked=assessed();assert not blocked['can_generate']
    assert 'PAYABLE_FEE_COVERAGE_UNKNOWN' in blocked['reason_codes']
    pending=accept();assert pending.status_code==202,pending.text
    failed=worker.run_one()
    assert failed.status=='completed' and failed.outcome=='computation_blocked'
    blocked_view,_=views(pending)
    assert blocked_view['result']['winner_option_id'] is None
    assert views(accepted)==(first,explanation)
    with Session(c[0][1]) as fresh:
        assert fresh.get(PlanningRun,record.run_id).record_json==original
        assert fresh.get(InventoryLot,setup.lot).on_hand_quantity==20
        assert fresh.scalar(select(func.count()).select_from(PlanningRun))==3
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==2


def test_recognized_fallback_and_partial_scope_match_worker_and_retained_evidence(flow):
    from app.models import Product
    from app.models.model_serving import ModelServingConfiguration
    from app.application.contracts.model_serving import ServingPolicy
    from tests.integration.test_contextual_readiness import contextual
    c,_,_,worker=flow;second=uuid4()
    demand_and_offer(flow)
    with Session(c[0][1]) as fresh:
        fresh.get(ModelServingConfiguration,c[1].store_id).configuration_json=ServingPolicy(mode='TRAINED',artifact_identity=None,
            dependency_versions=(),fallback_policy='ADR015_RECOGNIZED_ONLY').model_dump(mode='json')
        fresh.add(Product(id=second,store_id=c[1].store_id,name='No observed history',selling_unit='piece',active=True))
        fresh.commit()
    request=dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements=dict(paths=[dict(
        path='BASE',min_fill_rate_percent='95',product_overrides=[dict(product_id=str(second),min_fill_rate_percent='100')])],budget_limit=None))
    assessment=contextual(flow,request)['readiness']
    assert assessment['can_generate'],assessment
    assert assessment['forecast']['requested_mode']=='TRAINED' and assessment['forecast']['selection_reason']=='NO_ARTIFACT'
    assert assessment['forecast']['quality_status']=='not_evaluated'
    assert assessment['scope_estimate']['menu_product_count']==2 and assessment['scope_estimate']['estimated_computable_product_count']==1
    accepted=submit(c,body=request);assert accepted.status_code==202,accepted.text
    record=worker.run_one();assert record.outcome=='recommendation_available',record.error_code
    response=c[0][5].get(accepted.headers['Location']);assert response.status_code==200,response.text
    view=response.json()['data']
    assert view['forecast']['model_type']==assessment['forecast']['actual_model_type']
    assert record.public_capture.identity.selection_reason==assessment['forecast']['selection_reason']
    assert 'BASELINE_FALLBACK' in {w['code'] for w in view['forecast']['warnings']}
    assert 'BASELINE_FALLBACK' in {w['code'] for w in assessment['assessment']['warnings']}
    assert view['scope']['coverage_status']=='partial' and view['scope']['computed_product_ids']==[str(c[2])]
    exclusion=next(e for e in view['scope']['excluded_products'] if e['product_id']==str(second))
    assert exclusion['requirement_overrides']==[dict(path='BASE',target_percent='100',status='NOT_EVALUATED')]
    explanation=c[0][5].get(accepted.headers['Location']+'/explanation');assert explanation.status_code==200,explanation.text
    with Session(c[0][1]) as fresh:
        raw=fresh.get(PlanningRun,record.run_id).record_json
        assert raw['public_capture']['identity']['selection_reason']=='NO_ARTIFACT'
        assert raw['request']==request
        assert raw['capture']['computed_product_ids']==[str(c[2])]


def test_mandatory_safety_is_blocking_only_for_computed_dependencies(flow):
    from datetime import date
    from app.models import Ingredient,BusinessConstraint
    from app.application.contracts import import_domains as domains
    from tests.integration.test_readiness_context import declaration
    from tests.integration.test_contextual_readiness import contextual
    c,ingredient,_,worker=flow;unused=uuid4();outside=uuid4()
    with Session(c[0][1]) as fresh:
        fresh.add(Ingredient(id=unused,store_id=c[1].store_id,name='Outside computed dependencies',base_unit='ml',active=True,expiry_tracking=False))
        fresh.flush()
        declaration(fresh,c[1].store_id,domains.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',
            effective_from=date(2026,10,10),effective_to=None,committed_inbound_state='CONFIRMED_NONE',
            no_additional_orders_state='CONFIRMED_NONE',capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),
            supplier_limit_state='EXPLICIT_NOT_CONFIGURED',supplier_limits=(),evidence_reference='Explicit context after adding unused Ingredient'),'context')
        fresh.add(BusinessConstraint(id=outside,store_id=c[1].store_id,scope_type='INGREDIENT',scope_id=unused,
            constraint_type='MIN_SAFETY_STOCK',numeric_value=0,unit='ml',version=1,effective_from=date(2026,10,10),effective_to=None,active=True))
        fresh.commit()
    assert contextual(flow)['readiness']['can_generate']
    accepted=submit(c);assert accepted.status_code==202,accepted.text
    record=worker.run_one();assert record.outcome=='recommendation_available',record.error_code
    assert outside not in {constraint.id for constraint in record.capture.prepared.constraints}
    with Session(c[0][1]) as fresh:
        fresh.add(BusinessConstraint(id=uuid4(),store_id=c[1].store_id,scope_type='INGREDIENT',scope_id=ingredient,
            constraint_type='MIN_SAFETY_STOCK',numeric_value=0,unit='ml',version=1,effective_from=date(2026,10,10),effective_to=None,active=True))
        fresh.commit()
    current=contextual(flow)['readiness']
    assert not current['can_generate'] and 'MIN_SAFETY_STOCK_UNSUPPORTED' in current['reason_codes']
    accepted=submit(c);assert accepted.status_code==202,accepted.text
    blocked=worker.run_one()
    assert blocked.outcome=='computation_blocked' and blocked.result.procurement is None
