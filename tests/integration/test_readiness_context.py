"""IMP14/PLAN4 real snapshot projections, not public PlanningRun acceptance."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from tests.integration.test_planning_configuration_public import config,env,base,cap,save
from tests.integration.test_auth_public import setup,login,KEY
from app.application.use_cases.readiness import ReadinessReads
from app.application.use_cases.model_serving import ModelServingOperator
from app.application.contracts.model_serving import OperatorConfigurationCommand
from app.application.contracts import import_domains as d
from app.application.use_cases.operational_configuration import OperationalConfiguration
from app.application.operational_import_facts import declaration_dependency
from app.repositories.import_staging import read_set_in_session
from app.models import Product,Ingredient,Recipe,RecipeLine,SalesDaily,StoreMembership,ForecastRun,PlanningRun
from app.models.auth import MembershipGrant
from app.models.operational_import import ScopeDeclarationRecord


@pytest.fixture
def readiness(config):
    c=config
    c[0][5].app.state.readiness=ReadinessReads(c[0][2],c[0][5].app.state.forecast_serving)
    return c


def read(c,actions='planning',**params):
    return c[0][5].get(base(c)+'/readiness',params={'actions':actions,**params})


def configure_baseline(c):
    return ModelServingOperator(c[0][1],c[0][0],lambda:c[0][4][0]).configure(
        OperatorConfigurationCommand(store_id=c[1].store_id,action='BASELINE',expected_version=None,evidence_reference='synthetic operator approval'),
        'support-test',KEY)


def declaration(s,store,value,key):
    snap,_=read_set_in_session(s,store)
    OperationalConfiguration(s,store).declaration(d.DeclarationSource(source_declaration_key=key,declaration=value),uuid4(),'synthetic',{},declaration_dependency(snap,value))


def known_facts(c):
    configure_baseline(c)
    assert cap(c,**{'If-None-Match':'*'}).status_code==201
    ingredient,recipe=uuid4(),uuid4()
    with Session(c[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=c[1].store_id,name='Synthetic milk',base_unit='ml',expiry_tracking=False,active=True));s.flush()
        s.add(Recipe(id=recipe,store_id=c[1].store_id,product_id=c[2],version=1,effective_from=date(2026,10,1),effective_to=None,yield_quantity=1,process_loss_rate=0));s.flush()
        s.add(RecipeLine(id=uuid4(),store_id=c[1].store_id,recipe_id=recipe,ingredient_id=ingredient,quantity=1,unit='ml'))
        s.add(SalesDaily(id=uuid4(),store_id=c[1].store_id,product_id=c[2],sales_date=date(2026,10,9),quantity=0));s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,state='CONFIRMED_EMPTY',observed_at=c[0][4][0],covered_lot_ids=(),evidence_reference='physical empty'), 'inventory')
        declaration(s,c[1].store_id,d.SalesDeclaration(kind='SALES_COVERAGE',product_ids=(c[2],),from_date=date(2026,10,9),to_date=date(2026,10,9),state='COMPLETE',evidence_reference='observed zero'), 'sales')
        declaration(s,c[1].store_id,d.ProcurementDeclaration(kind='PROCUREMENT_CONTEXT',effective_from=date(2026,10,10),effective_to=None,
            committed_inbound_state='CONFIRMED_NONE',no_additional_orders_state='CONFIRMED_NONE',capacity_state='EXPLICIT_NOT_CONFIGURED',capacities=(),supplier_limit_state='EXPLICIT_NOT_CONFIGURED',supplier_limits=(),evidence_reference='confirmed one-order context'), 'context')
        OperationalConfiguration(s,c[1].store_id).fee(d.FeeSource(source_fee_key='none',scope='STORE_PROCUREMENT',effective_from=date(2026,10,10),effective_to=None,
            mode='NONE',coverage='COMPLETE',currency='VND',components=(),covered_source_term_keys=(),covered_source_supplier_keys=(),evidence_reference='known no fees',reason='explicit none'),uuid4(),'synthetic',{}, {})
        s.commit()
    return ingredient,recipe


def test_empty_reader_ready_forecast_blocked_and_no_computation(readiness,monkeypatch):
    c=readiness
    with Session(c[0][1]) as s:s.get(Product,c[2]).active=False;s.commit()
    response=read(c,'menu,inventory,import');assert response.status_code==200,response.text
    assert all(a['availability']=='ready' and a['data_status']=='valid' for a in response.json()['data']['actions'])
    assert response.json()['data']['scope_estimate'] is None
    forecasting=read(c,'forecast');assert forecasting.status_code==200,forecasting.text
    value=forecasting.json()['data'];assert value['actions'][0]['availability']=='blocked'
    assert 'NO_COMPUTABLE_PRODUCTS' in [i['code'] for i in value['actions'][0]['blockers']]
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ForecastRun))==0
        assert s.scalar(select(func.count()).select_from(PlanningRun))==0


def test_missing_history_is_not_zero_and_unconfigured_model_unknown(readiness):
    c=readiness
    result=read(c,'forecast').json()['data']
    assert result['scope_estimate']['estimated_computable_product_count']==0
    with Session(c[0][1]) as s:
        s.add(SalesDaily(id=uuid4(),store_id=c[1].store_id,product_id=c[2],sales_date=date(2026,10,9),quantity=0));s.commit()
    result=read(c,'forecast').json()['data']
    assert result['scope_estimate']['estimated_computable_product_count']==1
    assert result['actions'][0]['availability']=='unknown'
    assert result['history_watermark'] is None
    configure_baseline(c)
    result=read(c,'forecast').json()['data']
    assert result['actions'][0]['availability']=='ready'


def test_known_valid_data_execution_unavailable_context_same_codes_and_versions(readiness):
    c=readiness;known_facts(c)
    response=read(c);assert response.status_code==200,response.text
    value=response.json()['data'];action=value['actions'][0]
    assert action['data_status']=='valid' and action['execution_status']=='unavailable' and not action['can_execute']
    assert action['result_assessment']=='NOT_ASSESSED' and value['history_watermark']=='2026-10-09'
    assert value['scope_estimate']['estimated_computable_product_count']==1
    assert any(i['code']=='SUPPLIER_TERM_MISSING' for i in action['warnings'])
    context=c[0][5].get(base(c)+'/planning-context');assert context.status_code==200,context.text
    ctx=context.json()['data']
    assert ctx['readiness']['reason_codes']==[i['code'] for i in action['blockers']]
    assert ctx['readiness']['scope_estimate']==value['scope_estimate']
    assert ctx['capabilities']['winner_selection'] is False and ctx['capabilities']['saved_requirements'] is True
    assert ctx['latest_business_date']=='2026-10-09' and ctx['defaults']['cutoff_date']=='2026-10-09'
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ForecastRun))==0


def test_seven_day_timeline_gap_local_exclusion_not_global_fee_concealment(readiness):
    c=readiness;ingredient,recipe=known_facts(c)
    with Session(c[0][1]) as s:
        s.get(Recipe,recipe).effective_to=date(2026,10,15);s.commit()
    value=read(c).json()['data'];excluded=value['scope_estimate']['excluded_products'][0]
    assert excluded['affected_dates']==['2026-10-16'] and 'RECIPE_PERIOD_GAP' in excluded['reason_codes']
    assert value['scope_estimate']['estimated_computable_product_count']==0
    assert read(c,'forecast').json()['data']['scope_estimate']['estimated_computable_product_count']==1


def test_declaration_stale_coverage_watermark_exact_and_global_unsupported(readiness):
    c=readiness;ingredient,recipe=known_facts(c)
    from app.models import InventoryLot
    with Session(c[0][1]) as s:
        s.add(InventoryLot(id=uuid4(),store_id=c[1].store_id,ingredient_id=ingredient,received_date=None,expiry_date=None,on_hand_quantity=1,unit='ml'));s.commit()
    value=read(c).json()['data'];assert 'INVENTORY_SCOPE_UNKNOWN' in value['scope_estimate']['excluded_products'][0]['reason_codes']
    with Session(c[0][1]) as s:
        sale=s.scalar(select(SalesDaily));sale.quantity=1;s.commit()
    assert read(c,'forecast').json()['data']['history_watermark'] is None
    with Session(c[0][1]) as s:
        row=s.scalar(select(ScopeDeclarationRecord).where(ScopeDeclarationRecord.source_record_key=='context'))
        payload=dict(row.payload);payload['declaration']={**payload['declaration'],'committed_inbound_state':'PRESENT_UNSUPPORTED'}
        s.add(ScopeDeclarationRecord(id=uuid4(),store_id=row.store_id,source_system_key=row.source_system_key,source_record_key=row.source_record_key,
            source_record_hash=row.source_record_hash,version=2,payload=payload,dependency_digest=row.dependency_digest,provenance={}));s.commit()
    assert 'COMMITTED_INBOUND_UNSUPPORTED' in [i['code'] for i in read(c).json()['data']['actions'][0]['blockers']]


def test_whole_response_permissions_and_action_not_granted_after_sensitive_reads(readiness):
    c=readiness;known_facts(c);staff=setup(c[0],'staff@example.test',store=False)
    with Session(c[0][1]) as s:
        member=StoreMembership(id=uuid4(),store_id=c[1].store_id,user_id=staff.user_id,role='STAFF',active=True);s.add(member);s.flush()
        for grant in ('planning.context.read','budget.read','sales.read','menu.read'):
            s.add(MembershipGrant(membership_id=member.id,permission=grant))
        mid=member.id;s.commit()
    login(c[0],'staff@example.test')
    denied=read(c,'menu,planning');assert denied.status_code==403 and denied.json()['data'] is None
    assert c[0][5].get(base(c)+'/planning-context').status_code==403
    import json
    from tests.integration.test_contextual_readiness import custom
    assert c[0][5].get(base(c)+'/planning-context',params={'planning_request':json.dumps(custom())}).status_code==403
    with Session(c[0][1]) as s:s.add(MembershipGrant(membership_id=mid,permission='procurement.cost.read'));s.commit()
    value=read(c).json()['data'];assert any(i['code']=='ACTION_NOT_GRANTED' for i in value['actions'][0]['blockers'])
    # D4 adds sourced impact wording (which may say "quantity"); prohibit raw
    # value fields throughout the payload rather than matching prose words.
    def keys(node):
        if isinstance(node,dict):return set(node).union(*(keys(v) for v in node.values()))
        if isinstance(node,list):return set().union(*(keys(v) for v in node))
        return set()
    assert not {'quantity','pack_cost','on_hand_quantity','unit_cost'} & keys(value)


def test_context_all_saved_invalid_active_and_archived_removed(readiness):
    c=readiness;assert cap(c,**{'If-None-Match':'*'}).status_code==201
    active=save(c).json()['data'];archived=save(c).json()['data']
    response=c[0][5].put(base(c)+'/planning-requirements/'+archived['saved_requirement_id'],json={'state':'archived'},
        headers={**c[3],'Idempotency-Key':str(uuid4()),'If-Match':'"'+archived['version']+'"'})
    assert response.status_code==200
    value=c[0][5].get(base(c)+'/planning-context').json()['data']
    assert [r['saved_requirement_id'] for r in value['saved_requirements']]==[active['saved_requirement_id']]
    assert value['requirements_modes'][2]['availability']=='available'


def test_safety_stock_is_explicitly_unsupported_only_in_computed_scope(readiness):
    from app.models import BusinessConstraint
    c=readiness;ingredient,_=known_facts(c)
    assert not any(b['code']=='MIN_SAFETY_STOCK_UNSUPPORTED' for b in read(c).json()['data']['actions'][0]['blockers'])
    with Session(c[0][1]) as s:
        s.add(BusinessConstraint(id=uuid4(),store_id=c[1].store_id,scope_type='INGREDIENT',scope_id=ingredient,
            constraint_type='MIN_SAFETY_STOCK',numeric_value=0,unit='ml',version=1,
            effective_from=date(2026,10,10),effective_to=None,active=True));s.commit()
    action=read(c).json()['data']['actions'][0]
    assert not action['can_execute'] and 'MIN_SAFETY_STOCK_UNSUPPORTED' in {b['code'] for b in action['blockers']}
    assert read(c,'forecast').json()['data']['actions'][0]['can_execute']


def test_get_contract_invalid_filters_and_canonical_readonly(readiness):
    c=readiness;known_facts(c)
    assert read(c,'menu',forecast_start_date='2026-10-10').status_code==422
    assert read(c,'forecast',forecast_start_date='0001-01-01').status_code==422
    assert read(c,'menu,menu').status_code==422
    writes=[]
    def observe(conn,cursor,sql,params,context,many):
        statement=sql.strip().lower()
        if statement.startswith(('insert','update','delete')) and not any(t in statement for t in ('auth_sessions','auth_rate_limits')):writes.append(sql)
    event.listen(c[0][1],'before_cursor_execute',observe)
    try:assert read(c).status_code==200
    finally:event.remove(c[0][1],'before_cursor_execute',observe)
    assert not writes


def test_context_unrepresentable_suggestion_is_null(readiness):
    from datetime import datetime,timezone
    c=readiness;c[0][4][0]=datetime(1,1,1,2,tzinfo=timezone.utc)
    # Keep the current authenticated session valid at the synthetic boundary.
    from app.models.auth import AuthSession
    with Session(c[0][1]) as s:
        session=s.scalar(select(AuthSession))
        session.issued_at=c[0][4][0]
        s.commit()
    response=c[0][5].get(base(c)+'/planning-context')
    assert response.status_code==200,response.text
    value=response.json()['data']
    assert value['defaults']['forecast_start_date'] is None and value['defaults']['cutoff_date'] is None
    assert value['readiness']['can_generate'] is False


def test_current_membership_revoked_during_detached_preflight_denies_snapshot(readiness,monkeypatch):
    c=readiness;known_facts(c)
    def revoke(prepared,serving):
        with Session(c[0][1]) as s:
            membership=s.scalar(select(StoreMembership).where(StoreMembership.user_id==c[1].user_id))
            membership.active=False;membership.authorization_revision+=1;s.commit()
        return None
    monkeypatch.setattr(c[0][5].app.state.forecast_serving,'assess',revoke)
    response=read(c)
    assert response.status_code==404 and response.json()['data'] is None
    assert response.json()['meta']=={}
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ForecastRun))==0


def test_active_menu_bound_includes_products_without_history(readiness):
    c=readiness;known_facts(c)
    with Session(c[0][1]) as s:
        s.add_all(Product(id=uuid4(),store_id=c[1].store_id,name='No real observations '+str(i),selling_unit='cup',active=True) for i in range(50))
        s.commit()
    response=read(c);assert response.status_code==200,response.text
    value=response.json()['data']
    assert value['scope_estimate']['menu_product_count']==51
    assert value['scope_estimate']['estimated_computable_product_count']==1
    assert 'RESOURCE_LIMIT_EXCEEDED' in {i['code'] for i in value['actions'][0]['blockers']}
    context=c[0][5].get(base(c)+'/planning-context').json()['data']
    assert len(context['products'])==51 and context['readiness']['scope_estimate']==value['scope_estimate']


def test_unavailable_forecast_composition_keeps_valid_data_status(readiness):
    c=readiness;known_facts(c)
    c[0][5].app.state.readiness=ReadinessReads(c[0][2],None)
    response=read(c,'forecast');assert response.status_code==200,response.text
    action=response.json()['data']['actions'][0]
    assert action['data_status']=='valid' and action['execution_status']=='unavailable'
    assert action['can_execute'] is False
    assert 'EXECUTION_UNAVAILABLE' in {i['code'] for i in action['blockers']}
