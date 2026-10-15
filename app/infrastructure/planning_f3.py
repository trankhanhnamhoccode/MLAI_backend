"""F3 storage/orchestration reusing E4 budget, binding, oracle and host computation."""
import hashlib
import json
import os
from pathlib import Path
from time import monotonic
from decimal import Decimal
from app.application.contracts.forecast_benchmark import ArmCheckpoint,BenchmarkPrediction
from app.application.contracts.planning_impact import ImpactBinding,RealizedImpact
from app.application.contracts.planning_f3 import F3Binding,F3Plan,F3Run
from app.application.forecast_challenger_serialization import challenger_digest,canonical_bytes
from app.application.planning_impact import planning_request,plan_forecast,realized_evaluation
from app.application.planning_impact_oracle import finite_oracle
from app.application.planning_f3 import summarize,validate_fixed,cost_balance,mass_balance
from app.application.use_cases.planning_impact import ImpactBudget,ImpactBudgetExceeded
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.forecast_f2_harness import admitted as admitted_f2,SOURCE_FILES as F2_SOURCE_FILES
from app.infrastructure.planning_impact_source import source_identity

F2='ee4d7cb4de28dabb842c8900b4ebb3b9b32e8f423bd5f6611395f539323ecbc7'
VARIANTS=(('B_COMMON','B_common'),('C0_COMMON','C0'),('C1_COMMON','C1'))
BASE='runtime/challenger/dataset-admission/datasets/571fb650d4a867e7e8e51e485fc83b960dc5c1dd4aa52ab260d9a924c67ad21d'
OWN_SOURCES=('app/infrastructure/planning_f3.py','app/application/planning_f3.py',
    'app/application/contracts/planning_f3.py','scripts/planning_f3.py','tests/fixtures/forecast_engine/planning_f3_setup.py')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def inputs(root):
    store,out,spec,ctx=admitted_f2(root,F2)
    data,parent,_,_,_,_,pins=ctx
    pins=dict(pins)
    def load(directory,name):
        pins[(directory/name).relative_to(root).as_posix()]=sha(directory/name)
        return store.load(directory,name)
    variants=load(out,'predictions.json');admission=load(out,'admission.json')
    load(out,'summary.json');load(out,'execution.json')
    origins=tuple(t.origin for t in parent.tasks[-2:])
    bindings=[]
    for origin in origins:
        for variant,label in VARIANTS:
            raw=tuple(BenchmarkPrediction.model_validate(r|dict(actual=None,stockout=None,mask='missing'))
                      for r in variants[label] if r['origin']==str(origin))
            if len(raw)!=len(data.products)*7 or len({(r.product_id,r.target_date) for r in raw})!=len(raw):
                raise ValueError('F3_COMPLETE_FORECAST_SCOPE_REQUIRED')
            endpoint=sha(out/(str(origin)+'-parameters.json')) if variant=='C1_COMMON' else None
            if variant=='C1_COMMON':load(out,str(origin)+'-parameters.json')
            arm=raw[0].arm
            original=load(root/'runtime/challenger/benchmarks/experiments'/spec.parent_experiment,str(origin)+'-'+arm+'.json')
            key=challenger_digest('f3-forecast-binding',dict(f2=F2,variant=variant,origin=origin,rows=raw,endpoint=endpoint))
            checkpoint=ArmCheckpoint(arm=arm,origin=origin,identity=key,status='COMPLETED',reason=None,predictions=raw,
                artifact_identity=original['artifact_identity'],input_digest=key,training_seconds=Decimal(0),inference_seconds=Decimal(0))
            bindings.append(F3Binding(variant=variant,forecast=ImpactBinding(checkpoint=checkpoint,
                output_digest=challenger_digest('e3-output',raw)),f2_identity=F2,endpoint_parameters_sha256=endpoint))
    previous=load(root/BASE,'admission.json');load(root/BASE,'operational-evidence.json')
    if previous['E4']!='BLOCKED':raise ValueError('F3_OPERATIONAL_ADMISSION_CHANGED_REVIEW_REQUIRED')
    physical={p.relative_to(root).as_posix():sha(p) for p in (root/'runtime').rglob('*.xlsx')}
    if physical!={p:h for p,h in pins.items() if p.endswith('.xlsx')}:
        raise ValueError('F3_NEW_WORKBOOK_OR_HASH_REQUIRES_REVIEW')
    operational=dict(source_faithful='BLOCKED',source_revision=data.source_revision,
        source_evidence=BASE+'/operational-evidence.json',source_admission=BASE+'/admission.json',
        source_findings=[dict(area=f['area'],code=f['code'],classification=f['classification'],detail=f['detail']) for f in previous['findings'] if f['area']=='E4'],
        sourced=dict(products=data.products,timezone=data.timezone,forecast_origins=origins,raw_files=physical),
        declarations='Existing hash-bound five-single-Product/retrospective POS/calendar declarations only; no new real operational declaration.',
        unavailable=dict(recipes='Unit aliases/serving basis/yield/effectivity/loss unresolved; raw lines retained, not imported into synthetic recipes.',
            stock='Only08/07 snapshot; no historical full stock/lot/completeness at selected origins. No receipts inferred from purchase history.',
            suppliers='Price denominator/pack/MOQ/lead/effectivity and fee coverage not established for historical planning.',
            constraints='Mandatory safety-stock/aggregate semantics unsupported; source-faithful remains BLOCKED.',
            truth='POS+recipe usage is not independent demand/consumption truth; censored/unknown/missing labels are not complete demand.'),
        synthetic='F3_SYNTHETIC: recipes, loss/effectivity, Ingredient IDs g/ml, complete starting lots, expiry, offers/MOQ/pack cost/arrival/shelf life, generic fees, budget,95% BASE requirements and capacities explicitly fictional.',
        authority='Explicit user F3 task authorizes counterfactual fixtures, not canonical Store facts or safety-stock policy.',production='LOCKED')
    return data,origins,tuple(bindings),pins,operational


