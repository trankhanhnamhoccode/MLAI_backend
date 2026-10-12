"""Hand expectations and boundary failures for opt-in operational /2."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
import pytest
from pydantic import ValidationError
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2, OperationalPipelineResultV2
from app.application.contracts.decision_execution import PreparedDecisionInput
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_operational_pipeline_v2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from scripts.decision_capture_v2_demo_cases import synthetic_case_v2, SyntheticSnapshotSourceV2
from tests.unit.test_procurement_v2 import NoCandidate


def run(request,facts,factory=NativeProductSearch):
    return execute_operational_pipeline_v2(request,SyntheticSnapshotSourceV2(facts),factory,lambda:facts.facts.captured_at)


def rehash(data):
    f=data['facts']['forecast'];p=PreparedForecastInput.model_validate(f['retained'])
    f['retained_digest']=f['input_fingerprint']=serialize_prepared(p).digest


def pair(shared=True):
    request,facts=synthetic_case_v2();d=facts.model_dump();f=d['facts'];p=f['products'][0];second=UUID(int=777)
    f['products']=[*f['products'],p|{'product_id':second,'selling_unit':'piece'}]
    d['catalog']=[*d['catalog'],d['catalog'][0]|{'product_id':second,'selling_unit':'piece','name':'SYNTHETIC second'}]
    recipe=deepcopy(f['recipes'][0]);recipe.update(id=UUID(int=778),product_id=second)
    if not shared:
        ingredient=UUID(int=779);f['ingredients']=[*f['ingredients'],f['ingredients'][0]|{'ingredient_id':ingredient}]
        d['ingredient_scope_ids']=[*d['ingredient_scope_ids'],ingredient]
        recipe['lines'][0]['ingredient_id']=ingredient
    f['recipes']=[*f['recipes'],recipe]
    fc=f['forecast'];fc['retained']['request']['product_ids']=[*fc['retained']['request']['product_ids'],second]
    fc['retained']['products']=[*fc['retained']['products'],dict(product_id=second,selling_unit='piece')]
    fc['predictions']=[*fc['predictions'],*[p|{'id':UUID(int=9000+n),'product_id':second} for n,p in enumerate(list(fc['predictions']))]]
    rehash(d)
    r=request.model_dump()
    if not shared:
        r['inventory_scope']=[*r['inventory_scope'],dict(ingredient_id=ingredient,state='CONFIRMED_EMPTY',provenance='SYNTHETIC verified empty')]
    return OperationalDecisionInputV2.model_validate(r),OperationalFactsV2.model_validate(d)


def test_native_capture_to_selector_explicit_effective_values():
    r,f=synthetic_case_v2();result=run(r,f)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert result.capture.prepared.capture_version==2
    assert result.capture.operational_basis.kind=='CURRENT_CAPTURE'
    assert result.procurement.input.requirements==r.requirements
    assert result.selection.winner_token in result.selection.eligible_tokens
    assert result.capture.request.procurement.budget_version=='SYNTHETIC-budget-v1'
    assert result.comparison.source==result.procurement
    assert result.timing.total_seconds>=result.timing.capture_preparation_seconds+result.timing.engine_seconds
    assert result.timing.output_revalidation_seconds>0
    assert result.decision_readiness=='NOT_ASSESSED'


def test_multi_path_override_mixed_units_no_mutation():
    r,f=pair();d=r.model_dump();p=f.catalog[1].product_id
    d['requirements']['paths']=[dict(path='BASE',minimum='.1',overrides=[dict(product_id=p,target='.05')]),dict(path='HIGH',minimum='.01',overrides=[])]
    r=OperationalDecisionInputV2.model_validate(d);before=f.model_dump();result=run(r,f)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert {p.selling_unit for p in result.capture.prepared.products}=={'cup','piece'}
    assert result.capture.override_assessments[0].status=='COMPUTED_SCOPE'
    assert result.procurement.input.requirements==r.requirements
    assert len(result.bom.paths)==3 and f.model_dump()==before


def test_partial_missing_recipe_override_not_evaluated_and_original_kept():
    r,f=pair();d=f.model_dump();second=f.catalog[1].product_id
    d['facts']['recipes']=[p for p in d['facts']['recipes'] if p['product_id']!=second]
    q=r.model_dump();q['requirements']['paths'][0]['overrides']=[dict(product_id=second,target='1')]
    r=OperationalDecisionInputV2.model_validate(q);result=run(r,OperationalFactsV2.model_validate(d))
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert len(result.capture.menu)==2 and len(result.capture.computed_product_ids)==1
    assert result.capture.exclusions[0].product_id==second and len(result.capture.exclusions[0].affected_dates)==7
    assert result.capture.override_assessments[0].status=='NOT_EVALUATED'
    assert result.capture.request.requirements.paths[0].overrides[0].product_id==second
    assert result.procurement.input.requirements.paths[0].overrides==()
    assert all(p.product_id!=second for p in result.procurement.input.prepared.products)


def test_shared_ingredient_blocker_all_excluded_no_fake_engine():
    r,f=pair();d=r.model_dump();d['inventory_scope'][0]['state']='UNKNOWN'
    result=run(OperationalDecisionInputV2.model_validate(d),f,lambda *a:pytest.fail('solver must not run'))
    assert result.outcome=='NO_COMPUTABLE_PRODUCTS' and len(result.capture.exclusions)==2
    assert result.procurement is None and result.selection is None
    assert all(any(p.code=='INVENTORY_BALANCE_MISSING' for p in e.reasons) for e in result.capture.exclusions)


def test_unknown_scope_global_blocker_not_guessed():
    r,f=synthetic_case_v2();d=f.model_dump();d['problems']=[dict(code='UNKNOWN_GRAPH',kind='DATA_BLOCKER',entity='opaque_source',entity_id=None,field='x',detail='Unknown dependency')]
    result=run(r,OperationalFactsV2.model_validate(d),lambda *a:pytest.fail('must not solve'))
    assert result.outcome=='CAPTURE_BLOCKED' and result.procurement is None


@pytest.mark.parametrize('delta',[-4,0,4])
def test_temporal_basis_preserves_capture_and_dates(delta):
    r,f=synthetic_case_v2();d=f.model_dump();d['facts']['captured_at']+=timedelta(days=delta)
    # A real forecast must have completed before observation in every fixture.
    d['facts']['forecast']['completed_at']=d['facts']['captured_at']-timedelta(hours=1)
    f=OperationalFactsV2.model_validate(d);result=run(r,f)
    basis=result.capture.operational_basis
    assert basis.local_capture_date==f.facts.captured_at.date()
    assert basis.planning_start_date==r.cutoff_date+timedelta(days=1)
    assert basis.kind==('CURRENT_CAPTURE' if delta==0 else 'HYPOTHETICAL_CURRENT_CAPTURE')
    assert ('NONCURRENT_PLANNING_CURRENT_FACTS' in {p.code for p in result.problems})==(delta!=0)
    if result.capture.prepared:
        assert result.capture.prepared.inventory_as_of==f.facts.captured_at
        assert result.capture.prepared.lots[0].received_date==f.facts.lots[0].received_date


@pytest.mark.parametrize('field,value,code',[
    ('payable_fee_coverage','UNKNOWN','PAYABLE_FEE_COVERAGE_UNKNOWN'),
    ('capacity_state','UNKNOWN','LIMIT_CONFIGURATION_UNKNOWN'),
])
def test_unknown_declarations_block_before_solver(field,value,code):
    r,f=synthetic_case_v2();d=r.model_dump();d['procurement'][field]=value
    result=run(OperationalDecisionInputV2.model_validate(d),f,lambda *a:pytest.fail('must not run'))
    assert result.outcome=='CAPTURE_BLOCKED' and code in {p.code for p in result.problems}


def test_budget_conflict_no_clamp_or_hidden_change():
    r,f=synthetic_case_v2();d=f.model_dump();d['facts']['constraints']=[dict(id=UUID(int=888),store_id=r.store_id,version=1,kind='BUDGET_LIMIT',ingredient_id=None,value='3',unit='VND',effective_from=r.cutoff_date)]
    result=run(r,OperationalFactsV2.model_validate(d))
    assert result.outcome=='CAPTURE_BLOCKED'
    assert result.capture.request.procurement.budget.amount==5
    assert 'BUDGET_SOURCE_CONFLICT' in {p.code for p in result.problems}


def test_no_eligible_unproven_not_infeasibility_certificate():
    r,f=synthetic_case_v2();d=r.model_dump();d['procurement']['budget']['amount']='0';r=OperationalDecisionInputV2.model_validate(d)
    result=run(r,f,NoCandidate)
    assert result.outcome=='NO_ELIGIBLE_CANDIDATE' and result.selection.winner_token is None
    assert all(p.proof=='UNPROVEN' and p.customer_feasibility=='UNKNOWN' for p in result.procurement.strategies)


def test_zero_demand_zero_budget_zero_purchase_is_valid():
    r,f=synthetic_case_v2();d=f.model_dump()
    for p in d['facts']['forecast']['predictions']:p.update(p25='0',p50='0',p75='0')
    q=r.model_dump();q['procurement']['budget']['amount']='0'
    result=run(OperationalDecisionInputV2.model_validate(q),OperationalFactsV2.model_validate(d),NoCandidate)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert all(c.candidate.outlay.decimal_view==0 for c in result.procurement.strategies)
    assert all(m.service is None for c in result.procurement.strategies for m in c.candidate.services)


def test_invalid_override_is_input_error_not_exclusion():
    r,f=synthetic_case_v2();d=r.model_dump();d['requirements']['paths'][0]['overrides']=[dict(product_id=UUID(int=99999),target='.8')]
    with pytest.raises(ValueError,match='override'):
        run(OperationalDecisionInputV2.model_validate(d),f)


def test_copied_request_and_output_revalidate():
    r,f=synthetic_case_v2()
    bad=r.model_copy(update={'requirements':r.requirements.model_copy(update={'paths':()})})
    with pytest.raises(ValidationError):run(bad,f)
    result=run(r,f)
    forged=result.model_copy(update={'outcome':'NO_ELIGIBLE_CANDIDATE'})
    with pytest.raises(ValidationError):OperationalPipelineResultV2.model_validate(forged)
    capture=result.capture.model_copy(update={'computed_product_ids':()})
    with pytest.raises(ValidationError):OperationalPipelineResultV2.model_validate(result.model_copy(update={'capture':capture}))
    snapshot=result.capture.prepared.model_copy(update={'capture_version':1})
    with pytest.raises(ValidationError):PreparedDecisionInput.model_validate(snapshot)


@pytest.mark.parametrize('bad',[True,0.5,'NaN','Infinity','-1'])
def test_forged_source_numeric_revalidated(bad):
    r,f=synthetic_case_v2();lot=f.facts.lots[0].model_copy(update={'on_hand_quantity':bad})
    raw=f.model_copy(update={'facts':f.facts.model_copy(update={'lots':(lot,)})})
    result=run(r,raw,lambda *a:pytest.fail('must not run'))
    assert result.outcome=='CAPTURE_BLOCKED' and result.capture.source is None


def test_past_receipt_activation_expiry_and_customer_pass_construction_miss():
    r,f=synthetic_case_v2();d=f.model_dump();start=r.cutoff_date+timedelta(days=1)
    d['facts']['captured_at']+=timedelta(days=4)
    lot=d['facts']['lots'][0];lot.update(received_date=start+timedelta(days=2),expiry_date=start+timedelta(days=2),on_hand_quantity='3')
    for p in d['facts']['forecast']['predictions']:p.update(p25='1',p50='1',p75='1')
    q=r.model_dump();q['requirements']['paths'][0]['minimum']='.1';q['procurement']['budget']['amount']='0'
    result=run(OperationalDecisionInputV2.model_validate(q),OperationalFactsV2.model_validate(d),NoCandidate)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    strategy=result.procurement.strategies[0]
    assert strategy.customer_pass and not strategy.construction_pass and strategy.selection_kind=='CUSTOMER_PASS_FALLBACK'
    rows=[p for p in strategy.candidate.evaluation.products if p.path_id=='BASE']
    assert [p.fulfilled.decimal_view for p in rows]==[0,0,1,0,0,0,0]
    lots=[l for l in strategy.candidate.evaluation.lots if l.path_id=='BASE']
    assert lots[0].opening.decimal_view==0 and lots[2].arrivals.decimal_view==3
    assert lots[2].close_expired.decimal_view==2
    assert result.capture.prepared.lots[0].received_date==start+timedelta(days=2)
    # Independently reject serving forged to consume before the actual receipt.
    from app.application.contracts.serving import ServingSimulationResult
    forged=strategy.candidate.evaluation.model_dump()
    forged['lots'][0]['arrivals']=dict(numerator='3',denominator='1',decimal_view='3')
    with pytest.raises(ValidationError):ServingSimulationResult.model_validate(forged)


def test_future_start_current_balance_expired_before_start_not_used():
    r,f=synthetic_case_v2();d=f.model_dump();d['facts']['captured_at']-=timedelta(days=2)
    d['facts']['forecast']['completed_at']=d['facts']['captured_at']-timedelta(hours=1)
    lot=d['facts']['lots'][0];lot.update(received_date=d['facts']['captured_at'].date(),expiry_date=r.cutoff_date,on_hand_quantity='99')
    q=r.model_dump();q['procurement']['budget']['amount']='0'
    result=run(OperationalDecisionInputV2.model_validate(q),OperationalFactsV2.model_validate(d),NoCandidate)
    assert result.outcome=='NO_ELIGIBLE_CANDIDATE'
    assert result.capture.operational_basis.kind=='HYPOTHETICAL_CURRENT_CAPTURE'
    assert all(p.fulfilled.decimal_view==0 for p in result.procurement.strategies[0].candidate.evaluation.products)
    assert result.procurement.strategies[0].candidate.evaluation.lots[0].pre_service_expired.decimal_view==99


def test_missing_forecast_one_product_excluded_not_fabricated_zero():
    r,f=pair();d=f.model_dump();p=f.catalog[1].product_id
    d['facts']['forecast']['predictions']=[r for r in d['facts']['forecast']['predictions'] if r['product_id']!=p]
    result=run(r,OperationalFactsV2.model_validate(d),NoCandidate)
    assert result.capture.computed_product_ids==(f.catalog[0].product_id,)
    assert result.capture.exclusions[0].product_id==p
    assert 'FORECAST_COVERAGE_INVALID' in {q.code for q in result.capture.exclusions[0].reasons}
    assert all(q.product_id!=p for q in result.capture.prepared.forecast.predictions)


def test_unused_ingredient_blocker_kept_audit_does_not_block_independent_product():
    r,f=pair(shared=False);d=r.model_dump();d['inventory_scope'][1]['state']='UNKNOWN'
    result=run(OperationalDecisionInputV2.model_validate(d),f,NoCandidate)
    assert len(result.capture.computed_product_ids)==1
    assert result.capture.exclusions[0].product_id==f.catalog[1].product_id
    assert len(result.capture.source.facts.ingredients)==2 and len(result.capture.prepared.ingredients)==1
    assert 'INVENTORY_BALANCE_MISSING' in {p.code for p in result.problems}


def test_foreign_offer_not_silently_filtered():
    r,f=synthetic_case_v2();d=r.model_dump();d['procurement']['offers'][0]['term_id']=UUID(int=999999)
    result=run(OperationalDecisionInputV2.model_validate(d),f,lambda *a:pytest.fail('must not run'))
    assert result.outcome=='CAPTURE_BLOCKED' and 'OFFER_SCOPE_INVALID' in {p.code for p in result.problems}


def test_engine_numeric_unsupported_is_not_no_pass():
    from app.application.procurement_solver import NumericUnsupported
    r,f=synthetic_case_v2()
    def reject(*a):raise NumericUnsupported('INJECTED documented projection limit')
    result=run(r,f,reject)
    assert result.outcome=='NUMERIC_UNSUPPORTED'
    assert result.procurement.execution=='NUMERIC_UNSUPPORTED'
    assert result.selection.winner_token is None


def test_search_programming_error_remains_error_with_verified_partial_candidate():
    r,f=synthetic_case_v2();d=r.model_dump();d['requirements']['paths'][0]['minimum']='.1'
    def bug(*a):raise ValueError('INJECTED programming bug')
    result=run(OperationalDecisionInputV2.model_validate(d),f,bug)
    assert result.outcome=='EXECUTION_ERROR' and result.procurement.execution=='ERROR'
    assert result.selection.winner_token is not None
    assert all(p.proof=='UNPROVEN' for p in result.procurement.strategies)


def test_final_pipeline_boundary_rejects_forged_selector_return(monkeypatch):
    from app.application.use_cases import decision_pipeline_v2 as module
    r,f=synthetic_case_v2();original=module.select_winner
    def forge(comparison):
        result=original(comparison)
        return result.model_copy(update={'winner_token':'cmp1_'+'0'*64})
    monkeypatch.setattr(module,'select_winner',forge)
    with pytest.raises(ValidationError):run(r,f)


def test_final_pipeline_boundary_rejects_stale_bom_return(monkeypatch):
    from app.application.use_cases import decision_pipeline_v2 as module
    r,f=synthetic_case_v2();original=module.expand_bom
    def forge(snapshot):
        result=original(snapshot)
        return result.model_copy(update={'contributions':()})
    monkeypatch.setattr(module,'expand_bom',forge)
    with pytest.raises(ValidationError):run(r,f)


@pytest.mark.parametrize('mode',['empty','overlap','unit'])
def test_recipe_invalid_never_falls_back_or_bypasses_zero_demand(mode):
    r,f=synthetic_case_v2();d=f.model_dump();recipe=d['facts']['recipes'][0]
    for p in d['facts']['forecast']['predictions']:p.update(p25='0',p50='0',p75='0')
    if mode=='empty':recipe['lines']=()
    elif mode=='overlap':d['facts']['recipes']=[recipe,recipe|{'id':UUID(int=98989),'version':2}]
    else:recipe['lines'][0]['unit']='kg'
    result=run(r,OperationalFactsV2.model_validate(d),lambda *a:pytest.fail('must not run'))
    assert result.outcome=='NO_COMPUTABLE_PRODUCTS' and result.capture.exclusions
    assert result.bom is None and result.procurement is None


def test_dated_recipe_changes_without_querying_live_source_again():
    r,f=synthetic_case_v2();d=f.model_dump();recipe=d['facts']['recipes'][0]
    change=r.cutoff_date+timedelta(days=4)
    recipe['effective_to']=change-timedelta(days=1)
    later=deepcopy(recipe);later.update(id=UUID(int=7888),version=2,effective_from=change,effective_to=None)
    later['lines'][0]['quantity']='2'
    d['facts']['recipes']=[later,recipe]
    for p in d['facts']['forecast']['predictions']:p.update(p25='1',p50='1',p75='1')
    facts=OperationalFactsV2.model_validate(d);source=SyntheticSnapshotSourceV2(facts)
    before=facts.model_dump()
    def factory(*args):
        source.facts=f  # Changed live port after capture must not be read again.
        return NativeProductSearch(*args)
    result=execute_operational_pipeline_v2(r,source,factory)
    base=[c for c in result.bom.contributions if c.path_id=='BASE']
    assert [p.quantity for p in base]==[1,1,1,2,2,2,2]
    assert base[3].recipe_id==later['id'] and source.reads==1
    assert result.capture.source.model_dump()==before


def test_effective_budget_can_tighten_captured_ceiling_without_rewriting_fact():
    r,f=synthetic_case_v2();d=f.model_dump();d['facts']['constraints']=[dict(id=UUID(int=888),store_id=r.store_id,version=1,kind='BUDGET_LIMIT',ingredient_id=None,value='5',unit='VND',effective_from=r.cutoff_date)]
    q=r.model_dump();q['procurement']['budget']['amount']='3'
    result=run(OperationalDecisionInputV2.model_validate(q),OperationalFactsV2.model_validate(d))
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert result.procurement.input.budget.amount==3
    assert result.capture.prepared.constraints[0].value==5
    assert result.capture.request.procurement.budget_ceiling.amount==5


def test_limit_above_ceiling_blocks_without_clamp():
    r,f=synthetic_case_v2();d=r.model_dump();d['procurement']['budget']['amount']='6'
    result=run(OperationalDecisionInputV2.model_validate(d),f,lambda *a:pytest.fail('must not run'))
    assert result.outcome=='CAPTURE_BLOCKED'
    assert result.capture.request.procurement.budget.amount==6
    assert 'BUDGET_LIMIT_EXCEEDS_CEILING' in {p.code for p in result.problems}


@pytest.mark.parametrize('version',[1,2])
def test_historical_envelope_budget_equality_guard_unchanged(version):
    from app.application.contracts.procurement import ProcurementInput
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    from scripts.procurement_demo_cases import simple
    from scripts.procurement_v2_demo_cases import upgrade,path
    data=simple(demand=2,stock='1',budget='3',certification='DISABLED')
    p=data['prepared'];p['constraints']=[dict(id=UUID(int=123456),store_id=p['request']['store_id'],version=1,kind='BUDGET_LIMIT',ingredient_id=None,value='5',unit='VND',effective_from=p['request']['cutoff_date'])]
    if version==2:data=upgrade(data,[path('BASE','.8')])
    with pytest.raises(ValidationError,match='cannot bypass captured budget'):
        (ProcurementInput if version==1 else ProcurementInputV2).model_validate(data)


def test_source_failure_cannot_forge_a_warning_only_blocked_outcome():
    r,f=synthetic_case_v2();bad=f.model_copy(update={'facts':f.facts.model_copy(update={'lots':(f.facts.lots[0].model_copy(update={'on_hand_quantity':None}),)})})
    result=run(r,bad);d=result.model_dump();d['capture']['problems'][0]['kind']='WARNING'
    with pytest.raises(ValidationError):OperationalPipelineResultV2.model_validate(d)


def test_store_local_date_basis_not_utc_date():
    from datetime import datetime,timezone
    r,f=synthetic_case_v2();d=f.model_dump();d['facts']['store']['timezone']='Asia/Ho_Chi_Minh'
    d['facts']['captured_at']=datetime(2026,10,7,20,tzinfo=timezone.utc)
    d['facts']['forecast']['completed_at']=d['facts']['captured_at']-timedelta(hours=1)
    d['facts']['forecast']['retained']['timezone']='Asia/Ho_Chi_Minh';rehash(d)
    c=capture_decision_v2(r,SyntheticSnapshotSourceV2(OperationalFactsV2.model_validate(d)))
    assert c.operational_basis.kind=='CURRENT_CAPTURE'
    assert c.operational_basis.local_capture_date.isoformat()=='2026-10-08'
    assert c.prepared.inventory_as_of.date().isoformat()=='2026-10-07'


@pytest.mark.parametrize('mode',['overflow','timezone'])
def test_date_overflow_and_unresolvable_timezone_reject(mode):
    from datetime import date
    r,f=synthetic_case_v2()
    if mode=='overflow':
        with pytest.raises(ValidationError):OperationalDecisionInputV2.model_validate(r.model_copy(update={'cutoff_date':date.max}))
    else:
        d=f.model_dump();d['facts']['store']['timezone']='No/Such_Zone'
        result=run(r,OperationalFactsV2.model_validate(d))
        assert result.outcome=='CAPTURE_BLOCKED'
        assert 'INVALID_STORE_TIMEZONE' in {p.code for p in result.problems}
