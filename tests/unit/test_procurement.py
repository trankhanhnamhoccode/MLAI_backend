"""Hand expectations, independent finite oracle and labelled fault-injection evidence."""
from copy import deepcopy
from datetime import timedelta, date
from decimal import Decimal, localcontext, Inexact
from fractions import Fraction as F
from itertools import product
from uuid import UUID
import time

import pytest
from pydantic import ValidationError
from app.application.contracts.procurement import ProcurementInput, SolverEvidence, ProcurementResult
from app.application.contracts.serving import ServingSimulationInput
from app.application.use_cases.serving import simulate_serving
from app.application.use_cases.procurement import execute_procurement, evaluate_procurement_basket, rational, captured_offers
from app.application.procurement_solver import SolverProposal, NumericUnsupported
from app.infrastructure.procurement_milp import NativeSearch, build, exclude_vector, Model, add, mul, var
from scripts.procurement_demo_cases import snapshot, envelope, simple, representative, D, STORE, iid, pid


def run(data, factory=NativeSearch):
    return execute_procurement(ProcurementInput.model_validate(data),factory)


def chosen(row):
    return row.best_target_met or row.best_available


def independent_oracle(data, rule):
    """itertools + separately authored fees/constraints/objectives; canonical fixed basket service.

    This proves search for the canonical evaluator, not an independent simulator.
    """
    request=ProcurementInput.model_validate(data)
    terms={t.id:t for t in request.prepared.supplier_terms};records=[]
    for vector in product(*(range(o.bound.maximum_packs+1) for o in request.offers)):
        if any(n and n<terms[o.term_id].minimum_order_packs for o,n in zip(request.offers,vector)):continue
        spend=sum((F(terms[o.term_id].pack_cost)*n for o,n in zip(request.offers,vector)),F(0))
        if request.policy.fee_mode=='PER_OFFER':spend+=sum((F(o.payable_fee) for o,n in zip(request.offers,vector) if n),F(0))
        if request.policy.fee_mode=='PER_SUPPLIER_ORDER':
            suppliers={terms[o.term_id].supplier_id for o,n in zip(request.offers,vector) if n}
            spend+=sum((F(f.amount) for f in request.supplier_fees if f.supplier_id in suppliers),F(0))
        if request.budget.amount is not None and spend>F(request.budget.amount):continue
        if any(sum((F(terms[o.term_id].pack_size_base_quantity)*n for o,n in zip(request.offers,vector)
                    if terms[o.term_id].ingredient_id==c.ingredient_id and terms[o.term_id].supplier_id==c.supplier_id),F(0))>F(c.maximum_quantity)
               for c in request.supplier_limits):continue
        arrivals=list(request.arrivals)
        for o,n in zip(request.offers,vector):
            if not n:continue
            t=terms[o.term_id];day=D+timedelta(days=1+t.lead_time_days)
            # Independent exact Fraction -> finite Decimal source for synthetic terminating inputs.
            qty=F(t.pack_size_base_quantity)*n
            with localcontext() as ctx:
                ctx.prec=100
                source=Decimal(qty.numerator)/Decimal(qty.denominator)
            arrivals.append(dict(lot_id=o.arrival_lot_id,store_id=STORE,ingredient_id=t.ingredient_id,unit=t.unit,
                arrival_day=day,expiry_date=None if t.shelf_life_days is None else day+timedelta(days=t.shelf_life_days),quantity=source))
        evaluation=simulate_serving(ServingSimulationInput(prepared=request.prepared,arrivals=arrivals))
        if evaluation.status!='COMPLETE':continue
        if any(sum((rational(l.opening)+rational(l.arrivals) for l in evaluation.lots
                if l.path_id==path and l.day==D+timedelta(days=day) and l.ingredient_id==c.ingredient_id),F(0))>F(c.maximum_quantity)
               for c in request.capacities for path in ('LOW','BASE','HIGH') for day in range(1,8)):continue
        rows=[r for r in evaluation.products if r.path_id==rule.path]
        served=sum((rational(r.fulfilled) for r in rows),F(0));need=sum((rational(r.requested) for r in rows),F(0))
        passing=served>=F(rule.target)*need and all(
            sum((rational(r.fulfilled) for r in rows if r.product_id==f.product_id),F(0))>=F(f.target)*sum((rational(r.requested) for r in rows if r.product_id==f.product_id),F(0)) for f in rule.floors)
        records.append((passing,served,spend,vector))
    good=[r for r in records if r[0]]
    best=min(good,key=lambda r:(r[2],r[3])) if good else min(records,key=lambda r:(-r[1],r[2],r[3])) if records else None
    return best


