"""Exact hand-calculated comparisons; no solver or simulator invocation."""
from copy import deepcopy
from decimal import Decimal, localcontext, Inexact
from fractions import Fraction as F
from pathlib import Path
from uuid import UUID
import pytest
from pydantic import ValidationError
from app.application.contracts.procurement import ProcurementResult
from app.application.contracts.procurement_comparison import (
    ProcurementComparisonInput, ProcurementComparisonResult, SignedQuantity,
)
from app.application.use_cases.procurement_comparison import compare_procurement
from app.application.procurement_comparison_facts import q, signed
from app.domain.decision.comparison import total, delta, ComparisonNumericError
from app.domain.decision.quantities import ServingNumericError

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures'


def source(name='synthetic'):
    return ProcurementResult.model_validate_json((FIXTURES/f'procurement_comparison_{name}.json').read_text())


def compare(value=None):
    return compare_procurement(ProcurementComparisonInput(procurement=value or source()))


def option(result,strategy):
    return next(o for o in result.options if strategy in o.source_strategies)


def product(o,path,id=UUID(int=100)):
    return next(p for p in o.products if p.path==path and p.product_id==id)


def no_candidate():
    data=source().model_dump()
    for row in data['strategies']:
        row.update(best_target_met=None,best_available=None,target_met=False,target_feasibility='UNKNOWN',requirement_gaps=(),
            journal=(),enumerated_vectors=0,diagnostic='FAULT INJECTED no candidate evidence')
    return ProcurementResult.model_validate(data)


def test_zero_purchase_is_present_not_absence():
    result=compare()
    lean=option(result,'LEAN')
    assert lean.basket==() and lean.arrivals==() and q(lean.outlay.total)==0
    assert q(product(lean,'LOW').fulfilled)==10
    assert len(result.options)==3 and result.outcomes[0].target_met
    assert result.decision_readiness=='NOT_ASSESSED'


def test_unknown_no_candidate_not_synthetic_zero_plan():
    result=compare(no_candidate())
    assert result.options==() and result.deltas==()
    assert all(o.option_token is None and o.target_feasibility=='UNKNOWN' and o.diagnostic for o in result.outcomes)
    assert result.status=='COMPLETE' # Presentation projection completed, not business ready.
    assert result.input.procurement.execution=='INCOMPLETE'


def test_valid_miss_and_incomplete_unproven_preserved():
    result=compare()
    protected=result.outcomes[2]
    assert protected.execution=='INCOMPLETE' and protected.proof=='UNPROVEN' and not protected.search_complete
    assert not protected.target_met and protected.target_feasibility=='UNKNOWN'
    assert option(result,'PROTECTED').hard_validity=='EXACT_VALIDATED'
    assert q(product(option(result,'PROTECTED'),'HIGH').fulfilled)==F(150,7)
    assert q(protected.requirement_gaps[0].shortfall_quantity)==F(65,7)


def test_certified_no_pass_is_distinct_from_unknown():
    result=compare(source('no_pass_synthetic'))
    assert len(result.options)==1 and len(result.options[0].source_strategies)==3
    assert all(o.target_feasibility=='NO_PASS_CERTIFIED' and o.search_complete and o.enumerated_vectors==11 for o in result.outcomes)
    assert all(o.proof=='COMPLETE_EXACT_ENUMERATION' for o in result.outcomes)
    assert q(result.options[0].outlay.total)==F(3,10)
    assert q(result.outcomes[0].requirement_gaps[0].shortfall_quantity)==F(1,10**27)


def duplicate_with_distinct_evidence():
    data=source('target_met_synthetic').model_dump()
    # Explicit synthetic metadata exercise, not an assertion of a new native solve.
    for index,row in enumerate(data['strategies'][1:],1):
        target=Decimal('.29') if index==1 else Decimal('.3')
        data['input']['policy']['rules'][index]['target']=target;row['rule']['target']=target
        row['requirement_gaps'][0]['target']=target
        row.update(proof='UNPROVEN',search_complete=False,execution='INCOMPLETE',
            termination='SYNTHETIC_EVIDENCE_DOWNGRADE_TEST')
    data['execution']='INCOMPLETE'
    return ProcurementResult.model_validate(data)


