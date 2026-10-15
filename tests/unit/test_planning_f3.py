"""F3 hand/finite oracles, identity/mask/budget/replay invariants; no real data fits."""
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import UUID
import sys
import pytest
from app.application.contracts.forecast_benchmark import ARMS,ArmCheckpoint,BenchmarkPrediction,BenchmarkDataset
from app.application.contracts.planning_impact import ImpactBinding
from app.application.contracts.planning_f3 import F3Binding,F3Plan,F3Run
from app.application.forecast_benchmark_admission import next_run
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.planning_impact import planning_request,plan_forecast,realized_evaluation,fraction
from app.application.planning_impact_oracle import finite_oracle
from app.application.planning_f3 import mass_balance,cost_balance,validate_fixed
from app.application.use_cases.procurement_v2 import evaluate_basket_v2
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
from tests.fixtures.forecast_engine.planning_f3_setup import operational_snapshot,FIXTURES
from tests.unit.test_procurement_v2 import NoCandidate

STORE=UUID(int=1);DAY=date(2026,6,24)
PRODUCTS=tuple(NS(product_id=UUID(int=100+i),selling_unit='ly') for i in range(5))


def snap(fixture='stock_only',origin=DAY):
    return operational_snapshot(origin,PRODUCTS,'Asia/Ho_Chi_Minh',STORE,fixture)


def binding(origin=DAY,variant='B_COMMON',first='100'):
    arm=ARMS[1] if variant=='B_COMMON' else ARMS[2]
    rows=tuple(BenchmarkPrediction(arm=arm,store_id=STORE,product_id=p.product_id,selling_unit='ly',origin=origin,
        partition='holdout',target_date=origin+timedelta(days=h),horizon=h,actual=None,stockout=None,mask='missing',
        p25=Decimal(first if h==1 else '0'),p50=Decimal(first if h==1 else '0'),p75=Decimal(first if h==1 else '0')) for p in PRODUCTS for h in range(1,8))
    checkpoint=ArmCheckpoint(arm=arm,origin=origin,identity='a'*64,status='COMPLETED',reason=None,predictions=rows,
        input_digest='b'*64,artifact_identity=None,training_seconds=Decimal(0),inference_seconds=Decimal(0))
    return ImpactBinding(checkpoint=checkpoint,output_digest=challenger_digest('e3-output',rows))


def truth(b):
    return BenchmarkDataset(classification='SYNTHETIC',use_authority='F3_HAND_TEST_ONLY',source_revision='test/1',
        availability_basis='synthetic_next_run',limitations=('Explicit synthetic hand-test truth; not benchmark label filling.',),
        store_id=STORE,timezone='Asia/Ho_Chi_Minh',products=[dict(product_id=p.product_id,selling_unit=p.selling_unit) for p in PRODUCTS],calendar=(),
        observations=[dict(store_id=STORE,product_id=r.product_id,sales_date=r.target_date,selling_unit='ly',quantity=r.p50,
            is_stockout=False,available_at=next_run(r.target_date,'Asia/Ho_Chi_Minh'),source='F3_HAND_TEST') for r in b.checkpoint.predictions])


def plan():
    origins=(DAY,DAY+timedelta(days=7))
    snapshots=tuple(snap(f,o) for o in origins for f in FIXTURES)
    forecasts=tuple(F3Binding(variant=v,forecast=binding(o,v),f2_identity='f'*64,endpoint_parameters_sha256=None)
        for o in origins for v in ('B_COMMON','C0_COMMON','C1_COMMON'))
    order=tuple((o,f,v) for o in origins for f in FIXTURES for v in ('B_COMMON','C0_COMMON','C1_COMMON'))
    return F3Plan(f2_identity='f'*64,origins=origins,snapshots=snapshots,forecasts=forecasts,run_order=order)