def test_saved_decimal_counterexample_native_reject_research_exact_certification():
    data=simple(budget='.3',target='.3000000000000000000000000001')
    result=run(data)
    for row in result.strategies:
        assert not row.target_met and row.target_feasibility=='NO_PASS_CERTIFIED'
        assert chosen(row).counts==(3,) and rational(chosen(row).outlay)==F(3,10)
        assert rational(row.requirement_gaps[0].shortfall_quantity)==F(1,10**27)
        assert row.proof=='COMPLETE_EXACT_ENUMERATION' and row.enumerated_vectors==11
        assert any(j.counts==(3,) and j.classification=='HARD_VALID_TARGET_MISS' for j in row.journal)
        assert (3,) in row.excluded
        oracle=independent_oracle(data,row.rule)
        assert oracle[3]==chosen(row).counts and oracle[2]==rational(chosen(row).outlay)


@pytest.mark.parametrize('target,pass_expected',[('.3',True),('.2999999999999999999999999999',True)])
def test_exact_target_boundary(target,pass_expected):
    for row in run(simple(budget='.3',target=target)).strategies:
        assert row.target_met is pass_expected
        assert chosen(row).counts==(3,)


def test_complementarity_shared_and_independent_oracle():
    data=envelope(snapshot([[2,0,0,0,0,0,0],[2,0,0,0,0,0,0]],[{0:1,1:1},{0:1}]),
        [dict(ingredient=0,pack='4',cost='2',upper=1),dict(ingredient=1,pack='2',cost='3',upper=1)],budget='5')
    result=run(data)
    for row in result.strategies:
        assert chosen(row).counts==(1,1) and rational(chosen(row).outlay)==5
        assert row.target_met and independent_oracle(data,row.rule)[3]==(1,1)
        assert len(chosen(row).services)==9


def test_supplier_split_moq_and_supplied_quantity_limit():
    data=envelope(snapshot([[4,0,0,0,0,0,0]],[{0:1}]),[
        dict(ingredient=0,pack='1',cost='1',minimum=2,upper=4,supplier=0),
        dict(ingredient=0,pack='2',cost='3',upper=2,supplier=1)])
    data['supplier_limits']=[dict(store_id=STORE,supplier_id=UUID(int=2000),ingredient_id=iid(0),unit='g',maximum_quantity='2',scope='ONE_ORDER_SUPPLIER_INGREDIENT',provenance='SYNTHETIC captured supplier cap')]
    for row in run(data).strategies:
        assert chosen(row).counts==(2,1) and rational(chosen(row).outlay)==5
        assert len({b.supplier_id for b in chosen(row).basket})==2
        assert independent_oracle(data,row.rule)[3]==(2,1)


@pytest.mark.parametrize('mode,expected',[('NONE',2),('PER_OFFER',4),('PER_SUPPLIER_ORDER',3)])
def test_fee_once_per_offer_or_supplier_order(mode,expected):
    data=envelope(snapshot([[1,0,0,0,0,0,0]],[{0:1,1:1}]),[
        dict(ingredient=0,pack='1',cost='1',upper=1,fee='1' if mode!='NONE' else None),dict(ingredient=1,pack='1',cost='1',upper=1,fee='1' if mode!='NONE' else None)])
    data['policy']['fee_mode']=mode
    data['supplier_fees']=[dict(supplier_id=UUID(int=2000),amount='1' if mode!='NONE' else '0',provenance='SYNTHETIC fee')]
    for row in run(data).strategies:
        assert row.target_met and rational(chosen(row).outlay)==expected
        assert independent_oracle(data,row.rule)[2]==expected