def sources(root):
    _,hashes=source_identity(root)
    for name in (*OWN_SOURCES,*F2_SOURCE_FILES):hashes[name]=sha(root/name)
    return hashes


def freeze(root):
    from tests.fixtures.forecast_engine.planning_f3_setup import FIXTURES,operational_snapshot
    data,origins,bindings,pins,operational=inputs(root)
    snapshots=tuple(operational_snapshot(o,data.products,data.timezone,data.store_id,f) for o in origins for f in FIXTURES)
    order=[]
    for i,o in enumerate(origins):
        for j,f in enumerate(FIXTURES):
            arms=[v for v,_ in VARIANTS];shift=(i+j)%3
            order.extend((o,f,a) for a in arms[shift:]+arms[:shift])
    plan=F3Plan(f2_identity=F2,origins=origins,snapshots=snapshots,forecasts=bindings,run_order=tuple(order))
    manifest=dict(plan=plan,source=sources(root),inputs=pins,runtime=current_runtime(),operational_admission=operational,
        limitations=('Post-hoc exposed forecasts; synthetic operational scenarios, not real savings.',
            'Native default seed/options unchanged; deterministic rotating arm order, single repetition, cold/warm/deadline effects reported.',
            'No candidate/cache carry-over between arms. Certification only tiny domains≤9; tight-budget disabled.',
            'C1 is not validation-selected and cannot be selected by impact. All24 runs and no-winner cases stay in report.'))
    identity=challenger_digest('planning-f3',manifest)
    store=BenchmarkStorage(root/'runtime/challenger/f3');out=store.path('experiments',identity)
    store.retain(out,'setup.json',manifest)
    return dict(status='F3_FROZEN_BEFORE_SOLVES',identity=identity,origins=origins,runs=24,
        maximum_native_solves=144,per_run_seconds='4',max_solves_per_strategy=2,wall_seconds=300,
        classification='F3_SYNTHETIC',source_faithful='BLOCKED',output=str(out))


