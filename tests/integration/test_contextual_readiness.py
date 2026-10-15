"""D4 current contextual GET assessment; portable guarded PostgreSQL fixtures."""
import json
from uuid import uuid4
from datetime import date
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow, config, env, demand_and_offer, submit
from tests.integration.test_planning_configuration_public import base,save,full
from app.models.planning_configuration import PlanningDefault
from app.application.use_cases.readiness import ReadinessReads


def contextual(flow, body=None):
    c=flow[0]
    c[0][5].app.state.readiness=ReadinessReads(c[0][2],c[0][5].app.state.forecast_serving,planning_available=lambda:True)
    params={'planning_request':json.dumps(body)} if body is not None else {}
    response=c[0][5].get(base(c)+'/planning-context',params=params)
    assert response.status_code==200,response.text
    return response.json()['data']


def custom(**requirements):
    return dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements={
        'paths':[dict(path='BASE',min_fill_rate_percent='0',product_overrides=[])],**requirements})


def test_full_custom_independent_of_missing_default(flow):
    c=flow[0]
    with Session(c[0][1]) as s:s.delete(s.get(PlanningDefault,c[1].store_id));s.commit()
    default=contextual(flow)
    assert not default['readiness']['can_generate']
    assert default['readiness']['status']=='not_ready'
    value=contextual(flow,custom(budget_limit='0'))
    assert value['readiness']['can_generate']
    assert value['readiness']['assessment']['input_scope']=='SUPPLIED_REQUEST'
    assert value['readiness']['assessment']['configuration_status']=='RESOLVED'
    assert submit(c,body=custom(budget_limit='0')).status_code==202


def test_offer_omission_is_warning_in_current_readiness(flow):
    omitted=demand_and_offer(flow,cost='0',system='omitted')
    demand_and_offer(flow,cost='2',system='eligible')
    value=contextual(flow)
    assert value['readiness']['can_generate'],value['readiness']
    assessment=value['readiness']['assessment']
    warnings=assessment['warnings']
    warning=next(w for w in warnings if w['code']=='OFFER_OMITTED')
    assert warning['details']['entity_id']==str(omitted)
    assert warning['details']['version']==1
    assert warning['details']['proof_scope']=='CAPTURED_ELIGIBLE_OFFERS_ONLY'
    assert len(warnings)==len({json.dumps(w,sort_keys=True) for w in warnings})
    assert len(warnings)==len({(w['code'],w['entity_id'],tuple(w['affected_dates'])) for w in warnings})


@pytest.mark.parametrize('patch,version,code',[
    ({'paths':[{'path':'BASE'}]},None,'DEFAULT_REQUIREMENTS_VERSION_REQUIRED'),
    ({'paths':[{'path':'BASE'}]},'stale','DEFAULT_REQUIREMENTS_CHANGED'),
    ({'paths':[{'path':'HIGH'}]},'default-1','DEFAULT_VALUE_UNAVAILABLE'),
    ({'budget_limit':'101'},None,'BUDGET_LIMIT_EXCEEDS_CEILING'),
    ({'budget_limit':'0'},None,None),
    ({'budget_limit':None},None,None),
    ({},None,None),
])
def test_partial_overrides_budget_and_stale_versions_use_resolver(flow,patch,version,code):
    request=custom(**patch)
    if version is not None:request['default_requirements_version']=version
    value=contextual(flow,request)['readiness']
    codes=set(value['reason_codes'])
    assert value['can_generate']==(code is None),value
    if code:assert code in codes
    response=submit(flow[0],body=request)
    assert response.status_code==(202 if code is None else 409 if code=='DEFAULT_REQUIREMENTS_CHANGED' else 422),response.text


def test_full_custom_ignores_invalid_unused_defaults_and_partial_requires_missing_default(flow):
    c=flow[0]
    with Session(c[0][1]) as s:
        s.get(PlanningDefault,c[1].store_id).requirements_json={'budget_limit':None,'paths':[{'path':'BASE','min_fill_rate_percent':'90','product_overrides':[]}]}
        s.commit()
    assert contextual(flow,custom())['readiness']['can_generate']
    assert not contextual(flow)['readiness']['can_generate']
    with Session(c[0][1]) as s:s.delete(s.get(PlanningDefault,c[1].store_id));s.commit()
    request=custom(paths=[{'path':'BASE'}]);request['default_requirements_version']='default-1'
    assert 'DEFAULT_CONFIGURATION_UNAVAILABLE' in contextual(flow,request)['readiness']['reason_codes']