@pytest.mark.parametrize('mode',['PER_OFFER','PER_SUPPLIER_ORDER'])
def test_fee_above_exact_budget_rejected(mode):
    data=simple(demand=1,budget='.3')
    data['prepared']['supplier_terms'][0]['pack_cost']='.2'
    data['offers'][0]['payable_fee']='.1000000000000000000000000001'
    data['policy']['fee_mode']=mode
    data['supplier_fees']=[dict(supplier_id=UUID(int=2000),amount='.1000000000000000000000000001',provenance='SYNTHETIC fee')]
    for row in run(data).strategies:
        assert not row.target_met and chosen(row).counts==(0,)
        assert row.target_feasibility=='NO_PASS_CERTIFIED'


def test_zero_purchase_budget_zero_existing_stock_and_equivalent_baskets():
    data=simple(demand=10,stock='10',budget='0',certification='DISABLED')
    for row in run(data).strategies:
        assert row.target_met and chosen(row).counts==(0,) and rational(chosen(row).outlay)==0
        assert row.proof=='UNPROVEN' and row.target_feasibility=='PASS_EXISTS'
        assert row.journal[0].stage=='ZERO_BASELINE'


def test_distinct_construction_paths_all_three_evaluations_and_floors():
    data=simple(demand=6,budget='1')
    data['prepared']['forecast']['predictions'][0].update(p25='2',p50='4',p75='6')
    for row in run(data).strategies:
        assert chosen(row).counts==({'LOW':(2,),'BASE':(4,),'HIGH':(6,)}[row.rule.path])
        assert {m.path for m in chosen(row).services}=={'LOW','BASE','HIGH'}
    data['policy']['rules'][1]['floors']=[dict(product_id=pid(0),target='1')]
    data['policy']['rules'][1]['target']='.5'
    assert run(data).strategies[1].best_target_met.counts==(4,)


