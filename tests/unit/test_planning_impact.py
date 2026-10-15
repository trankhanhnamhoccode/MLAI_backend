"""Hand arithmetic and E4 separation invariants; synthetic complete truth is its own dataset."""
from datetime import date,datetime,timedelta
from decimal import Decimal
from fractions import Fraction as F
from uuid import UUID

import pytest

from app.application.contracts.forecast_benchmark import ARMS, ArmCheckpoint, BenchmarkDataset, BenchmarkPrediction
from app.application.contracts.planning_impact import ImpactSnapshot, ImpactBinding
from app.application.forecast_benchmark_admission import next_run
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.planning_impact import planning_request,plan_forecast,realized_evaluation,realized_metrics,fraction
from app.application.planning_impact_oracle import finite_oracle
from app.application.contracts.serving import ServingSimulationInput
from app.application.use_cases.serving import simulate_serving
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from scripts.procurement_demo_cases import snapshot,envelope,D,pid,iid
from scripts.procurement_v2_demo_cases import upgrade,path

DAY=date(2026,6,1)


def hand_snapshot(*,stock='2',pack='3',cost='2',minimum=2,upper=3,budget='5',fee='1'):
    data=upgrade(envelope(snapshot([[0]*7],[{0:1}],[(0,stock,D+timedelta(days=1))]),
        [dict(ingredient=0,pack=pack,cost=cost,minimum=minimum,upper=upper,shelf=0)],
        budget=budget,seconds='2',limit=32),[path('BASE','.95')])
    data['policy'].update(max_solves_per_strategy=4,fee_mode='PER_SUPPLIER_ORDER')
    data['supplier_fees']=[dict(supplier_id=UUID(int=2000),amount=fee,provenance='HAND_ORACLE explicit fee')]
    def shift(v):
        if isinstance(v,dict): return {k:shift(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)): return [shift(x) for x in v]
        if isinstance(v,(date,datetime)): return v+(DAY-D)
        return v
    data=shift(data)
    data['prepared']['forecast'].update(model_type='counterfactual_placeholder')
    data['prepared']['ingredients'][0]['expiry_tracking']=True
    return ImpactSnapshot(fixture_id='HAND_ORACLE_COMPLETE_TRUTH',origin=DAY,
        facts_known_at=next_run(DAY,'UTC'),template=data)


def binding(snapshot,values,arm=ARMS[0]):
    p=snapshot.template.prepared
    rows=tuple(BenchmarkPrediction(arm=arm,store_id=p.request.store_id,product_id=pid(0),selling_unit='cup',
        origin=DAY,partition='validation',target_date=DAY+timedelta(days=i+1),horizon=i+1,
        actual=None,stockout=None,mask='missing',p25=Decimal(v),p50=Decimal(v),p75=Decimal(v)) for i,v in enumerate(values))
    checkpoint=ArmCheckpoint(arm=arm,origin=DAY,identity='a'*64,status='COMPLETED',reason=None,predictions=rows,
        input_digest='b'*64,artifact_identity=None,training_seconds=Decimal(0),inference_seconds=Decimal(0))
    return ImpactBinding(checkpoint=checkpoint,output_digest=challenger_digest('e3-output',rows))


def truth(snapshot,values):
    p=snapshot.template.prepared
    return BenchmarkDataset(classification='SYNTHETIC',use_authority='HAND_ORACLE_COMPLETE_TRUTH/1',
        source_revision='hand-explicit-quantity/1',availability_basis='synthetic_next_run',
        limitations=('Separate hand-oracle truth; not E3 observed-target evidence.',),
        store_id=p.request.store_id,timezone='UTC',products=[dict(product_id=pid(0),selling_unit='cup')],calendar=(),
        observations=tuple(dict(store_id=p.request.store_id,product_id=pid(0),sales_date=DAY+timedelta(days=i+1),
            selling_unit='cup',quantity=Decimal(v),is_stockout=False,available_at=next_run(DAY+timedelta(days=i+1),'UTC'),
            source='HAND_ORACLE_COMPLETE_TRUTH/1') for i,v in enumerate(values)))