def test_duplicate_plan_different_targets_proofs_no_evidence_promotion():
    result=compare(duplicate_with_distinct_evidence())
    assert len(result.options)==1 and result.options[0].source_strategies==('LEAN','BALANCED','PROTECTED')
    assert result.outcomes[0].proof=='COMPLETE_EXACT_ENUMERATION'
    assert result.outcomes[1].proof=='UNPROVEN' and result.outcomes[1].rule.target==Decimal('.29')
    assert result.outcomes[0].rule.target==Decimal('.3') and result.deltas==()
    assert result.outcomes[1].journal==result.input.procurement.strategies[1].journal


def test_same_total_different_offer_lot_plan_not_grouped():
    result=compare(source('equal_cost_synthetic'))
    assert len(result.options)==2
    a,b=result.options
    assert q(a.outlay.total)==q(b.outlay.total)==3
    assert a.basket[0].term_id!=b.basket[0].term_id
    assert a.arrivals[0].lot_id!=b.arrivals[0].lot_id
    assert q(result.deltas[0].total_outlay)==0
    assert all(q(p.fulfilled)==0 for p in result.deltas[0].products)


def test_more_money_different_product_path_gains_exact_deltas():
    result=compare();lean=option(result,'LEAN');base=option(result,'BALANCED');high=option(result,'PROTECTED')
    assert (q(base.outlay.purchase),q(base.outlay.payable_fees),q(base.outlay.total))==(4,1,5)
    assert base.outlay.delivery_fees is None and base.outlay.fee_classification=='PAYABLE_FEE_TYPE_NOT_CAPTURED'
    assert q(base.outlay.total)-q(lean.outlay.total)==5
    assert q(product(base,'BASE').fulfilled)-q(product(lean,'BASE').fulfilled)==5
    assert q(product(base,'BASE',UUID(int=101)).fulfilled)-q(product(lean,'BASE',UUID(int=101)).fulfilled)==F(5,2)
    assert q(product(base,'LOW').fulfilled)==q(product(lean,'LOW').fulfilled)
    assert q(high.outlay.total)-q(base.outlay.total)==4
    assert q(product(high,'HIGH').fulfilled)-q(product(base,'HIGH').fulfilled)==F(30,7)
    assert q(product(high,'HIGH',UUID(int=101)).fulfilled)-q(product(base,'HIGH',UUID(int=101)).fulfilled)==F(20,7)
    options={o.token:o for o in result.options}
    for d in result.deltas:
        a,b=options[d.from_token],options[d.to_token]
        assert q(d.total_outlay)==q(b.outlay.total)-q(a.outlay.total)
        for p in d.products:
            assert q(p.fulfilled)==q(product(b,p.path,p.product_id).fulfilled)-q(product(a,p.path,p.product_id).fulfilled)
            assert q(p.lost)==-q(p.fulfilled) # same requested scope
    assert any(q(d.total_outlay)<0 for d in result.deltas)


def test_ingredient_shortage_diagnostic_and_horizon_ending_not_sum_balances():
    result=compare()
    lean=option(result,'LEAN');base=option(result,'BALANCED')
    low=lambda o:next(i for i in o.ingredients if i.path=='LOW')
    assert q(low(lean).horizon_ending)==2 and q(low(base).horizon_ending)==4
    assert sum(q(r.ending) for r in lean.daily_ingredients if r.path_id=='LOW')==14
    assert q(low(lean).daily_shortage_sum)==0
    assert q(next(i for i in lean.ingredients if i.path=='BASE').daily_shortage_sum)==2
    assert q(next(i for i in lean.ingredients if i.path=='HIGH').daily_shortage_sum)==8


def test_none_fees_explicit_zero_delivery_not_missing():
    result=compare(source('target_met_synthetic'))
    outlay=result.options[0].outlay
    assert q(outlay.payable_fees)==0 and q(outlay.delivery_fees)==0 and outlay.fee_classification=='NO_PAYABLE_FEES'


def test_repeating_ratios_signed_canonical_and_ambient_context():
    request=ProcurementComparisonInput(procurement=source())
    expected=compare_procurement(request)
    assert q(product(option(expected,'LEAN'),'BASE').service)==F(3,4)
    assert q(product(option(expected,'PROTECTED'),'HIGH').service)==F(5,7)
    with localcontext() as ctx:
        ctx.prec=2;ctx.traps[Inexact]=True;ctx.Emax=2;ctx.Emin=-2
        assert compare_procurement(request)==expected
        assert q(signed(F(-30,7)))==F(-30,7)
    for change in (dict(numerator='-0'),dict(numerator='-60',denominator='14'),dict(decimal_view=0.1),dict(decimal_view='NaN')):
        data=signed(F(-30,7)).model_dump()|change
        with pytest.raises(ValidationError):SignedQuantity.model_validate(data)