@pytest.mark.parametrize('kind',['active','archived','missing','over_cap','inactive_product'])
def test_saved_context_matches_current_resolver_and_store_scope(flow,kind):
    c=flow[0]
    body=full(requirements=custom()['requirements'])
    if kind=='over_cap':body['requirements']['budget_limit']='100'
    saved=save(c,body).json()['data']
    ident=saved['saved_requirement_id']
    if kind=='missing':ident=str(uuid4())
    if kind=='archived':
        response=c[0][5].put(base(c)+'/planning-requirements/'+ident,json={'state':'archived'},
            headers={**c[3],'Idempotency-Key':str(uuid4()),'If-Match':'"'+saved['version']+'"'})
        assert response.status_code==200,response.text
    from app.models.planning_configuration import PlanningBudget
    from app.models import Product
    with Session(c[0][1]) as s:
        s.delete(s.get(PlanningDefault,c[1].store_id))
        if kind=='over_cap':s.get(PlanningBudget,c[1].store_id).amount='1'
        if kind=='inactive_product':s.get(Product,c[2]).active=False
        s.commit()
    request=dict(requirements_mode='saved',saved_requirement_id=ident,forecast_start_date='2026-10-10')
    value=contextual(flow,request)['readiness']
    assert value['can_generate']==(kind=='active'),value
    if kind=='archived':assert 'SAVED_REQUIREMENTS_ARCHIVED' in value['reason_codes']
    if kind=='missing':assert 'SAVED_REQUIREMENT_NOT_FOUND' in value['reason_codes']
    response=submit(c,body=request)
    assert response.status_code==(202 if kind=='active' else 422),response.text


def test_same_snapshot_r01_c01_today_and_get_never_executes(flow,monkeypatch):
    from app.models import ForecastRun,PlanningRun,Product
    from app.application.use_cases.today import TodayReads
    from app.application.contracts.model_serving import ServingPolicy
    from app.models.model_serving import ModelServingConfiguration
    c=flow[0]
    with Session(c[0][1]) as s:
        s.get(ModelServingConfiguration,c[1].store_id).configuration_json=ServingPolicy(mode='TRAINED',artifact_identity=None,
            dependency_versions=(),fallback_policy='ADR015_RECOGNIZED_ONLY').model_dump(mode='json')
        s.add(Product(id=uuid4(),store_id=c[1].store_id,name='No history',selling_unit='cup',active=True));s.commit()
    def forbidden(*a,**k):pytest.fail('GET invoked execution')
    import scipy.optimize
    monkeypatch.setattr(scipy.optimize,'milp',forbidden)
    monkeypatch.setattr(c[0][5].app.state.forecast_serving,'serve',forbidden)
    ctx=contextual(flow)
    r=c[0][5].get(base(c)+'/readiness',params={'actions':'planning'}).json()['data']
    response=c[0][5].get(base(c)+'/today',params={'section':'readiness'})
    assert response.status_code==200,response.text
    value=response.json()['data']['sections']['readiness']['value']
    action=next(a for a in value['actions'] if a['action']=='planning')
    assert action==r['actions'][0]
    assert ctx['readiness']['assessment']==r['planning_assessment']
    assert ctx['readiness']['forecast']==r['forecast_assessment']
    assert r['forecast_assessment']['quality_status']=='not_evaluated'
    assert r['forecast_assessment']['selection_reason']=='NO_ARTIFACT'
    assert any(w['code']=='BASELINE_FALLBACK' for w in r['actions'][0]['warnings'])
    assert r['scope_estimate']['menu_product_count']==2 and r['scope_estimate']['estimated_computable_product_count']==1
    assert r['planning_assessment']['input_scope']=='DEFAULT_CONFIGURATION'
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ForecastRun))==0
        assert s.scalar(select(func.count()).select_from(PlanningRun))==0


@pytest.mark.parametrize('payload',['null','{}','{"requirements_mode":"custom","requirements":{"paths":[{"path":"BASE","min_fill_rate_percent":null}]},"forecast_start_date":"2026-10-10"}'])
def test_invalid_context_is_not_a_hypothetical_default(flow,payload):
    c=flow[0]
    contextual(flow)
    response=c[0][5].get(base(c)+'/planning-context',params={'planning_request':payload})
    assert response.status_code==422 and response.json()['data'] is None


def test_context_query_scope_conflict_foreign_store_and_known_budget_absence(flow):
    from app.models.planning_configuration import PlanningBudget
    c=flow[0];contextual(flow)
    params={'planning_request':json.dumps(custom()),'actions':'planning','forecast_start_date':'2026-10-11'}
    assert c[0][5].get(base(c)+'/readiness',params=params).status_code==422
    params.pop('forecast_start_date');params['actions']='forecast'
    assert c[0][5].get(base(c)+'/readiness',params=params).status_code==422
    assert c[0][5].get(f'/api/v1/stores/{uuid4()}/planning-context',params={'planning_request':json.dumps(custom())}).status_code==404
    with Session(c[0][1]) as s:s.delete(s.get(PlanningBudget,c[1].store_id));s.commit()
    value=contextual(flow,custom(budget_limit='0'))['readiness']
    assert not value['can_generate'] and 'BUDGET_CEILING_UNKNOWN' in value['reason_codes']