def test_integer_packs_moq_fee_and_expiry_hand_oracle():
    snap=hand_snapshot();b=binding(snap,[7,0,0,0,0,0,0])
    request=planning_request(snap,b);selection=plan_forecast(request,NativeProductSearch)
    winner=next(o for o in selection.comparison.options if o.token==selection.winner_token)
    assert winner.basket[0].packs==2
    assert fraction(winner.outlay.purchase)==4 and fraction(winner.outlay.payable_fees)==1
    assert fraction(winner.outlay.total)==5
    result=realized_evaluation(truth(snap,[7,0,0,0,0,0,0]),b.checkpoint,selection)
    metrics=realized_metrics(result)
    assert metrics['products'][0]['lost']=={'numerator':'0','denominator':'1'}
    ingredient=metrics['ingredients'][0]
    assert ingredient['consumed']=={'numerator':'7','denominator':'1'}
    assert ingredient['expired']=={'numerator':'1','denominator':'1'}
    assert ingredient['ending']=={'numerator':'0','denominator':'1'}
    assert finite_oracle(request,selection.comparison.source)['status']=='FINITE_ORACLE_VERIFIED'


def test_zero_purchase_winner_and_no_reoptimization_in_realized(monkeypatch):
    snap=hand_snapshot(stock='20');b=binding(snap,[7,0,0,0,0,0,0])
    selection=plan_forecast(planning_request(snap,b),NativeProductSearch)
    winner=next(o for o in selection.comparison.options if o.token==selection.winner_token)
    assert winner.basket==() and fraction(winner.outlay.total)==0
    def forbidden(*a,**k): pytest.fail('Realized evaluation must not optimize')
    monkeypatch.setattr('app.application.planning_impact.execute_procurement_v2',forbidden)
    result=realized_evaluation(truth(snap,[10,0,0,0,0,0,0]),b.checkpoint,selection)
    assert result.status=='COMPLETE_PRIMARY_OBSERVED'
    assert sum(fraction(r.fulfilled) for r in result.simulation.products if r.path_id=='BASE')==10


def test_budget_no_winner_keeps_null_and_reference_separate():
    snap=hand_snapshot(stock='0',budget='0');b=binding(snap,[7,0,0,0,0,0,0])
    selection=plan_forecast(planning_request(snap,b),NativeProductSearch)
    assert selection.winner_token is None
    assert any(s.selection_kind=='REFERENCE_NOT_RANKED' for s in selection.comparison.source.strategies)
    result=realized_evaluation(truth(snap,[7,0,0,0,0,0,0]),b.checkpoint,selection)
    assert result.status=='UNAVAILABLE_NO_WINNER' and result.simulation is None


@pytest.mark.parametrize('kind',['missing','censored','unknown'])
def test_incomplete_actuals_do_not_become_zero_or_complete_inventory_ledger(kind):
    snap=hand_snapshot(stock='20');b=binding(snap,[7,0,0,0,0,0,0])
    request=planning_request(snap,b);before=challenger_digest('planning',request)
    selection=plan_forecast(request,NativeProductSearch)
    data=truth(snap,[7,0,0,0,0,0,0]).model_dump(mode='python')
    if kind=='missing': data['observations']=data['observations'][:-1]
    else: data['observations'][-1]['is_stockout']=True if kind=='censored' else None
    result=realized_evaluation(BenchmarkDataset.model_validate(data),b.checkpoint,selection)
    assert result.status=='UNAVAILABLE_INCOMPLETE_PRIMARY' and result.simulation is None
    assert challenger_digest('planning',planning_request(snap,b))==before


def test_underbuy_overbuy_are_service_outlay_expiry_tradeoffs():
    snap=hand_snapshot(stock='0',pack='1',cost='1',minimum=1,upper=20,budget='30',fee='0')
    realized=truth(snap,[10,0,0,0,0,0,0])
    outputs=[]
    for demand in (5,15):
        b=binding(snap,[demand,0,0,0,0,0,0])
        selection=plan_forecast(planning_request(snap,b),NativeProductSearch)
        result=realized_evaluation(realized,b.checkpoint,selection)
        rows=[r for r in result.simulation.products if r.path_id=='BASE']
        waste=sum(fraction(r.expired) for r in result.simulation.ingredients if r.path_id=='BASE')
        outputs.append((sum(fraction(r.fulfilled) for r in rows),sum(fraction(r.lost) for r in rows),waste))
    assert outputs==[(5,5,0),(10,0,5)]