def test_no_solver_simulator_procurement_execution_or_valuation(monkeypatch):
    import app.application.use_cases.procurement as execution
    import app.application.use_cases.serving as serving
    def forbidden(*a,**kw):raise AssertionError('Comparison called an engine')
    monkeypatch.setattr(execution,'execute_procurement',forbidden)
    monkeypatch.setattr(execution,'evaluate_procurement_basket',forbidden)
    monkeypatch.setattr(execution,'simulate_serving',forbidden)
    monkeypatch.setattr(serving,'simulate_serving',forbidden)
    result=compare()
    for model in (type(result),type(result.options[0]),type(result.deltas[0])):
        assert not set(model.model_fields)&{'winner','recommended_strategy','selected_strategy','suggested_strategy','probability','confidence','profit','revenue','roi','product_lot_attribution'}


@pytest.mark.parametrize('field',['currency','unit','context','horizon','scope','metric','fee','lost'])
def test_malformed_input_rejected_not_partial(field):
    data=source().model_dump();candidate=data['strategies'][1]['best_target_met']
    if field=='currency':candidate['currency']='USD'
    if field=='unit':candidate['basket'][0]['unit']='ml'
    if field=='context':candidate['evaluation']['input']['prepared']['timezone']='Asia/Ho_Chi_Minh'
    if field=='horizon':data['input']['prepared']['request']['cutoff_date']='2026-10-08'
    if field=='scope':candidate['evaluation']['products']=candidate['evaluation']['products'][:-1]
    if field=='metric':candidate['services']=()
    if field=='fee':data['input']['supplier_fees'][0]['amount']='2'
    if field=='lost':candidate['evaluation']['products'][0]['lost']['numerator']='999'
    with pytest.raises(ValidationError):compare_procurement(ProcurementComparisonInput.model_construct(procurement=ProcurementResult.model_construct(**data)))


def test_snapshot_mutation_after_capture_and_nested_copy_revalidation():
    data=source().model_dump();request=ProcurementComparisonInput.model_validate({'procurement':data})
    expected=compare_procurement(request)
    data['input']['prepared']['lots'][0]['on_hand_quantity']='999'
    data['strategies'][1]['best_target_met']['basket']=()
    assert compare_procurement(request)==expected
    with pytest.raises(ValidationError):expected.options[0].outlay.currency='USD'
    row=request.procurement.strategies[1]
    bad=row.best_target_met.model_copy(update={'currency':'USD'})
    modified=request.procurement.model_copy(update={'strategies':(request.procurement.strategies[0],row.model_copy(update={'best_target_met':bad}),request.procurement.strategies[2])})
    with pytest.raises(ValidationError):compare_procurement(request.model_copy(update={'procurement':modified}))


def test_ordering_numeric_equivalence_and_identifiers_stable():
    original=source('target_met_synthetic');expected=compare(original)
    data=original.model_dump()
    for row in data['strategies']:
        candidate=row['best_target_met']
        for name in ('products','ingredients','lots','contributions'):candidate['evaluation'][name]=tuple(reversed(candidate['evaluation'][name]))
    data['input']['prepared']['supplier_terms'][0]['pack_cost']=Decimal('.1000')
    other=compare(ProcurementResult.model_validate(data))
    assert other.options==expected.options and other.deltas==expected.deltas
    assert len(other.options)==1
    assert all(o.identity_kind=='INTERNAL_COMPARISON_TOKEN_NOT_PERSISTED' for o in other.options)


def test_same_plan_incompatible_evaluation_kept_separate_with_diagnostic():
    data=source('target_met_synthetic').model_dump()
    data['strategies'][0]['best_target_met']['evaluation']['issues']+=({
        'code':'SYNTHETIC_EXTRA_INFO','kind':'INFO','field':'evaluation',
        'affected':({'entity':'product','entity_id':UUID(int=100)},),
        'impact':'Synthetic evidence incompatibility test','suggested_action':'Review source evidence',
        'path_id':None,'day':None},)
    result=compare(ProcurementResult.model_validate(data))
    assert len(result.options)==2 and result.status=='COMPLETE_WITH_DIAGNOSTICS'
    assert result.diagnostics[0].code=='SAME_PLAN_DIFFERENT_EVALUATION'
    assert len(result.diagnostics[0].option_tokens)==2 and len(result.outcomes)==3
    assert any(i.code=='SYNTHETIC_EXTRA_INFO' for o in result.options for i in o.issues)


