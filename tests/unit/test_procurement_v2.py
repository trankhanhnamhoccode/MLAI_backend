"""Hand expectations and independent finite ranking oracle; no fake simulator."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, localcontext, Inexact
from fractions import Fraction as F
from itertools import product
from uuid import UUID
import time
import pytest
from pydantic import ValidationError
from app.application.contracts.procurement_v2 import ProcurementInputV2, ProcurementResultV2, SolverEvidenceV2
from app.application.contracts.procurement_selection import WinnerSelection
from app.application.procurement_solver_v2 import ProposalV2
from app.application.use_cases.procurement_v2 import execute_procurement_v2, evaluate_basket_v2
from app.application.use_cases.procurement_selection import compare_procurement_v2, select_winner
from app.infrastructure.procurement_milp_v2 import NativeProductSearch, requirement_rows
from app.infrastructure.procurement_milp import build
from app.application.use_cases.procurement import captured_offers
from scripts.procurement_demo_cases import snapshot, envelope, simple, pid, iid, STORE, D
from scripts.procurement_v2_demo_cases import upgrade, path


def q(v):return F(int(v.numerator),int(v.denominator))


class NoCandidate:
    """Fault injected generator absence; exact enumeration still executes."""
    def __init__(self,*args):pass
    def solve(self,strategy,phase,deadline):
        return ProposalV2(SolverEvidenceV2(phase=phase,status=2,message='FAULT INJECTED NO INCUMBENT',
            incumbent=False,objective=None,bound=None,gap=None,nodes=0,seconds=0,variables=0,constraints=0,
            solver_version='FAULT INJECTION',time_limit=0),None)
    def exclude(self,*args,**kwargs):pass
    def accept(self,*args):pass


class Fixed(NoCandidate):
    """Explicit candidate injection to isolate exact classification/selector, not native proof."""
    def __init__(self,counts,status=0,error=None):self.counts=counts;self.status=status;self.error=error
    def solve(self,strategy,phase,deadline):
        if self.error:raise self.error
        old=super().solve(strategy,phase,deadline).evidence.model_dump()
        old.update(status=self.status,incumbent=True,extracted_counts=self.counts)
        return ProposalV2(SolverEvidenceV2(**old),self.counts)


def run(data,factory=NativeProductSearch):
    return execute_procurement_v2(ProcurementInputV2.model_validate(data),factory)


def facts(candidate):
    result={}
    for r in candidate.evaluation.products:
        key=r.path_id,r.product_id
        requested,served=result.get(key,(F(0),F(0)))
        result[key]=requested+q(r.requested),served+q(r.fulfilled)
    return result


def customer_pass(data,values):
    for rule in data['requirements']['paths']:
        overrides={r['product_id']:F(r['target']) for r in rule['overrides']}
        for p in data['prepared']['request']['product_ids']:
            requested,served=values[rule['path'],p]
            if served < requested*overrides.get(p,F(rule['minimum'])):return False
    return True


def stable(c):
    return tuple((str(b.term_id),b.packs) for b in c.basket)


def oracle(data):
    """Independent itertools search and ranking over the canonical exact serving policy.

    No production gaps/keys/selector used for expected results. The fixed-basket
    evaluator supplies serving/FEFO/hard validity, not the search or ranking.
    """
    request=ProcurementInputV2.model_validate(data)
    candidates=[]
    for counts in product(*(range(o.bound.maximum_packs+1) for o in request.offers)):
        c=evaluate_basket_v2(request,counts)
        if c is not None:
            terms={t.id:t for t in request.prepared.supplier_terms}
            money=sum((F(terms[o.term_id].pack_cost)*n for o,n in zip(request.offers,counts)),F(0))
            if request.policy.fee_mode=='PER_OFFER':money+=sum((F(o.payable_fee) for o,n in zip(request.offers,counts) if n),F(0))
            if request.policy.fee_mode=='PER_SUPPLIER_ORDER':
                suppliers={terms[o.term_id].supplier_id for o,n in zip(request.offers,counts) if n}
                money+=sum((F(f.amount) for f in request.supplier_fees if f.supplier_id in suppliers),F(0))
            assert q(c.outlay)==money
            candidates.append((c,facts(c)))
    choices=[]
    for construction in ('LOW','BASE','HIGH'):
        passing=[(c,v) for c,v in candidates if customer_pass(data,v)]
        target=[(c,v) for c,v in passing if all(served==req for (s,p),(req,served) in v.items() if s==construction)]
        def fallback(item):
            c,v=item;ratios=[served/req for (s,p),(req,served) in v.items() if s==construction and req]
            return (-min(ratios) if ratios else 0,-sum(ratios)/len(ratios) if ratios else 0,q(c.outlay),stable(c))
        pool=target or passing
        key=(lambda item:(q(item[0].outlay),stable(item[0]))) if target else fallback
        choices.append(min(pool,key=key)[0] if pool else None)
    return choices


@pytest.mark.parametrize('case',range(6))
def test_small_exhaustive_oracle_and_native(case):
    data=snapshot([[2,0,0,0,0,0,0],[3,0,0,0,0,0,0]],[{0:1},{1:1}])
    for p in data['forecast']['predictions']:
        value=F(p['p50']);p['p25']=str(float(value/2));p['p75']=str(float(value*2))
    specs=[dict(ingredient=i,pack='1',cost=str(i+1),upper=3,minimum=1+(case%2)) for i in range(2)]
    data=upgrade(envelope(data,specs,budget=str(3+case),seconds='30',limit=16),
                 [path('BASE','0.2',[(pid(0),'0.5')]),path('HIGH','0.1')])
    expected=oracle(data)
    result=run(data)
    assert result.execution=='FINISHED'
    for row,want in zip(result.strategies,expected):
        assert row.proof=='COMPLETE_EXACT_ENUMERATION'
        assert (row.candidate.counts if row.customer_pass else None)==(want.counts if want else None)
    assert any(row.solver for row in result.strategies)


def test_multi_path_override_replace_and_mixed_units():
    data=snapshot([[2,0,0,0,0,0,0],[4,0,0,0,0,0,0]],[{0:1},{1:1}])
    data['products'][1]['selling_unit']='piece'
    for r in data['forecast']['predictions']:
        if r['product_id']==pid(1):r['unit']='piece'
    data=upgrade(envelope(data,[dict(ingredient=i,pack='1',cost='1',upper=4) for i in range(2)],budget='3'),
                 [path('BASE','1',[(pid(1),'0.25')]),path('HIGH','0.25')])
    result=run(data,NoCandidate)
    assert result.strategies[1].customer_pass and not result.strategies[1].construction_pass
    assert result.strategies[1].candidate.counts==(2,1)
    assert all(m.product_id is not None for m in result.strategies[1].candidate.services)
    selected=select_winner(compare_procurement_v2(result))
    assert selected.winner_token is not None


def test_fallback_minimum_before_mean_then_cost():
    data=upgrade(envelope(snapshot([[2,0,0,0,0,0,0],[8,0,0,0,0,0,0]],[{0:1},{1:1}]),
        [dict(ingredient=i,pack='1',cost='1',upper=2) for i in range(2)],budget='2'),[path('BASE','0')])
    result=run(data)
    assert all(r.candidate.counts==(1,1) for r in result.strategies)  # min=.125, not mean-max (2,0)
    data['prepared']['products'].append(dict(store_id=STORE,product_id=pid(2),sku='P2',selling_unit='cup'))
    # Build third Product with no available Ingredient to pin the minimum at zero.
    third=snapshot([[2,0,0,0,0,0,0],[8,0,0,0,0,0,0],[1,0,0,0,0,0,0]],[{0:1},{1:1},{2:1}])
    data=upgrade(envelope(third,[dict(ingredient=i,pack='1',cost='1',upper=2) for i in range(2)],budget='2'),[path('BASE','0')])
    assert all(r.candidate.counts==(2,0) for r in run(data).strategies)  # mean 1/3 before cheaper .5/3


def test_exact_tiny_above_point_three_native_research():
    data=upgrade(simple(demand=1),[path('BASE','0.300000000000000000000000000001')])
    data['offers'][0]['bound']['maximum_packs']=4
    data['prepared']['supplier_terms'][0].update(pack_size_base_quantity='.1',pack_cost='1')
    for point in data['prepared']['forecast']['predictions']:
        if point['forecast_date']==D+timedelta(days=1):point['p25']='.3'
    result=run(data)
    assert result.strategies[0].candidate.counts==(4,)
    assert result.strategies[0].customer_gaps[0].target==Decimal('0.300000000000000000000000000001')
    request=ProcurementInputV2.model_validate(data)
    c=evaluate_basket_v2(request,(3,))
    assert facts(c)['BASE',pid(0)]==(F(1),F(3,10))
    assert not customer_pass(data,facts(c))
    assert any(e.counts==(3,) and not e.customer_pass for e in result.strategies[0].journal)


@pytest.mark.parametrize('bad',[True,0.3,'NaN','Infinity','-1','1.01'])
def test_requirements_reject_bad_numeric(bad):
    data=upgrade(simple(),[path('BASE',bad)])
    with pytest.raises(ValidationError):ProcurementInputV2.model_validate(data)


def test_capture_detached_ordering_ambient_context_and_public_revalidation():
    data=upgrade(simple(),[path('BASE','0.2')]);request=ProcurementInputV2.model_validate(data)
    expected=evaluate_basket_v2(request,(3,))
    data['prepared']['recipes'][0]['lines'][0]['quantity']='999'
    assert evaluate_basket_v2(request,(3,))==expected
    with localcontext() as context:
        context.prec=2;context.traps[Inexact]=True
        assert evaluate_basket_v2(request,(3,))==expected
    bad=request.model_copy(update={'requirements':request.requirements.model_copy(update={'paths':()})})
    with pytest.raises(ValidationError):execute_procurement_v2(bad,NoCandidate)
    other=request.model_dump()
    other['prepared']['forecast']['predictions']=tuple(reversed(other['prepared']['forecast']['predictions']))
    assert evaluate_basket_v2(ProcurementInputV2.model_validate(other),(3,))==expected


def test_zero_demand_budget_purchase_grouping_and_no_fabricated_ratio():
    data=upgrade(simple(demand=0,budget='0'),[path('BASE','1')])
    result=run(data)
    assert all(r.customer_pass and r.construction_pass and r.candidate.counts==(0,) for r in result.strategies)
    assert all(m.service is None for m in result.strategies[0].candidate.services)
    comparison=compare_procurement_v2(result)
    assert len(comparison.options)==1 and len(comparison.options[0].source_strategies)==3
    assert select_winner(comparison).winner_token==comparison.options[0].token


def test_customer_fail_reference_vs_certified_no_pass():
    data=upgrade(simple(budget='0'),[path('BASE','.95')])
    result=run(data,NoCandidate)
    assert all(r.customer_feasibility=='NO_PASS_CERTIFIED' and r.selection_kind=='REFERENCE_NOT_RANKED' for r in result.strategies)
    selection=select_winner(compare_procurement_v2(result))
    assert selection.winner_token is None and selection.rejected
    data['policy'].update(certification='DISABLED',certification_vector_limit=0)
    result=run(data,NoCandidate)
    assert all(r.customer_feasibility=='UNKNOWN' for r in result.strategies)


def test_deadline_incumbent_and_technical_failure_preserve_evidence():
    data=upgrade(simple(certification='DISABLED'),[path('BASE','.1')])
    result=run(data,lambda *a:Fixed((10,),status=1))
    assert result.execution=='INCOMPLETE'
    assert all(r.proof=='UNPROVEN' for r in result.strategies)
    assert select_winner(compare_procurement_v2(result)).winner_token
    factories=iter([Fixed((10,),status=1),Fixed((0,),error=ValueError('INJECTED PROGRAMMING ERROR')),Fixed((10,),status=1)])
    result=run(data,lambda *a:next(factories))
    assert result.execution=='ERROR' and 'PROGRAMMING ERROR' in result.strategies[1].diagnostic
    comparison=compare_procurement_v2(result)
    assert select_winner(comparison).winner_token
    assert comparison.source.execution=='ERROR'


@pytest.mark.parametrize('which',['HIGH','BASE','LOW','COST'])
def test_hand_winner_ties_and_money_priority(which):
    demands=[[2,0,0,0,0,0,0],[2,0,0,0,0,0,0]]
    raw=snapshot(demands,[{0:1},{1:1}])
    if which=='BASE':
        for r in raw['forecast']['predictions']:
            if r['product_id']==pid(0) and r['p50']=='2':r.update(p25='1',p50='1')
        a,b=(1,2),(2,1)
    elif which=='LOW':
        for r in raw['forecast']['predictions']:
            if r['product_id']==pid(0) and r['p25']=='2':r['p25']='1'
        a,b=(1,2),(2,1)
    elif which=='HIGH':
        for r in raw['forecast']['predictions']:
            if r['p75']=='2':r['p75']='4'
        a,b=(1,3),(2,2)
    else:a,b=(1,1),(2,2)
    data=upgrade(envelope(raw,[dict(ingredient=i,pack='1',cost='1',upper=4) for i in range(2)],
        certification='DISABLED'),[path('BASE','.1')])
    sequence=iter([Fixed(a),Fixed(b),NoCandidate()])
    source=run(data,lambda *args:next(sequence))
    selection=select_winner(compare_procurement_v2(source))
    chosen=next(o for o in selection.comparison.options if o.token==selection.winner_token)
    expected=b if which=='HIGH' else a
    assert tuple(next((l.packs for l in chosen.basket if l.ingredient_id==iid(i)),0) for i in range(2))==expected


def test_fee_moq_arrival_expiry_capacity_and_gap_truth():
    raw=snapshot([[1,1,0,0,0,0,0]],[{0:1}])
    data=upgrade(envelope(raw,[dict(ingredient=0,pack='1',cost='1',fee='2',upper=3,minimum=2,lead=1,shelf=0)]),[path('BASE','.5')])
    data['policy']['fee_mode']='PER_OFFER'
    data['capacities']=[dict(store_id=STORE,ingredient_id=iid(0),unit='g',maximum_quantity='2',
        checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',provenance='SYNTHETIC')]
    request=ProcurementInputV2.model_validate(data)
    assert evaluate_basket_v2(request,(1,)) is None  # MOQ
    assert evaluate_basket_v2(request,(3,)) is None  # capacity
    result=run(data)
    c=result.strategies[1].candidate
    assert c.counts==(2,) and q(c.outlay)==4
    assert facts(c)['BASE',pid(0)]==(F(2),F(1))  # arrival too late for day one
    option=compare_procurement_v2(result).options[0]
    assert option.outlay.delivery_fees is None and option.outlay.fee_classification=='PAYABLE_FEE_TYPE_NOT_CAPTURED'


def test_forged_results_and_winner_rejected():
    result=run(upgrade(simple(),[path('BASE','.5')]),NoCandidate)
    row=result.strategies[0].model_copy(update={'customer_pass':False})
    with pytest.raises(ValidationError):ProcurementResultV2.model_validate(result.model_copy(update={'strategies':(row,*result.strategies[1:])}))
    selected=select_winner(compare_procurement_v2(result))
    with pytest.raises(ValidationError):WinnerSelection.model_validate(selected.model_copy(update={'winner_token':None}))
    with pytest.raises(ValidationError):ProcurementResultV2.model_validate(result.model_copy(update={'unique_exact_evaluations':999}))
    with pytest.raises(ValidationError):ProcurementResultV2.model_validate(result.model_copy(update={'deadline_overrun_seconds':999}))
    row=result.strategies[0]
    entry=row.journal[0].model_copy(update={'reasons':('FABRICATED',)})
    forged=row.model_copy(update={'journal':(entry,*row.journal[1:])})
    with pytest.raises(ValidationError):ProcurementResultV2.model_validate(result.model_copy(update={'strategies':(forged,*result.strategies[1:])}))


def test_search_limit_without_incumbent_is_unknown_not_infeasible():
    class Limit(NoCandidate):
        def solve(self,strategy,phase,deadline):
            evidence=super().solve(strategy,phase,deadline).evidence.model_copy(update={'status':1})
            return ProposalV2(evidence,None)
    result=run(upgrade(simple(certification='DISABLED'),[path('BASE','1')]),Limit)
    assert result.execution=='INCOMPLETE'
    assert all(r.termination=='SEARCH_LIMIT_NO_INCUMBENT' and r.customer_feasibility=='UNKNOWN'
               and r.proof=='UNPROVEN' for r in result.strategies)
    assert select_winner(compare_procurement_v2(result)).winner_token is None


@pytest.mark.parametrize('blocker',['fees','budget','captured'])
def test_blocked_input_never_calls_search_or_fabricates_proof(blocker):
    data=upgrade(simple(certification='DISABLED'),[path('BASE','0')])
    if blocker=='fees':data['policy']['fee_mode']='PER_OFFER'
    elif blocker=='budget':data['budget'].update(state='UNKNOWN',amount=None)
    else:data['prepared']['issues']=[dict(kind='DATA_BLOCKER',code='SYNTHETIC_MISSING',field='quantity',
        affected=[dict(entity='ingredient',entity_id=iid(0))],impact='Missing captured data',suggested_action='Capture facts')]
    def forbidden(*args):raise AssertionError('Search must not be called')
    result=run(data,forbidden)
    assert result.execution=='BLOCKED' and all(r.candidate is None and not r.solver for r in result.strategies)
    assert select_winner(compare_procurement_v2(result)).winner_token is None
    forged=result.strategies[0].model_copy(update={'proof':'COMPLETE_EXACT_ENUMERATION','search_complete':True})
    with pytest.raises(ValidationError):ProcurementResultV2.model_validate(result.model_copy(update={'strategies':(forged,*result.strategies[1:])}))


def test_stable_basket_tie_and_grouping_retains_source_evidence():
    # Same physical Ingredient, two supplier terms: identical money and all services.
    data=upgrade(envelope(snapshot([[1,0,0,0,0,0,0]],[{0:1}]),
        [dict(ingredient=0,pack='1',cost='1',upper=1),dict(ingredient=0,pack='1',cost='1',upper=1,supplier=1)],
        certification='DISABLED'),[path('BASE','1')])
    sequence=iter([Fixed((0,1),status=1),Fixed((1,0)),Fixed((1,0),status=1)])
    result=run(data,lambda *args:next(sequence))
    comparison=compare_procurement_v2(result)
    assert len(comparison.options)==2
    grouped=next(o for o in comparison.options if len(o.source_strategies)==2)
    assert grouped.source_strategies==('BALANCED','PROTECTED')
    assert [r.execution for r in comparison.source.strategies]==['INCOMPLETE','FINISHED','INCOMPLETE']
    assert all(r.proof=='UNPROVEN' for r in comparison.source.strategies)
    assert select_winner(comparison).winner_token==grouped.token  # smaller term UUID, not LEAN


def test_legacy_identity_tokens_unchanged_and_v2_admission_separate():
    import json
    from app.application.contracts.procurement import ProcurementInput
    from app.application.use_cases.procurement import evaluate_procurement_basket
    from app.application.procurement_comparison_facts import plan_identity,evaluation_identity
    old=ProcurementInput.model_validate(simple())
    c=evaluate_procurement_basket(old,(1,))
    plan=json.loads(plan_identity(old,c));evaluation=json.loads(evaluation_identity(c))
    assert 'capture_version' not in plan['context']['prepared']
    assert 'capture_version' not in evaluation['evaluation']['input']['prepared']
    # Adding the default field to original /1 input cannot change historical tokens.
    raw=old.model_dump();raw['prepared'].pop('capture_version')
    assert plan_identity(ProcurementInput.model_validate(raw),c)==plan_identity(old,c)
    modern=ProcurementInputV2.model_validate(upgrade(simple(),[path('BASE','0')]))
    assert json.loads(plan_identity(modern,evaluate_basket_v2(modern,(1,))))['context']['prepared']['capture_version']==2


def test_effective_requirements_scope_and_no_implicit_default():
    data=upgrade(simple(),[path('BASE','0')])
    data['requirements']['paths'].append(path('BASE','1'))
    with pytest.raises(ValidationError):ProcurementInputV2.model_validate(data)
    data=upgrade(simple(),[path('BASE','0',[(UUID(int=999999),'1')])])
    with pytest.raises(ValidationError):ProcurementInputV2.model_validate(data)
    data=upgrade(simple(),[])
    with pytest.raises(ValidationError):ProcurementInputV2.model_validate(data)


@pytest.mark.parametrize('demand,minimum',[(10,'1e-1001'),('.001','1e-999')])
def test_numeric_capacity_failure_is_typed_without_partial_cache_evidence(demand,minimum):
    def forbidden(*args):raise AssertionError('Unsupported numeric facts must not reach search')
    result=run(upgrade(simple(demand=demand,certification='DISABLED'),[path('BASE',minimum)]),forbidden)
    assert result.execution=='NUMERIC_UNSUPPORTED' and result.unique_exact_evaluations==0
    assert all(r.candidate is None and not r.journal and r.customer_feasibility=='UNKNOWN'
               and r.diagnostic and r.proof=='UNPROVEN' for r in result.strategies)