def test_arrivals_expiry_and_conservation_have_day_specific_oracle():
    snap=hand_snapshot(stock='1');b=binding(snap,[2,1,4,0,0,0,0])
    prepared=planning_request(snap,b).prepared
    result=simulate_serving(ServingSimulationInput(prepared=prepared,arrivals=[dict(lot_id=UUID(int=999),
        store_id=prepared.request.store_id,ingredient_id=iid(0),unit='g',arrival_day=DAY+timedelta(days=3),
        expiry_date=DAY+timedelta(days=3),quantity='6')]))
    rows=[r for r in result.products if r.path_id=='BASE']
    assert [fraction(r.fulfilled) for r in rows]==[1,0,4,0,0,0,0]
    assert sum(fraction(r.lost) for r in rows)==2
    ingredients=[r for r in result.ingredients if r.path_id=='BASE']
    assert sum(fraction(r.expired) for r in ingredients)==2
    assert 1+6==sum(fraction(r.consumed)+fraction(r.expired) for r in ingredients)+fraction(ingredients[-1].ending)


def test_shared_bottleneck_mixed_units_exact_progressive_serving():
    from tests.fixtures.forecast_engine.benchmark_setup import synthetic_benchmark
    from tests.fixtures.forecast_engine.planning_impact_setup import operational_snapshot
    data,plan=synthetic_benchmark()
    snap=operational_snapshot(plan.tasks[0].origin,data.products,data.timezone,'shared_purchase')
    raw=snap.template.prepared.model_dump(mode='python')
    raw['lots'][0]['on_hand_quantity']='6'
    raw['lots'][1]['on_hand_quantity']='1000'
    for row in raw['forecast']['predictions']:
        value='4' if row['product_id']==data.products[0].product_id else '2'
        for key in ('p25','p50','p75'): row[key]=value if row['forecast_date']==snap.origin+timedelta(days=1) else '0'
    result=simulate_serving(ServingSimulationInput(prepared=raw))
    rows=[r for r in result.products if r.path_id=='BASE' and r.day==snap.origin+timedelta(days=1)]
    assert {r.unit:fraction(r.fulfilled) for r in rows}=={'cup':F(3),'piece':F(3,2)}
    assert sum(fraction(r.consumed) for r in result.ingredients if r.path_id=='BASE' and r.unit=='g')==6


def test_scored_targets_and_changed_forecast_digest_cannot_enter_planning():
    snap=hand_snapshot();b=binding(snap,[7,0,0,0,0,0,0])
    changed=b.model_dump(mode='python');changed['checkpoint']['predictions'][0]['actual']=Decimal(9)
    changed['output_digest']=challenger_digest('e3-output',ArmCheckpoint.model_validate(changed['checkpoint']).predictions)
    with pytest.raises(ValueError,match='SCORED_TARGETS'): planning_request(snap,ImpactBinding.model_validate(changed))
    with pytest.raises(ValueError,match='OUTPUT_DIGEST'): planning_request(snap,b.model_copy(update={'output_digest':'c'*64}))


def test_common_facts_policy_resources_and_actual_independent_planning_identity():
    snap=hand_snapshot(stock='20')
    values=[]
    for i,arm in enumerate(ARMS):
        b=binding(snap,[5+i,0,0,0,0,0,0],arm)
        request=planning_request(snap,b)
        raw=request.model_dump(mode='python')
        raw['prepared'].pop('forecast')
        raw['prepared']['request'].pop('forecast_run_id')
        raw['prepared']['source_references']=[r for r in raw['prepared']['source_references'] if r['entity']!='forecast_run']
        raw['source_references']=[r for r in raw['source_references'] if r['entity']!='forecast_run']
        values.append(raw)
    assert values[0]==values[1]==values[2]
    b=binding(snap,[5,0,0,0,0,0,0])
    first=truth(snap,[10,0,0,0,0,0,0]);second=truth(snap,[99,0,0,0,0,0,0])
    request=planning_request(snap,b)
    before=challenger_digest('impact-planning-input',request)
    def forbidden(*a,**k): pytest.fail('Zero-purchase target pass needs no generator')
    selected=plan_forecast(request,forbidden)
    one=realized_evaluation(first,b.checkpoint,selected)
    two=realized_evaluation(second,b.checkpoint,selected)
    assert one.target_digest!=two.target_digest and one.simulation!=two.simulation
    assert challenger_digest('impact-planning-input',selected.comparison.source.input)==before