def test_zero_purchase_literal_expectation_and_mass_balance():
    b=binding();request=planning_request(snap(),b)
    def forbidden(*a,**k):pytest.fail('Zero purchase needs no native generator')
    selection=plan_forecast(request,forbidden)
    winner=next(o for o in selection.comparison.options if o.token==selection.winner_token)
    assert winner.basket==() and fraction(winner.outlay.total)==0
    assert all(fraction(p.fulfilled)==fraction(p.requested)==100 for p in winner.products)
    candidate=selection.comparison.source.strategies[0].candidate
    ledger=mass_balance(candidate.evaluation)
    assert len(ledger)==6 and all(r['consumed']=={'numerator':'500','denominator':'1'} for r in ledger)
    assert all(r['ending']=={'numerator':'99500','denominator':'1'} for r in ledger)


def test_small_purchase_independent_finite_oracle_cost_fee_pack_and_requirements():
    request=planning_request(snap('scarce_purchase'),binding())
    selected=plan_forecast(request,NoCandidate)
    winner=next(o for o in selected.comparison.options if o.token==selected.winner_token)
    assert [b.packs for b in winner.basket]==[2]
    assert fraction(winner.outlay.purchase)==40 and fraction(winner.outlay.payable_fees)==3 and fraction(winner.outlay.total)==43
    assert finite_oracle(request,selected.comparison.source)['status']=='FINITE_ORACLE_VERIFIED'
    assert all(s.customer_pass for s in selected.comparison.source.strategies)
    for s in selected.comparison.source.strategies:cost_balance(request,s.candidate)


def test_dated_recipe_loss_arrivals_expiry_exact_mass_and_units():
    request=planning_request(snap('dated_shared'),binding(first='50'))
    candidate=evaluate_basket_v2(request,(1,1))
    assert candidate is not None and {r.unit for r in candidate.evaluation.ingredients}=={'g','ml'}
    assert len(request.prepared.recipes)==10
    assert {a.arrival_day for a in candidate.arrivals}=={DAY+timedelta(days=1),DAY+timedelta(days=3)}
    assert all(r['incoming'] for r in mass_balance(candidate.evaluation))
    assert fraction(candidate.outlay)==70


@pytest.mark.parametrize('kind',['missing','censored','unknown'])
def test_incomplete_truth_is_unavailable_no_zero_fill(kind):
    b=binding();selection=plan_forecast(planning_request(snap(),b),NoCandidate)
    raw=truth(b).model_dump(mode='python')
    if kind=='missing':raw['observations']=raw['observations'][:-1]
    else:raw['observations'][-1]['is_stockout']=True if kind=='censored' else None
    result=realized_evaluation(BenchmarkDataset.model_validate(raw),b.checkpoint,selection)
    assert result.status=='UNAVAILABLE_INCOMPLETE_PRIMARY' and result.simulation is None


def test_tight_budget_keeps_reference_separate_no_realized_zero_basket():
    request=planning_request(snap('tight_budget'),binding())
    selection=plan_forecast(request,NoCandidate)
    assert selection.winner_token is None
    assert all(s.selection_kind in ('REFERENCE_NOT_RANKED','NONE') for s in selection.comparison.source.strategies)
    assert all(s.proof=='UNPROVEN' and s.customer_feasibility=='UNKNOWN' for s in selection.comparison.source.strategies)
    result=realized_evaluation(truth(binding()),binding().checkpoint,selection)
    assert result.status=='UNAVAILABLE_NO_WINNER' and result.simulation is None


def test_scored_targets_wrong_origin_and_quantile_digest_reject_planning():
    b=binding();raw=b.model_dump(mode='python');raw['checkpoint']['predictions'][0]['actual']=Decimal(1)
    raw['output_digest']=challenger_digest('e3-output',ArmCheckpoint.model_validate(raw['checkpoint']).predictions)
    with pytest.raises(ValueError,match='SCORED_TARGETS'):planning_request(snap(),ImpactBinding.model_validate(raw))
    with pytest.raises(ValueError,match='ORIGIN'):planning_request(snap(origin=DAY+timedelta(days=7)),b)
    raw=b.model_dump(mode='python');raw['output_digest']='e'*64
    with pytest.raises(ValueError,match='DIGEST'):planning_request(snap(),ImpactBinding.model_validate(raw))