def test_dated_yield_loss_arrival_expiry_capacity_checkpoint():
    data=simple(demand=0,stock='0')
    data['prepared']['forecast']['predictions'][0].update(p25='1',p50='1',p75='1')
    data['prepared']['recipes'][0].update(yield_quantity='3',process_loss_rate='.2')
    data['prepared']['supplier_terms'][0].update(pack_size_base_quantity='1',shelf_life_days=0)
    data['offers'][0]['bound']['maximum_packs']=1
    data['capacities']=[dict(store_id=STORE,ingredient_id=iid(0),unit='g',maximum_quantity='1',checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',provenance='SYNTHETIC gross cap')]
    request=ProcurementInput.model_validate(data)
    candidate=evaluate_procurement_basket(request,(1,))
    assert candidate is not None
    lot=next(l for l in candidate.evaluation.lots if l.lot_id==UUID(int=3000) and l.path_id=='BASE' and l.day==D+timedelta(days=1))
    assert rational(lot.consumed)==F(5,12) and rational(lot.close_expired)==F(7,12) and rational(lot.ending)==0
    data['capacities'][0]['maximum_quantity']='.9'
    assert evaluate_procurement_basket(ProcurementInput.model_validate(data),(1,)) is None
    data['capacities'][0]['maximum_quantity']='1'
    data['prepared']['supplier_terms'][0]['lead_time_days']=1
    assert not run(data).strategies[0].target_met


@pytest.mark.parametrize('mode',['fees','budget','safety','unsupported','captured_blocker'])
def test_readiness_blockers_no_solver_invocation(mode):
    data=simple()
    if mode=='fees':data['policy']['fee_mode']='PER_OFFER'
    if mode=='budget':data['budget'].update(state='UNKNOWN',amount=None)
    if mode=='safety':data['prepared']['constraints']=[dict(id=UUID(int=9000),store_id=STORE,version=1,kind='MIN_SAFETY_STOCK',ingredient_id=iid(0),value='1',unit='g',effective_from=D)]
    if mode=='unsupported':data['unsupported_configured_constraints']=['MIN_DELIVERY_VALUE']
    if mode=='captured_blocker':data['prepared']['issues']=[dict(code='UNKNOWN_SOURCE',kind='DATA_BLOCKER',field='quantity',affected=[dict(entity='ingredient',entity_id=iid(0))],impact='Required unknown',suggested_action='Capture facts')]
    def forbidden(*args):raise AssertionError('Blocked input invoked solver')
    result=run(data,forbidden)
    assert result.execution=='BLOCKED' and result.readiness=='BLOCKED'
    assert all(chosen(r) is None and r.execution=='BLOCKED' for r in result.strategies)
    assert result.input.prepared.issues==ProcurementInput.model_validate(data).prepared.issues


@pytest.mark.parametrize('bad',[True,0.3,'NaN','Infinity','-1'])
def test_exact_input_numeric_rejections(bad):
    data=simple();data['policy']['rules'][0]['target']=bad
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)


def test_scope_unit_provenance_copied_boundary_and_immutability():
    data=simple();request=ProcurementInput.model_validate(data)
    expected=evaluate_procurement_basket(request,(10,))
    data['prepared']['supplier_terms'][0]['pack_cost']='999'
    data['prepared']['recipes'][0]['lines'][0]['quantity']='999'
    assert evaluate_procurement_basket(request,(10,))==expected
    with pytest.raises(ValidationError):request.offers[0].provenance='changed'
    with pytest.raises(ValidationError):
        execute_procurement(request.model_copy(update={'budget':request.budget.model_copy(update={'amount':Decimal('-1')})}),NativeSearch)
    for update in (dict(source_references=[]),dict(capacities=[dict(store_id=STORE,ingredient_id=iid(0),unit='kg',maximum_quantity='1',checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',provenance='SYNTHETIC')])):
        with pytest.raises(ValidationError):ProcurementInput.model_validate(simple()|update)
    other=simple()
    for name in ('products','recipes','ingredients','lots','supplier_terms'):other['prepared'][name].reverse()
    other['prepared']['forecast']['predictions'].reverse()
    with localcontext() as ctx:
        ctx.prec=2;ctx.traps[Inexact]=True
        assert evaluate_procurement_basket(ProcurementInput.model_validate(other),(10,))==expected
    copied=request.model_copy(update={'prepared':request.prepared.model_copy(update={'recipes':()})})
    with pytest.raises(ValidationError):execute_procurement(copied,NativeSearch)


class FakeSearch:
    """Fault injection only; does not claim native HiGHS timeout observations."""
    def __init__(self, counts=(10,),status=0,error=None,cut_error=False):
        self.counts=counts;self.status=status;self.error=error;self.cut_error=cut_error;self.calls=[]
    def solve(self,rule,phase,deadline):
        self.calls.append((rule.strategy,phase,deadline))
        if self.error:raise self.error
        return SolverProposal(SolverEvidence(phase=phase,status=self.status,message='FAULT INJECTED',incumbent=self.counts is not None,
            objective=0,bound=0,gap=0,nodes=0,seconds=0,variables=1,constraints=1,solver_version='FAULT INJECTED',time_limit=1),self.counts)
    def exclude(self,counts,**kwargs):
        if self.cut_error:raise ValueError('FAULT cut failure')


def test_target_met_unproven_is_valid_not_certified():
    result=run(simple(certification='DISABLED'),lambda *args:FakeSearch())
    assert result.execution=='FINISHED'
    for row in result.strategies:
        assert row.target_met and row.proof=='UNPROVEN' and not row.search_complete
        assert chosen(row).hard_validity=='EXACT_VALIDATED'


@pytest.mark.parametrize('counts',[None,(10,)])
def test_fault_timeout_with_without_incumbent(counts):
    result=run(simple(certification='DISABLED'),lambda *args:FakeSearch(counts,status=1))
    assert result.execution=='INCOMPLETE'
    for row in result.strategies:
        assert row.target_met==(counts is not None)
        assert row.proof=='UNPROVEN' and row.target_feasibility==('UNKNOWN' if counts is None else 'PASS_EXISTS')


@pytest.mark.parametrize('factory,message',[
    (lambda *a:FakeSearch((3,)), 'REPEATED_EXCLUDED'),
    (lambda *a:FakeSearch((3,),cut_error=True), 'cut failure'),
    (lambda *a:FakeSearch(error=ValueError('FAULT programming')), 'programming'),
    (lambda *a:FakeSearch(None,status=3), 'MODEL_OR_TECHNICAL'),
    (lambda *a:FakeSearch(None,status=4), 'MODEL_OR_TECHNICAL'),
])
def test_fault_errors_never_business_completion(factory,message):
    result=run(simple(certification='DISABLED'),factory)
    assert result.execution=='ERROR'
    assert all(message in r.diagnostic and r.proof=='UNPROVEN' for r in result.strategies)
    assert all(chosen(r) is not None for r in result.strategies) # Valid zero baseline retained.


def test_native_infeasible_not_exact_no_pass_when_certification_disabled():
    result=run(simple(budget='0',certification='DISABLED'))
    assert all(r.target_feasibility=='UNKNOWN' and not r.search_complete for r in result.strategies)
    assert any(s.status==2 for r in result.strategies for s in r.solver)


def test_numeric_unsupported_preserves_valid_zero_and_reports_diagnostic():
    data=simple(certification='DISABLED');data['offers'][0]['bound']['maximum_packs']=2**53
    result=run(data)
    assert result.execution=='NUMERIC_UNSUPPORTED'
    assert all(r.proof=='UNPROVEN' and 'INTEGER_FLOAT64_RANGE' in r.diagnostic for r in result.strategies)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),.5,2**53])
def test_integer_extraction_guards(value):
    request=ProcurementInput.model_validate(simple())
    model=Model(request.policy.numeric);model.pack=[model.v('pack',10,integer=True)]
    with pytest.raises(NumericUnsupported):model.extract([value])


def test_exact_no_good_membership_native_two_dimensional_grid():
    request=ProcurementInput.model_validate(simple())
    for vector in product(range(3),repeat=2):
        model=Model(request.policy.numeric)
        model.pack=[model.v('x',2,integer=True),model.v('y',2,integer=True)]
        exclude_vector(model,(1,1))
        for j,n in zip(model.pack,vector):model.eq(var(j),n)
        _,e=model.solve({},time.perf_counter()+5)
        assert (e.status==2)==(vector==(1,1))


def test_best_available_floor_gaps_and_exact_objective_ties():
    data=envelope(snapshot([[10,0,0,0,0,0,0]],[{0:1}]),[
        dict(ingredient=0,pack='3',cost='1',upper=1,supplier=0),
        dict(ingredient=0,pack='3.000000000000000000000000001',cost='1',upper=1,supplier=1)],budget='1')
    for rule in data['policy']['rules']:rule['floors']=[dict(product_id=pid(0),target='1')]
    for row in run(data).strategies:
        assert chosen(row).counts==(0,1)
        assert row.target_feasibility=='NO_PASS_CERTIFIED' and len(row.requirement_gaps)==2
        assert independent_oracle(data,row.rule)[3]==(0,1)


def test_deadline_fairness_no_false_complete_comparison(monkeypatch):
    data=simple(seconds='1',certification='DISABLED')
    clock=[100.0]
    monkeypatch.setattr(time,'perf_counter',lambda:clock[0])
    touched=[]
    class Slow(FakeSearch):
        def solve(self,rule,phase,deadline):
            touched.append(rule.strategy);clock[0]+=.34
            return super().solve(rule,phase,deadline)
    result=run(data,lambda *a:Slow(None,status=1))
    assert result.execution=='INCOMPLETE' and not any(r.search_complete for r in result.strategies)
    assert touched==['LEAN','BALANCED','PROTECTED']
    assert all(r.execution=='INCOMPLETE' for r in result.strategies)


def flatten(result):
    values={}
    for group,identity,fields in (
        ('products','product_id',('requested','fulfilled','lost')),
        ('contributions','product_id',('quantity',)),
        ('lots','lot_id',('opening','arrivals','pre_service_expired','consumed','close_expired','other_waste','ending')),
        ('ingredients','ingredient_id',('requested','available','shortage','consumed','expired','other_waste','ending'))):
        for row in getattr(result,group):
            key=(group,row.path_id,str(row.day),str(getattr(row,identity)))
            if group=='contributions':key+=(str(row.ingredient_id),)
            for field in fields:values[key+(field,)]=rational(getattr(row,field))
    return values


@pytest.mark.parametrize('vector',[(0,0),(1,1)])
def test_native_policy_faithful_full_state_parity_dated_shared_fefo(vector):
    data=envelope(snapshot([[2]*7,[1]*7],[{0:1,1:1},{0:2}],[(0,'2',D+timedelta(days=1)),(0,'3',None),(1,'4',None)]),
        [dict(ingredient=0,pack='8',cost='2',upper=1),dict(ingredient=1,pack='8',cost='2',upper=1,lead=1,shelf=2)])
    first=data['prepared']['recipes'][0];first.update(yield_quantity='3',process_loss_rate='.2',effective_to=D+timedelta(days=3))
    later=deepcopy(first);later.update(id=UUID(int=990),version=2,effective_from=D+timedelta(days=4),effective_to=None,yield_quantity='2',process_loss_rate='.1')
    data['prepared']['recipes'].append(later)
    request=ProcurementInput.model_validate(data)
    candidate=evaluate_procurement_basket(request,vector)
    model=build(request,captured_offers(request),fixed=vector)
    x,e=model.solve({},time.perf_counter()+20)
    assert e.status==0 and x is not None
    canonical=flatten(candidate.evaluation);native=model.project(x)
    assert canonical.keys()<=native.keys()
    assert all(k[0]=='lots' and abs(native[k])<1e-9 for k in native.keys()-canonical.keys()) # Inactive offer lot placeholders.
    assert all(abs(float(v)-native[k])<=1e-7*(1+abs(float(v))) for k,v in canonical.items())


@pytest.mark.parametrize('field',['outlay','basket','arrivals','services','target','gap','rule','coverage','proof'])
def test_procurement_output_mutations_rejected(field):
    result=run(simple(certification='DISABLED'),lambda *a:FakeSearch())
    data=result.model_dump();row=data['strategies'][0];candidate=row['best_target_met']
    if field=='outlay':candidate['outlay']=dict(numerator='0',denominator='1',decimal_view=Decimal(0))
    if field=='basket':candidate['basket']=()
    if field=='arrivals':candidate['arrivals']=()
    if field=='services':candidate['services']=()
    if field=='target':row.update(target_met=False,target_feasibility='UNKNOWN')
    if field=='gap':row['requirement_gaps']=()
    if field=='rule':row['rule']['target']='.5'
    if field=='coverage':data['coverage']=()
    if field=='proof':row.update(search_complete=True,proof='COMPLETE_EXACT_ENUMERATION',enumerated_vectors=11)
    with pytest.raises(ValidationError):ProcurementResult.model_validate(data)


def test_supplier_bound_proof_scope_and_source_reference_scope():
    data=simple();data['offers'][0]['bound']['source']='CAPTURED_SUPPLIER_LIMIT'
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)
    data=simple();data['source_references'][0]['entity_id']=UUID(int=987)
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)
    for field in ('version','order_count'):
        data=simple();data['policy'][field]=True
        with pytest.raises(ValidationError):ProcurementInput.model_validate(data)