def load(root,identity):
    store=BenchmarkStorage(root/'runtime/challenger/f3');out=store.path('experiments',identity)
    manifest=store.load(out,'setup.json')
    if manifest is None or challenger_digest('planning-f3',manifest)!=identity:raise ValueError('F3_IDENTITY_CHANGED')
    if manifest['source']!=sources(root) or manifest['runtime']!=current_runtime().model_dump(mode='json'):
        raise ValueError('F3_SOURCE_OR_RUNTIME_CHANGED')
    for path,h in manifest['inputs'].items():
        p=root/path
        if not p.resolve().is_relative_to(root) or sha(p)!=h:raise ValueError('F3_INPUT_OR_PARAMETER_CHANGED:'+path)
    data,origins,bindings,pins,operational=inputs(root)
    plan=F3Plan.model_validate(manifest['plan'])
    if origins!=plan.origins or bindings!=plan.forecasts or pins!=manifest['inputs'] or canonical_bytes(operational)!=canonical_bytes(manifest['operational_admission']):
        raise ValueError('F3_BINDINGS_CHANGED')
    return store,out,plan,data


def case_input(plan,origin,fixture,variant,identity):
    snap=next(s for s in plan.snapshots if (s.origin,s.fixture_id)==(origin,fixture))
    binding=next(b.forecast for b in plan.forecasts if (b.forecast.checkpoint.origin,b.variant)==(origin,variant))
    request=planning_request(snap,binding)
    input_digest=challenger_digest('impact-planning-input',request);snapshot_digest=challenger_digest('impact-snapshot',snap)
    key=challenger_digest('f3-case',dict(experiment=identity,snapshot=snapshot_digest,forecast=binding.output_digest,variant=variant,input=input_digest))
    return key,request,snap,binding,input_digest,snapshot_digest