def test_persisted_resource_budget_cannot_reset_on_resume(tmp_path):
    from types import SimpleNamespace
    from app.application.use_cases.planning_impact import ImpactBudget,ImpactBudgetExceeded
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    storage=BenchmarkStorage(tmp_path)
    directory=storage.path('experiments','a'*64)
    storage.retain(directory,'resource-old.json',dict(seconds=300,solves=10))
    guard=ImpactBudget(storage,directory,SimpleNamespace(wall_seconds=300,maximum_native_solves=576))
    assert guard.solves==10
    with pytest.raises(ImpactBudgetExceeded,match='WALL_BUDGET'): guard.check()


def test_noncomplete_runs_report_failure_and_preserve_unpaired_availability():
    from app.application.contracts.planning_impact import ImpactRun
    from app.application.planning_impact import report_runs
    snap=hand_snapshot()
    b=binding(snap,[7,0,0,0,0,0,0])
    run=ImpactRun(identity='a'*64,snapshot_digest='b'*64,forecast_output_digest=b.output_digest,
        planning_input_digest='c'*64,binding=b,snapshot=snap,status='BUDGET_EXCEEDED',reason='WALL_BUDGET_EXCEEDED',
        selection=None,realized=None,elapsed_seconds=0.)
    report=report_runs([run],expected=48)
    assert report['status']=='INCOMPLETE' and report['paired_winner_groups']==0
    assert report['results'][0]['outlay'] is None
    assert report['results'][0]['realized_status']=='NOT_EVALUATED'
    assert len(report['exclusions'])==1


def test_dated_recipe_reciprocal_loss_and_yield_hand_oracle():
    from copy import deepcopy
    snap=hand_snapshot(stock='20');b=binding(snap,[1]*7)
    prepared=planning_request(snap,b).prepared.model_dump(mode='python')
    prepared['lots'][0]['expiry_date']=DAY+timedelta(days=7)
    first=prepared['recipes'][0]
    first.update(process_loss_rate=Decimal('.2'),effective_to=DAY+timedelta(days=3))
    later=deepcopy(first)
    later.update(id=UUID(int=999),version=2,effective_from=DAY+timedelta(days=4),effective_to=None,
                 yield_quantity=Decimal(2),process_loss_rate=Decimal(0))
    prepared['recipes']=(*prepared['recipes'],later)
    result=simulate_serving(ServingSimulationInput(prepared=prepared))
    rows=[r for r in result.ingredients if r.path_id=='BASE']
    assert sum(fraction(r.consumed) for r in rows)==F(23,4)
    assert sum(fraction(r.expired) for r in rows)==F(57,4)


def test_verifier_refuses_vacuous_success_without_any_completed_case(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    from app.application.use_cases.planning_impact import PlanningImpact
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from scripts import verify_planning_impact as verifier
    snap=hand_snapshot();b=binding(snap,[7,0,0,0,0,0,0])
    service=PlanningImpact(Path('.'))
    service.storage=BenchmarkStorage(tmp_path)
    directory=service.storage.path('experiments','d'*64)
    monkeypatch.setattr(service,'load',lambda identity:(directory,SimpleNamespace(snapshots=(snap,),forecasts=(b,)),truth(snap,[7,0,0,0,0,0,0]),'e'*64))
    monkeypatch.setattr(verifier,'PlanningImpact',lambda root:service)
    with pytest.raises(ValueError,match='NO_COMPLETED_CASES'):
        verifier.verify(Path('.'),'d'*64)
    assert not list(tmp_path.rglob('verify-*.json'))