def test_arrival_and_expiry_overflow_rejected_at_boundary():
    data=simple();data['prepared']['supplier_terms'][0]['lead_time_days']=10**10
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)
    data=simple();data['prepared']['supplier_terms'][0]['shelf_life_days']=10**10
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)


def test_multi_offer_permutations_ties_ambient_context_and_captured_only():
    data=envelope(snapshot([[2,0,0,0,0,0,0]],[{0:1}]),[
        dict(ingredient=0,pack='2',cost='1',upper=1),dict(ingredient=0,pack='2',cost='1',upper=1,supplier=1)])
    result=run(data)
    assert all(chosen(r).counts==(0,1) for r in result.strategies) # Explicit lexicographic pack-vector tie.
    other=deepcopy(data)
    for name in ('offers','source_references'):other[name].reverse()
    other['prepared']['supplier_terms'].reverse()
    other['policy']['rules'].reverse()
    again=run(other)
    assert all(chosen(a)==chosen(b) for a,b in zip(result.strategies,again.strategies))
    request=ProcurementInput.model_validate(data)
    data['prepared']['supplier_terms'][0]['pack_cost']='100'
    with localcontext() as ctx:
        ctx.prec=1;ctx.traps[Inexact]=True
        assert evaluate_procurement_basket(request,(0,1))==chosen(result.strategies[0])