@pytest.mark.parametrize('field',['outlay','fee_type','products','ingredients','delta','delta_scope','evidence','members','provenance','issues','token','diagnostic'])
def test_comparison_output_tampering_rejected(field):
    data=compare().model_dump();o=data['options'][0]
    zero=dict(numerator='0',denominator='1',decimal_view=Decimal(0))
    if field=='outlay':o['outlay']['total']=zero
    if field=='fee_type':o['outlay']['delivery_fees']=zero
    if field=='products':o['products']=()
    if field=='ingredients':o['ingredients']=()
    if field=='delta':data['deltas'][0]['total_outlay']=zero
    if field=='delta_scope':data['deltas'][0]['products']=()
    if field=='evidence':data['outcomes'][0]['proof']='COMPLETE_EXACT_ENUMERATION'
    if field=='members':o['source_strategies']=()
    if field=='provenance':o['provenance']=()
    if field=='issues':o['issues']=({'code':'FAKE','kind':'INFO','field':'quantity','affected':({'entity':'product','entity_id':UUID(int=100)},),'impact':'Fabricated','suggested_action':'None','day':None,'path_id':None},)
    if field=='token':o['token']='cmp1_'+'0'*64
    if field=='diagnostic':data['status']='COMPLETE_WITH_DIAGNOSTICS'
    with pytest.raises(ValidationError):ProcurementComparisonResult.model_validate(data)


def test_numeric_sum_delta_guards_no_fabricated_zero():
    big=F(10**999)
    assert total((big,big))==2*big
    with pytest.raises(ServingNumericError):total((9*big,9*big))
    with pytest.raises(ServingNumericError):delta(-9*big,9*big)


def test_numeric_comparison_failure_no_partial_result(monkeypatch):
    from app.application.use_cases import procurement_comparison as module
    def unsupported(*a,**kw):raise ServingNumericError('FAULT exact capacity exceeded')
    monkeypatch.setattr(module,'product_totals',unsupported)
    with pytest.raises(ComparisonNumericError,match='exact aggregate/delta'):compare()


def test_blocked_outcomes_and_provenance_preserved_without_options():
    data=no_candidate().model_dump()
    data['input']['unsupported_configured_constraints']=('MIN_SAFETY_STOCK',)
    for r in data['strategies']:r.update(execution='BLOCKED',termination='INPUT_BLOCKED')
    data.update(execution='BLOCKED',readiness='BLOCKED')
    from app.application.use_cases.procurement import constraint_coverage
    from app.application.contracts.procurement import ProcurementInput
    data['coverage']=constraint_coverage(ProcurementInput.model_validate(data['input']))
    result=compare(ProcurementResult.model_validate(data))
    assert not result.options and all(o.execution=='BLOCKED' for o in result.outcomes)
    assert result.input.procurement.coverage[-1].status=='BLOCKED'
    assert result.input.procurement.input.source_references


def test_identity_hash_collision_never_groups_distinct_plans(monkeypatch):
    from app.application import procurement_comparison_facts as facts
    monkeypatch.setattr(facts,'digest',lambda v:'0'*64)
    with pytest.raises(ValueError,match='token collision'):compare()


def test_units_remain_separate_and_zero_requested_service_undefined():
    from datetime import date
    from app.domain.decision.comparison import IngredientObservation, ingredient_totals, ProductObservation, product_totals
    day=date(2026,10,14)
    rows=(IngredientObservation('LOW',day,UUID(int=1),'g',F(1000),F(20),F(3),F(0)),
          IngredientObservation('LOW',day,UUID(int=2),'ml',F(2000),F(40),F(4),F(0)))
    values=ingredient_totals(rows,day)
    assert [(r.unit,r.daily_shortage_sum,r.horizon_ending,r.expired) for r in values]==[('g',1000,20,3),('ml',2000,40,4)]
    zero=product_totals((ProductObservation('LOW',UUID(int=100),'cup',F(0),F(0),F(0)),))
    assert zero[0].service is None and zero[0].fulfilled==0


def test_new_domain_import_without_boundary_or_infrastructure():
    import subprocess,sys
    code="""
import sys
class Reject:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'pydantic','scipy','numpy','sqlalchemy','fastapi','psycopg','httpx'} or fullname.startswith(('app.application','app.infrastructure','app.models','app.api')):
   raise AssertionError(fullname)
sys.meta_path.insert(0,Reject())
import app.domain.decision.comparison
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
