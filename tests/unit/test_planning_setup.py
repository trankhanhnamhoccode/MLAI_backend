"""Contract/hand-expected resolver behavior; no DB or implicit policy persistence."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError
from app.application.contracts.planning_setup import PlanningRequest, PlanningConfiguration, ResolvedPlanningSetup
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations, prepare_planning_pipeline, execute_planning_pipeline
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2, SyntheticSnapshotSourceV2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch


def source_case():
    r, facts = synthetic_case_v2()
    source = dict(store_id=r.store_id, currency=facts.facts.store.currency,
        timezone=facts.facts.store.timezone, read_at=facts.facts.captured_at,
        configuration_version='SYNTHETIC-config/1', provenance='SYNTHETIC in-memory config',
        consistency='UNSPECIFIED', defaults=dict(version='defaults/1', updated_at=facts.facts.captured_at,
            requirements=dict(paths=[dict(path='BASE', min_fill_rate_percent='95', product_overrides=[])], budget_limit=None)),
        budget_ceiling=dict(amount='5', currency=facts.facts.store.currency, version='ceiling/1',
            updated_at=facts.facts.captured_at, provenance='SYNTHETIC budget ceiling'), saved=None,
        products=[p.model_dump() for p in facts.catalog], policy=r.procurement.policy.model_dump())
    return r, facts, source


def default_request():
    r, _, _ = source_case()
    return dict(requirements_mode='default', forecast_start_date=(r.cutoff_date+timedelta(days=1)).isoformat(), default_requirements_version='defaults/1')


def custom(paths=None, budget='OMIT'):
    request = default_request();request.pop('default_requirements_version');request['requirements_mode']='custom'
    request['requirements'] = dict(paths=paths if paths is not None else [dict(path='HIGH', min_fill_rate_percent='90', product_overrides=[])])
    if budget != 'OMIT': request['requirements']['budget_limit'] = budget
    return request


def saved_case():
    _, facts, source = source_case();saved_id=UUID(int=3663)
    source['saved']=dict(store_id=source['store_id'],saved_requirement_id=saved_id,version='saved/3',name='Synthetic saved',
        updated_at=facts.facts.captured_at-timedelta(days=2),
        requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='80',product_overrides=[])],budget_limit=None))
    q=default_request();q.pop('default_requirements_version');q.update(requirements_mode='saved',saved_requirement_id=str(saved_id))
    return q, source


def resolved(request, source):
    outcome=resolve_planning_setup(request,source)
    assert outcome.status=='RESOLVED',outcome.errors
    return outcome.resolution


def invalid(request, source, code=None, field=None):
    outcome=resolve_planning_setup(request,source)
    assert outcome.status=='INVALID' and outcome.resolution is None
    if code: assert code in {e.code for e in outcome.errors}
    if field: assert any(field in e.field for e in outcome.errors)
    return outcome


def test_default_hand_expected_declared_base95_ceiling_and_provenance():
    _,_,s=source_case();r=resolved(default_request(),s)
    assert r.requirements.paths[0].minimum==Decimal('.95')
    assert r.requirements.paths[0].overrides==() and r.budget.amount==5
    assert r.default_reference.version=='defaults/1' and r.saved_reference is None
    assert r.configuration.consistency=='UNSPECIFIED' and r.decision_readiness=='NOT_ASSESSED'
    assert r.cutoff_date+timedelta(days=7)==r.forecast_end_date


@pytest.mark.parametrize('field,value',[('strategy','lean'),('model','x'),('forecast_id',str(UUID(int=1))),('product_ids',[]),('horizon_days',7),('currency','VND'),('cutoff_date','2026-01-01'),('unknown',True)])
def test_forbidden_customer_fields(field,value):
    _,_,s=source_case();q=default_request();q[field]=value;invalid(q,s,field=field)


@pytest.mark.parametrize('mode,extra',[('default',{'requirements':None}),('default',{'saved_requirement_id':None}),('custom',{'saved_requirement_id':str(UUID(int=1))}),('saved',{'requirements':{}})])
def test_mode_fields_forbidden_even_null(mode,extra):
    _,_,s=source_case();q=custom() if mode=='custom' else saved_case()[0] if mode=='saved' else default_request()
    q.update(extra);invalid(q,s)


@pytest.mark.parametrize('q',[{'requirements_mode':'custom','forecast_start_date':'2026-10-09'}, {'requirements_mode':'saved','forecast_start_date':'2026-10-09'}, {'forecast_start_date':'2026-10-09'}, {'requirements_mode':'default'}])
def test_required_fields(q):
    invalid(q,source_case()[2])


def test_partial_custom_uses_same_path_default_only_and_stale_check():
    _,_,s=source_case();q=custom([{'path':'BASE'}]);q['default_requirements_version']='defaults/1'
    r=resolved(q,s);assert r.requirements.paths[0].minimum==Decimal('.95') and r.default_reference
    q['default_requirements_version']='stale';invalid(q,s,'DEFAULT_REQUIREMENTS_CHANGED','default_requirements_version')
    q.pop('default_requirements_version');invalid(q,s,'DEFAULT_REQUIREMENTS_VERSION_REQUIRED')


@pytest.mark.parametrize('path',['HIGH','LOW'])
def test_missing_same_path_default_never_inherits_base(path):
    q=custom([{'path':path}]);q['default_requirements_version']='defaults/1'
    invalid(q,source_case()[2],'DEFAULT_VALUE_UNAVAILABLE', 'requirements.paths[0].min_fill_rate_percent')


def test_full_custom_and_budget_inheritance_need_no_default_version():
    _,_,s=source_case();s['defaults']=None;q=custom();q['default_requirements_version']='unused-stale'
    r=resolved(q,s);assert r.default_reference is None and r.budget.amount==5
    assert r.requirements.paths[0].minimum==Decimal('.90')


def test_overrides_omit_inherit_but_explicit_array_replaces_no_merge():
    _,f,s=source_case();p=str(f.catalog[0].product_id)
    q=custom([dict(path='BASE',min_fill_rate_percent='85')]);q['default_requirements_version']='defaults/1'
    assert resolved(q,s).requirements.paths[0].overrides==()
    assert resolved(q,s).default_reference is not None
    q['requirements']['paths'][0]['product_overrides']=[]
    assert resolved(q,s).requirements.paths[0].overrides==() and resolved(q,s).default_reference is None
    q['requirements']['paths'][0]['product_overrides']=[dict(product_id=p,min_fill_rate_percent='99')]
    assert resolved(q,s).requirements.paths[0].overrides[0].target==Decimal('.99')


@pytest.mark.parametrize('field',['min_fill_rate_percent','product_overrides'])
def test_explicit_null_not_missing(field):
    q=custom();q['requirements']['paths'][0][field]=None
    invalid(q,source_case()[2],field=field)


@pytest.mark.parametrize('budget,expected',[('OMIT','5'),(None,'5'),('0','0'),('3.000','3')])
def test_budget_omitted_null_zero_private(budget,expected):
    assert resolved(custom(budget=budget),source_case()[2]).budget.amount==Decimal(expected)


def test_budget_unknown_excess_and_currency_corruption_reject_not_clamp():
    _,_,s=source_case();invalid(custom(budget='5.000000000000000001'),s,'BUDGET_LIMIT_EXCEEDS_CEILING')
    s['budget_ceiling']=None;invalid(custom(budget='0'),s,'BUDGET_CEILING_UNKNOWN')
    _,_,s=source_case();s['budget_ceiling']['currency']='USD';invalid(custom(),s,'CONFIGURATION_INVALID')


def test_saved_preserves_levels_version_and_late_binding_cap_with_warning():
    q,s=saved_case();before=deepcopy(s);s['budget_ceiling']['amount']='4'
    q['default_requirements_version']='unused-stale';r=resolved(q,s)
    assert r.requirements.paths[0].minimum==Decimal('.8') and r.budget.amount==4
    assert r.default_reference is None and r.saved_reference.version=='saved/3'
    assert r.warnings[0].code=='DEFAULT_CHANGED_SINCE_SAVED_UPDATE'
    assert r.warnings[0].default_updated_at==s['defaults']['updated_at']
    assert s['saved']==before['saved']
    s['defaults']=None
    assert resolved(q,s).warnings[0].code=='DEFAULT_CHANGE_HISTORY_UNKNOWN'


def test_saved_equal_timestamp_no_warning_unknown_history_no_fake_timestamp():
    q,s=saved_case();s['saved']['updated_at']=s['defaults']['updated_at']
    assert resolved(q,s).warnings==()
    s['saved']['updated_at']=None;r=resolved(q,s)
    assert r.warnings[0].saved_updated_at is None and r.warnings[0].code=='DEFAULT_CHANGE_HISTORY_UNKNOWN'


def test_saved_wrong_id_store_invalid_record_and_private_budget():
    q,s=saved_case();q['saved_requirement_id']=str(UUID(int=999));invalid(q,s,'SAVED_REQUIREMENT_NOT_FOUND')
    q,s=saved_case();s['saved']['store_id']=UUID(int=888);invalid(q,s,'SAVED_REQUIREMENT_WRONG_STORE')
    q,s=saved_case();s['saved']['requirements']['paths'][0].pop('product_overrides');invalid(q,s,'CONFIGURATION_INVALID')
    q,s=saved_case();s['saved']['requirements']['budget_limit']='6';invalid(q,s,'BUDGET_LIMIT_EXCEEDS_CEILING')


@pytest.mark.parametrize('kind',['unknown','inactive','foreign','duplicate'])
def test_override_product_reference_validation(kind):
    _,f,s=source_case();p=str(f.catalog[0].product_id)
    if kind=='unknown':p=str(UUID(int=999))
    if kind=='inactive':s['products'][0]['active']=False;s['products'].append(dict(s['products'][0],product_id=UUID(int=999),active=True))
    if kind=='foreign':s['products'][0]['store_id']=UUID(int=999)
    overrides=[dict(product_id=p,min_fill_rate_percent='20')]
    if kind=='duplicate':overrides*=2
    q=custom([dict(path='HIGH',min_fill_rate_percent='10',product_overrides=overrides)])
    invalid(q,s)


@pytest.mark.parametrize('text',[1,1.2,True,Decimal('1'),'NaN','Infinity','-1','+1','01','1e-2','1%',' 1','100.0001','0.'+'1'*33,'1000'])
def test_invalid_wire_percent(text):
    q=custom();q['requirements']['paths'][0]['min_fill_rate_percent']=text;invalid(q,source_case()[2])


def test_exact_tiny_percentage_and_money_ambient_context_independence():
    q=custom(budget='4.123456789012345678');q['requirements']['paths'][0]['min_fill_rate_percent']='0.'+'0'*31+'1'
    s=source_case()[2]
    with localcontext() as ctx:
        ctx.prec=2;ctx.Emin=-3;ctx.Emax=3;ctx.traps[__import__('decimal').Inexact]=True
        r=resolved(q,s)
    assert r.requirements.paths[0].minimum==Decimal('1e-34')
    assert r.budget.amount==Decimal('4.123456789012345678')


@pytest.mark.parametrize('text',['1000000000000000000','0.'+'1'*19,0,False,'-0','1e1'])
def test_money_digit_and_wire_limits(text):
    invalid(custom(budget=text),source_case()[2])


@pytest.mark.parametrize('start',['0001-01-01','9999-12-26','2026-02-30','2026-1-01','2026-10-09T00:00:00Z',True])
def test_dates_invalid_or_overflow(start):
    q=custom();q['forecast_start_date']=start;invalid(q,source_case()[2],field='forecast_start_date')


@pytest.mark.parametrize('start',['0001-01-02','9999-12-25'])
def test_supported_extreme_dates(start):
    q=custom();q['forecast_start_date']=start;r=resolved(q,source_case()[2]);assert r.forecast_end_date==date.fromisoformat(start)+timedelta(days=6)


@pytest.mark.parametrize('paths',[[],[dict(path='BASE',min_fill_rate_percent='1',product_overrides=[])]*2])
def test_path_coverage_unique_nonempty(paths):
    invalid(custom(paths),source_case()[2])


def test_request_size_product_and_override_resource_limits():
    s=source_case()[2];invalid(b' '*65537,s,'RESOURCE_LIMIT_EXCEEDED')
    q=custom();q['requirements']['paths'][0]['product_overrides']=[dict(product_id=str(UUID(int=100+n)),min_fill_rate_percent='1') for n in range(51)]
    invalid(q,s,'RESOURCE_LIMIT_EXCEEDED')
    s['products']=[dict(s['products'][0],product_id=UUID(int=100+n)) for n in range(51)]
    invalid(custom(),s,'RESOURCE_LIMIT_EXCEEDED')


def test_default_missing_corrupt_policy_timezone_and_version():
    s=source_case()[2];s['defaults']=None;invalid(default_request(),s,'DEFAULT_CONFIGURATION_UNAVAILABLE')
    s=source_case()[2];s['defaults']['requirements']['paths'][0]['min_fill_rate_percent']='100';invalid(default_request(),s,'DEFAULT_CONFIGURATION_INVALID')
    s=source_case()[2];s['timezone']='Not/AZone';invalid(custom(),s,'CONFIGURATION_INVALID')
    q=custom();q['default_requirements_version']='x'*129;invalid(q,source_case()[2])


def test_presence_detachment_no_save_and_forged_revalidation():
    q=custom();s=source_case()[2];r=resolved(q,s);before=r.model_dump()
    q['requirements']['paths'][0]['min_fill_rate_percent']='1';s['products'].clear();s['budget_ceiling']['amount']='0'
    assert r.model_dump()==before
    assert 'budget_limit' not in r.request.requirements.model_fields_set
    null=resolved(custom(budget=None),source_case()[2]);assert 'budget_limit' in null.request.requirements.model_fields_set
    source=PlanningConfiguration.model_validate(source_case()[2]);bad=source.model_copy(update={'budget_ceiling':None})
    invalid(custom(),bad,'BUDGET_CEILING_UNKNOWN')
    req=PlanningRequest.model_validate(custom());bad=req.model_copy(update={'requirements_mode':'default'})
    invalid(bad,source)
    forged=r.model_copy(update={'budget':r.budget.model_copy(update={'amount':Decimal('0')})})
    with pytest.raises(ValidationError):ResolvedPlanningSetup.model_validate(forged)


def test_programming_error_not_converted_to_validation(monkeypatch):
    from app.application.use_cases import planning_setup as module
    def bug(*args):raise RuntimeError('programming fault')
    monkeypatch.setattr(module,'_project',bug)
    with pytest.raises(RuntimeError,match='programming fault'):module.resolve_planning_setup(custom(),source_case()[2])


def declarations(request):
    return PlanningPipelineDeclarations(forecast_run_id=request.forecast_run_id, inventory_scope=request.inventory_scope,
        committed_inbound_state=request.committed_inbound_state,committed_inbound_provenance=request.committed_inbound_provenance,
        no_additional_orders_provenance=request.no_additional_orders_provenance,snapshot_policy=request.snapshot_policy,
        **request.procurement.model_dump(exclude={'policy','budget','budget_ceiling','budget_version'}))


def test_resolver_to_native_pipeline_actual_levels_budget_and_no_relookup():
    old,facts,s=source_case();q=custom([dict(path='BASE',min_fill_rate_percent='80',product_overrides=[])],budget='4')
    r=resolved(q,s);s['budget_ceiling']['amount']='999';s['defaults']=None
    output=execute_planning_pipeline(r,declarations(old),SyntheticSnapshotSourceV2(facts),NativeProductSearch,lambda:facts.facts.captured_at)
    assert output.capture.request.requirements.paths[0].minimum==Decimal('.8')
    assert output.procurement.input.budget.amount==4 and output.capture.request.procurement.budget_ceiling.amount==5
    assert output.procurement.input.requirements==r.requirements
    assert output.outcome=='RECOMMENDATION_AVAILABLE'


def test_missing_recipe_active_override_retained_for_not_evaluated_audit():
    from tests.unit.test_decision_pipeline_v2 import pair
    from app.application.contracts.decision_capture_v2 import OperationalFactsV2
    old,facts=pair();s=source_case()[2];s['products']=[p.model_dump() for p in facts.catalog]
    second=facts.catalog[1].product_id;q=custom([dict(path='BASE',min_fill_rate_percent='80',product_overrides=[dict(product_id=str(second),min_fill_rate_percent='90')])])
    r=resolved(q,s);d=facts.model_dump();d['facts']['recipes']=[p for p in d['facts']['recipes'] if p['product_id']!=second]
    output=execute_planning_pipeline(r,declarations(old),SyntheticSnapshotSourceV2(OperationalFactsV2.model_validate(d)),NativeProductSearch,lambda:facts.facts.captured_at)
    assert output.capture.request.requirements==r.requirements
    assert output.capture.override_assessments[0].status=='NOT_EVALUATED'
    assert output.capture.exclusions[0].product_id==second


def test_bridge_rejects_forged_output_and_requires_explicit_declarations():
    old,_,s=source_case();r=resolved(custom(),s)
    with pytest.raises(ValidationError):prepare_planning_pipeline(r.model_copy(update={'cutoff_date':date(2000,1,1)}),declarations(old))
    with pytest.raises(ValidationError):PlanningPipelineDeclarations.model_validate({'forecast_run_id':old.forecast_run_id})
    unknown=declarations(old).model_copy(update={'payable_fee_coverage':'UNKNOWN'})
    assert prepare_planning_pipeline(r,unknown).procurement.payable_fee_coverage=='UNKNOWN'


def test_retained_round_trip_preserves_every_omitted_vs_null_field():
    q=custom([dict(path='BASE')]);q['default_requirements_version']='defaults/1'
    r=resolved(q,source_case()[2])
    reconstructed=ResolvedPlanningSetup.model_validate_json(r.model_dump_json())
    assert reconstructed==r
    assert reconstructed.request.model_fields_set==r.request.model_fields_set
    assert reconstructed.request.requirements.paths[0].model_fields_set=={'path'}
    assert 'budget_limit' not in reconstructed.request.requirements.model_fields_set
    null=resolved(custom(budget=None),source_case()[2])
    assert 'budget_limit' in ResolvedPlanningSetup.model_validate_json(null.model_dump_json()).request.requirements.model_fields_set


@pytest.mark.parametrize('raw',[b'{',b'\xff',b'null',b'[]'])
def test_raw_json_bad_or_nonobject_rejected_without_raw_value(raw):
    outcome=invalid(raw,source_case()[2])
    assert all(e.message=='Invalid field for planning contract' or e.message=='Request is not valid JSON' for e in outcome.errors)


def test_raw_json_request_uses_exact_wire_values():
    import json
    q=custom(budget='0');r=resolved(json.dumps(q).encode(),source_case()[2])
    assert r.budget.amount==0


def test_zero_rate_and_overrides_above_below_common_are_replacements():
    _,f,s=source_case();pid=str(f.catalog[0].product_id)
    for common,override in [('0','100'),('100','0'),('50','50')]:
        r=resolved(custom([dict(path='BASE',min_fill_rate_percent=common,product_overrides=[dict(product_id=pid,min_fill_rate_percent=override)])]),s)
        assert r.requirements.paths[0].minimum==Decimal(common)/100
        assert r.requirements.paths[0].overrides[0].target==Decimal(override)/100


def test_copied_constructed_invalid_nested_numeric_revalidates_at_boundary():
    q=PlanningRequest.model_validate(custom());p=q.requirements.paths[0]
    broken=p.model_copy(update={'min_fill_rate_percent':True})
    constructed=PlanningRequest.model_construct(requirements_mode='custom',forecast_start_date=q.forecast_start_date,
        requirements=q.requirements.model_copy(update={'paths':(broken,)}))
    invalid(constructed,source_case()[2],field='min_fill_rate_percent')


def test_unknown_declarations_remain_blockers_and_do_not_become_defaults():
    old,f,s=source_case();r=resolved(custom([dict(path='BASE',min_fill_rate_percent='80',product_overrides=[])]),s)
    d=declarations(old).model_copy(update={'payable_fee_coverage':'UNKNOWN'})
    output=execute_planning_pipeline(r,d,SyntheticSnapshotSourceV2(f),lambda *a:pytest.fail('blocked fees must not invoke solver'),lambda:f.facts.captured_at)
    assert output.outcome=='CAPTURE_BLOCKED'
    assert output.procurement is None


def test_corrupt_default_cannot_be_inherited_as_custom_policy():
    _,_,s=source_case();s['defaults']['requirements']['paths'][0]['min_fill_rate_percent']='100'
    q=custom([dict(path='BASE')]);q['default_requirements_version']='defaults/1'
    invalid(q,s,'DEFAULT_CONFIGURATION_INVALID')
    # A full custom uses neither these values nor their version.
    assert resolved(custom(),s).default_reference is None


def test_duplicate_json_fields_rejected():
    invalid(b'{"requirements_mode":"default","requirements_mode":"saved"}',source_case()[2],'INVALID_REQUEST')


def test_bridge_known_offer_resource_limit_rejects_forged_oversized_declaration():
    old,_,s=source_case();r=resolved(custom(),s);d=declarations(old)
    forged=d.model_copy(update={'offers':(d.offers[0],)*101})
    with pytest.raises(ValidationError) as caught:prepare_planning_pipeline(r,forged)
    assert any(e['loc']==('offers',) and e['type']=='too_long' for e in caught.value.errors())