def test_domain_module_import_isolation():
    import subprocess,sys
    code="""
import sys
class Reject:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'pydantic','scipy','numpy','sqlalchemy','fastapi','psycopg'} or fullname.startswith(('app.application','app.infrastructure','app.models','app.api')):
   raise AssertionError(fullname)
sys.meta_path.insert(0,Reject())
import app.domain.decision.procurement
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_fault_deadline_before_any_validation_no_incumbent(monkeypatch):
    stamps=iter((0,))
    monkeypatch.setattr(time,'perf_counter',lambda:next(stamps,2))
    result=run(simple(seconds='1',certification='DISABLED'),lambda *a:FakeSearch(None,status=1))
    assert result.execution=='INCOMPLETE'
    assert all(chosen(r) is None and r.target_feasibility=='UNKNOWN' for r in result.strategies)
    assert result.unique_exact_evaluations==0


def test_fault_post_zero_baseline_programming_error_preserves_passing_evidence():
    result=run(simple(stock='10',budget='0',certification='DISABLED'),lambda *a:FakeSearch(error=ValueError('FAULT after zero')))
    assert result.execution=='ERROR'
    assert all(r.target_met and r.best_target_met.counts==(0,) and r.proof=='UNPROVEN' for r in result.strategies)


def test_fault_certification_interrupted_does_not_manufacture_no_pass(monkeypatch):
    from app.application.use_cases import procurement as module
    clock=[100.0];monkeypatch.setattr(time,'perf_counter',lambda:clock[0])
    original=module.vectors
    def interrupt(bounds):
        for n,v in enumerate(original(bounds)):
            if n==2:clock[0]+=1
            yield v
    monkeypatch.setattr(module,'vectors',interrupt)
    result=run(simple(budget='.3',target='1',seconds='1'),lambda *a:FakeSearch(None,status=1))
    assert result.execution=='INCOMPLETE' and not any(r.search_complete for r in result.strategies)
    assert all(r.target_feasibility=='UNKNOWN' for r in result.strategies)
    assert result.strategies[0].enumerated_vectors==2


def test_fee_none_conflict_and_unknown_supplier_fee():
    data=simple();data['offers'][0]['payable_fee']='1'
    with pytest.raises(ValidationError):ProcurementInput.model_validate(data)
    data=simple();data['policy']['fee_mode']='PER_SUPPLIER_ORDER'
    result=run(data)
    assert result.execution=='BLOCKED'


def test_exclusion_numeric_range_never_creates_inexact_integer_cut():
    request=ProcurementInput.model_validate(simple())
    model=Model(request.policy.numeric)
    model.pack=[model.v('large_pack',2**52,integer=True)]
    # Pack itself is representable; a cut RHS at 2*upper+1 is not. Diagnose,
    # retaining the model unchanged rather than excluding an unproved neighborhood.
    before=(len(model.names),len(model.rows))
    with pytest.raises(NumericUnsupported,match='EXCLUSION_INTEGER_ROW_RANGE'):
        exclude_vector(model,(2**52,))
    assert (len(model.names),len(model.rows))==before