def execute(root,identity,*,attempts):
    store,out,plan,data=load(root,identity)
    marker=store.load(store.root,'bounded-batch-start.json')
    if marker is None or marker['identity']!=identity:raise ValueError('F3_BATCH_NOT_ADMITTED')
    claim=canonical_bytes(dict(identity=identity,maximum_runs=24,maximum_native_solves=144))
    with (out/'execution-claim.json').open('xb') as file:
        file.write(canonical_bytes(dict(sha256=hashlib.sha256(claim).hexdigest(),value=json.loads(claim))))
        file.flush()
        os.fsync(file.fileno())
    guard=ImpactBudget(store,out,plan);runs=[];order=[];checks=[]
    for position,(origin,fixture,variant) in enumerate(plan.run_order):
        if guard.exhausted:break
        key,request,snap,binding,input_digest,snapshot_digest=case_input(plan,origin,fixture,variant,identity)
        started=monotonic();selection=None;realized=None;status='COMPLETED';reason=None
        try:
            guard.check();selection=plan_forecast(request,guard.factory)
            if guard.exhausted:raise ImpactBudgetExceeded('F3_COOPERATIVE_BUDGET_EXCEEDED')
            if selection.comparison.source.execution in ('ERROR','NUMERIC_UNSUPPORTED'):
                status='TECHNICAL_FAILURE';reason='HOST_'+selection.comparison.source.execution
            if status=='COMPLETED':
                realized=realized_evaluation(data,binding.checkpoint,selection)
        except Exception as error:
            status='BUDGET_EXCEEDED' if isinstance(error,ImpactBudgetExceeded) else 'TECHNICAL_FAILURE'
            reason=str(error) if isinstance(error,ImpactBudgetExceeded) else type(error).__name__+':'+str(error)[:160]
            if isinstance(error,ImpactBudgetExceeded):guard.exhausted=True
        finally:guard.retain()
        run=F3Run(variant=variant,f2_identity=F2,identity=key,snapshot_digest=snapshot_digest,
            forecast_output_digest=binding.output_digest,planning_input_digest=input_digest,binding=binding,snapshot=snap,
            status=status,reason=reason,selection=selection,realized=realized,elapsed_seconds=monotonic()-started)
        store.retain(out,'case-'+key+'.json',run);runs.append(run)
        if selection is not None:
            for strategy in selection.comparison.source.strategies:
                c=strategy.candidate
                if c is not None:
                    checks.append(dict(case=key,strategy=strategy.strategy,cost=cost_balance(request,c),
                        exact_mass_balanced_lots=len(mass_balance(c.evaluation))))
        if realized is not None and realized.simulation is not None:mass_balance(realized.simulation)
        if origin==plan.origins[0] and variant=='B_COMMON' and fixture in ('stock_only','scarce_purchase') and selection is not None:
            try:oracle=finite_oracle(request,selection.comparison.source)
            except ValueError as error:oracle=dict(status='ORACLE_DISAGREEMENT',reason=str(error),native_proof=False)
            store.retain(out,'oracle-'+fixture+'.json',oracle)
        order.append(dict(position=position,origin=origin,fixture=fixture,variant=variant,elapsed_seconds=run.elapsed_seconds,
            native_solves_so_far=guard.solves,status=status))
        progress=dict(completed_attempts=len(runs),expected=24,solves=guard.solves,seconds=monotonic()-guard.started)
        store.retain(out,'progress-'+challenger_digest('f3-progress',progress)+'.json',progress)
    report=summarize(runs,plan)
    report.update(identity=identity,solves=guard.solves,compute_wall_seconds=monotonic()-guard.started,order_effects=order)
    report['oracles']={f:store.load(out,'oracle-'+f+'.json') for f in ('stock_only','scarce_purchase')}
    store.retain(out,'metrics.json',report);store.retain(out,'reconciliation.json',checks)
    return dict(status=report['status'],identity=identity,runs=len(runs),expected=24,native_solves=guard.solves,
        compute_wall_seconds=report['compute_wall_seconds'],network_process_attempts=attempts,forecast_fits=0,production='LOCKED')


def replay(root,identity,*,attempts):
    store,out,plan,data=load(root,identity)
    verified=0;missing=[];noncomplete=[];realized_count=0
    for origin,fixture,variant in plan.run_order:
        key,request,snap,binding,input_digest,snapshot_digest=case_input(plan,origin,fixture,variant,identity)
        raw=store.load(out,'case-'+key+'.json')
        label=dict(origin=origin,fixture=fixture,variant=variant)
        if raw is None:missing.append(label);continue
        run=F3Run.model_validate(raw)
        if (run.identity,run.planning_input_digest,run.snapshot_digest,run.binding,run.snapshot,run.variant,run.f2_identity)!=(key,input_digest,snapshot_digest,binding,snap,variant,F2):
            raise ValueError('F3_RETAINED_CASE_CHANGED')
        if run.status!='COMPLETED' or run.selection is None:noncomplete.append(label|dict(status=run.status));continue
        validate_fixed(run.selection,request)
        realized=realized_evaluation(data,binding.checkpoint,run.selection)
        if realized!=run.realized:raise ValueError('F3_REALIZED_FIXED_BASKET_CHANGED')
        if realized.simulation is not None:mass_balance(realized.simulation);realized_count+=1
        verified+=1
    if not verified:raise ValueError('F3_NO_COMPLETED_CASES')
    return dict(status='F3_COMPLETED_CASES_FIXED_BASKET_REPLAY_VERIFIED',identity=identity,verified_cases=verified,
        expected_cases=24,realized_ledgers=realized_count,missing=missing,noncomplete=noncomplete,
        semantics='Re-evaluate retained baskets with exact serving/FEFO and selector; no re-optimization.',
        procurement_solves=0,forecast_fits=0,network_process_attempts=attempts,original_writes=0,production='LOCKED')