def test_shared_facts_actual_independence_and_fixed_basket_replay_without_solver(monkeypatch):
    requests=[]
    for v in ('B_COMMON','C0_COMMON','C1_COMMON'):
        r=planning_request(snap(),binding(variant=v));raw=r.model_dump(mode='python')
        raw['prepared'].pop('forecast');raw['prepared']['request'].pop('forecast_run_id')
        raw['source_references']=[];raw['prepared']['source_references']=[];requests.append(raw)
    assert requests[0]==requests[1]==requests[2]
    b=binding();r=planning_request(snap(),b);selected=plan_forecast(r,NoCandidate)
    before=challenger_digest('planning',r)
    def forbidden(*a,**k):pytest.fail('Fixed basket replay must not optimize')
    monkeypatch.setattr('app.application.planning_impact.execute_procurement_v2',forbidden)
    validate_fixed(selected,r)
    raw=truth(b).model_dump(mode='python');raw['observations'][0]['quantity']=Decimal(999)
    realized_evaluation(BenchmarkDataset.model_validate(raw),b.checkpoint,selected)
    assert challenger_digest('planning',planning_request(snap(),b))==before


@pytest.mark.parametrize('what',['source','artifact','parameter','dataset','version'])
def test_input_source_artifact_parameter_dataset_version_tamper_rejects(tmp_path,monkeypatch,what):
    from app.infrastructure import planning_f3 as h
    p=plan();source=tmp_path/'source.py';source.write_text('original',encoding='utf-8')
    pins={}
    for n in ('artifact','parameter','dataset'):
        (tmp_path/(n+'.json')).write_text('{}',encoding='utf-8');pins[n+'.json']=h.sha(tmp_path/(n+'.json'))
    hashes={'source.py':h.sha(source)}
    monkeypatch.setattr(h,'sources',lambda root:{'source.py':h.sha(source)})
    monkeypatch.setattr(h,'current_runtime',lambda:NS(model_dump=lambda **k:{}))
    monkeypatch.setattr(h,'inputs',lambda root:(None,p.origins,p.forecasts,pins,{}))
    manifest=dict(plan=p,source=hashes,runtime={},inputs=pins,operational_admission={})
    identity=challenger_digest('planning-f3',manifest);store=BenchmarkStorage(tmp_path/'runtime/challenger/f3')
    out=store.path('experiments',identity);store.retain(out,'setup.json',manifest)
    h.load(tmp_path,identity)
    if what=='version':
        raw=p.model_dump(mode='python');raw['version']='planning_f3/2'
        with pytest.raises(ValueError):F3Plan.model_validate(raw)
    else:
        (source if what=='source' else tmp_path/(what+'.json')).write_text('tampered',encoding='utf-8')
        with pytest.raises(ValueError,match='CHANGED'):h.load(tmp_path,identity)


def test_consumed_child_claim_cannot_resume_or_reopen_budget(tmp_path,monkeypatch):
    from app.infrastructure import planning_f3 as h
    identity='a'*64;store=BenchmarkStorage(tmp_path);out=store.path('experiments',identity);out.mkdir(parents=True)
    store.retain(store.root,'bounded-batch-start.json',{'identity':identity});(out/'execution-claim.json').write_bytes(b'consumed')
    monkeypatch.setattr(h,'load',lambda *a:(store,out,None,None))
    def forbidden(*a,**k):pytest.fail('Consumed claim must stop before Planning')
    monkeypatch.setattr(h,'plan_forecast',forbidden)
    with pytest.raises(FileExistsError):h.execute(tmp_path,identity,attempts=[])
