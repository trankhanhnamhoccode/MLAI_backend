"""Private immutable F2 admission, bounded endpoint batch and read-only replay."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic

from app.application.contracts.forecast_f2 import F2Protocol
from app.application.contracts.forecast_benchmark import BenchmarkDataset, BenchmarkPlan
from app.application.contracts.demo_calendar import DemoCalendarAssumption
from app.application.forecast_benchmark_plan import restore_plan
from app.application.forecast_benchmark_admission import admit_plan
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.forecast_f2 import (
    fit_origin, validate_parameters, forecasts, metrics, validation_decision, retained_value,
    validate_closed_sales,
)
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from app.infrastructure.forecast_challenger_runtime import current_runtime

PARENT='e8fd6eea4f2528bdd9d83a95b6ffcabc84017228c04f2e347ea5a80ce1524e54'
DEMO='57249b1b53513eb9d5ea34304d4e3197271d08ccfa77341634e01efcba0b8f3a'
PROTOCOL='tests/fixtures/forecast_engine/benchmark_manifest_f2_v1.json'
SOURCE_FILES=(
    'app/domain/forecasting/endpoint_calibration.py','app/application/contracts/forecast_f2.py',
    'app/application/forecast_f2.py','app/infrastructure/forecast_f2_harness.py','scripts/forecast_f2.py',
    'app/domain/forecasting/diagnostics.py','app/application/contracts/forecast_benchmark.py',
    'app/application/contracts/demo_calendar.py','app/application/contracts/forecast_challenger.py',
    'app/application/forecast_benchmark_plan.py','app/application/forecast_benchmark_admission.py',
    'app/application/forecast_challenger_serialization.py','app/application/forecast_challenger_validation.py',
    'app/infrastructure/forecast_benchmark_storage.py','app/infrastructure/storage/forecast_challenger.py',
    'app/infrastructure/forecast_challenger_runtime.py','scripts/run_demo_benchmark.py',PROTOCOL,
)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def context(root:Path):
    storage=BenchmarkStorage(root/'runtime/challenger/benchmarks')
    directory=storage.path('experiments',PARENT)
    pins={}
    def pin(path):
        relative=path.relative_to(root).as_posix()
        pins[relative]=sha(path)
    def load(folder,name):
        pin(folder/name)
        value=storage.load(folder,name)
        if value is None:raise ValueError('F2_RETAINED_INPUT_MISSING:'+name)
        return value
    plan=restore_plan(load(directory,'plan.json'),BenchmarkPlan)
    data=BenchmarkDataset.model_validate(load(directory,'dataset.json'))
    admit_plan(data,plan);validate_closed_sales(data)
    predictions=load(directory,'predictions.json')
    load(directory,'environment.json');load(directory,'demo-freeze.json')
    demo=root/'runtime/challenger/demo-abc/inputs'/DEMO
    declaration=DemoCalendarAssumption.model_validate(load(demo,'calendar-assumption.json'))
    if (declaration.source_revision!=data.source_revision or declaration.store_id!=data.store_id or
            declaration.timezone!=data.timezone or set(declaration.product_ids)!={p.product_id for p in data.products}):
        raise ValueError('F2_DECLARATION_SCOPE_CHANGED')
    expected_source='benchmark_assumed_calendar:'+challenger_digest('demo-calendar-assumption',declaration)
    if not all(c.source==expected_source for c in data.calendar):raise ValueError('F2_CALENDAR_DECLARATION_CHANGED')
    sources=load(demo,'sources.json')
    for source in sources:
        path=Path(source['path'])
        if not path.is_relative_to(root) or sha(path)!=source['sha256']:raise ValueError('F2_RAW_WORKBOOK_CHANGED')
        pin(path)
    actuals={(str(o.product_id),str(o.sales_date)):o for o in data.observations}
    for r in predictions:
        actual=actuals.get((r['product_id'],r['target_date']))
        mask='missing' if actual is None else 'primary_known_false' if actual.is_stockout is False else 'censored_lower_bound' if actual.is_stockout else 'supplementary_unknown'
        if r['mask']!=mask or r['actual']!=(None if actual is None else str(actual.quantity)):
            raise ValueError('F2_RETAINED_ACTUAL_MASK_CHANGED')
    artifacts=ChallengerStorage(root/'runtime/challenger')
    tables={};evidence={};bindings={}
    for task in plan.tasks:
        checkpoints={a:load(directory,str(task.origin)+'-'+a+'.json') for a in plan.configuration_ids}
        c=checkpoints[plan.configuration_ids[2]]
        if c['origin']!=str(task.origin) or c['status']!='COMPLETED':raise ValueError('F2_ORIGIN_CHECKPOINT_CHANGED')
        fit=storage.path('fits',c['identity'])
        if load(fit,'checkpoint.json')!=c:raise ValueError('F2_PARENT_FIT_CHANGED')
        tables[str(task.origin)]=load(fit,'calibration-tasks.json')
        b=checkpoints[plan.configuration_ids[1]]
        host=load(storage.path('fits',b['identity']),'host-model.json')
        if challenger_digest('host-artifact',host['files'])!=b['artifact_identity']:
            raise ValueError('F2_HOST_ARTIFACT_CHANGED')
        bundle=artifacts.load_artifact(c['artifact_identity'])
        if bundle.manifest.training.end!=task.train_end or bundle.manifest.point_fit.end>task.point_end or bundle.manifest.calibration.end>task.calibration_end:
            raise ValueError('F2_ARTIFACT_WINDOW_CHANGED')
        for path in bundle.directory.iterdir():
            if path.is_file():pin(path)
        path=root/'runtime/challenger/runs'/c['replay_identity']
        e=artifacts.load_evidence(c['replay_identity'])
        # The evidence envelope uses ChallengerStorage's own integrity contract.
        for item in path.iterdir():
            if item.is_file():pin(item)
        evidence[str(task.origin)]=e.model_dump(mode='json')
        if evidence[str(task.origin)]['input']['artifact_identity']!=c['artifact_identity']:
            raise ValueError('F2_EVIDENCE_ARTIFACT_CHANGED')
        bindings[str(task.origin)]=dict(parent_checkpoint=c['identity'],parent_artifact=c['artifact_identity'],parent_evidence=c['replay_identity'])
    inventory=root/'runtime/challenger/f2/preflight/workbook-inventory.json'
    pin(inventory)
    inv=json.loads(inventory.read_bytes())
    observed={Path(r['path']).resolve():r['sha256'] for r in inv}
    actual_files={p.resolve() for p in (root/'runtime').rglob('*.xlsx')}
    if actual_files!=set(observed) or any(sha(p)!=h for p,h in observed.items()):
        raise ValueError('F2_WORKBOOK_INVENTORY_DRIFT_REVIEW_REQUIRED')
    if {r['sha256'] for r in sources}!={r['sha256'] for r in inv}:
        raise ValueError('F2_SOURCE_SELECTION_REQUIRES_NEW_ADMISSION')
    return data,plan,predictions,tables,evidence,bindings,pins


def protocol(root):
    raw=json.loads((root/PROTOCOL).read_bytes())
    spec=F2Protocol.model_validate(raw)
    if canonical_bytes(spec)!=canonical_bytes(raw):raise ValueError('F2_PROTOCOL_REPRESENTATION')
    return spec


def freeze(root):
    spec=protocol(root)
    data,plan,_,_,_,bindings,pins=context(root)
    if tuple(str(t.origin) for t in plan.tasks)!=spec.origins:raise ValueError('F2_ORIGINS_CHANGED')
    manifest=dict(protocol=spec,inputs=pins,source={name:sha(root/name) for name in SOURCE_FILES},
        runtime=current_runtime(),python=sys.version,bindings=bindings,
        dataset_digest=plan.dataset_digest,source_revision=data.source_revision,
        products=data.products,timezone=data.timezone,windows=plan.tasks,
        evaluation='EXPOSED_DEVELOPMENT_ONLY_NO_FRESH_LABELS',parent_protocol=plan.protocol_digest,
        counters=dict(booster_fits=0,point_cqr_fits=0,endpoint_fit_artifacts=4,horizon_statistics=28),
        notes=('Same boosters, point/CQR and origins; no rebuild needed.',
               'Calibration arrays overlap the parent CQR fit window; no split-conformal guarantee.',
               'Raw POS ends2026-07-08; calendar through2026-07-15 is not fresh labels.',
               'Unit pooling only within the exact five-Product ly scope; no inferred open/closed facts.'))
    identity=challenger_digest('f2-admission',manifest)
    store=BenchmarkStorage(root/'runtime/challenger/f2');out=store.path('experiments',identity)
    store.retain(out,'admission.json',manifest)
    return dict(status='F2_FROZEN_BEFORE_ENDPOINT_FITS',identity=identity,output=str(out),budget=spec.model_dump(mode='json'))


def admitted(root,identity):
    store=BenchmarkStorage(root/'runtime/challenger/f2');out=store.path('experiments',identity)
    manifest=store.load(out,'admission.json')
    if manifest is None or challenger_digest('f2-admission',manifest)!=identity:raise ValueError('F2_ADMISSION_IDENTITY_CHANGED')
    spec=F2Protocol.model_validate(manifest['protocol'])
    if protocol(root)!=spec or set(manifest['source'])!=set(SOURCE_FILES):raise ValueError('F2_PROTOCOL_OR_SOURCE_SET_CHANGED')
    for name,digest in manifest['source'].items():
        if sha(root/name)!=digest:raise ValueError('F2_SOURCE_CHANGED:'+name)
    for name,digest in manifest['inputs'].items():
        if not (root/name).resolve().is_relative_to(root) or sha(root/name)!=digest:raise ValueError('F2_INPUT_CHANGED:'+name)
    if manifest['runtime']!=current_runtime().model_dump(mode='json') or manifest['python']!=sys.version:
        raise ValueError('F2_RUNTIME_CHANGED')
    ctx=context(root)
    if ctx[-1]!=manifest['inputs'] or ctx[-2]!=manifest['bindings']:raise ValueError('F2_INPUT_BINDING_CHANGED')
    return store,out,spec,ctx


def result_values(data,plan,predictions,evidence,parameters):
    variants,audits=forecasts(data,predictions,evidence,parameters)
    all_metrics,counts=metrics(variants,audits)
    primary=[m for m in all_metrics if m['mask']=='primary_known_false' and m['dimension']=='all']
    native_c=[a for a in audits if a['arm']=='C']
    summary=dict(status='F2_EXPLORATORY_COMPLETE',aggregate=primary,
        decision=validation_decision(all_metrics,parameters),mask_counts=counts,
        invariants=dict(p50_C0_C1_exact=True,unit_preserved=True,original_experiment_readonly=True,
            final_crossings=sum(m['final_crossings'] for m in primary if m['cohort']=='ALL'),
            common_policy_closed_tasks=sum(a['state']=='CLOSED' for a in audits),
            endpoint_raw_crossings=sum(a['endpoint_clamps']['raw_crossing'] for a in native_c),
            lower_nonnegative_clamps=sum(a['endpoint_clamps']['lower_nonnegative_clamp'] for a in native_c),
            lower_median_clamps=sum(a['endpoint_clamps']['lower_median_clamp'] for a in native_c),
            upper_median_clamps=sum(a['endpoint_clamps']['upper_median_clamp'] for a in native_c),
            original_raw_crossings_by_arm={arm:sum(r['raw_crossing'] for r in predictions if r['arm'].startswith(arm)) for arm in ('A','B','C')}),
        counts=dict(forecasts_per_variant={k:len(v) for k,v in variants.items()},metric_groups=len(all_metrics),
            endpoint_statuses={o:p['status'] for o,p in parameters.items()}),
        budget=dict(booster_fits=0,point_cqr_fits=0,endpoint_fit_artifacts=4,horizon_statistics=28),
        limitations=('EXPOSED development validation and evaluation, not independent final holdout.',
                    'No fresh POS labels, historical vintages or calibration/production guarantee.',
                    'CQR retained unchanged, not relabeled quantiles; closed intervals factual degenerate zeros.',
                    'Censored scores describe observed lower bounds, not true demand; missing/unknown excluded from primary.',
                    'Forecast metrics do not imply savings, inventory impact or Planning acceptance.'),production='LOCKED')
    return {'summary.json':summary,'metrics.json':all_metrics,'predictions.json':variants,'stages.json':audits}


def execute(root,identity,*,attempts):
    started=monotonic()
    store,out,spec,ctx=admitted(root,identity)
    data,plan,predictions,tables,evidence,bindings,_=ctx
    marker=store.load(store.root,'bounded-batch-start.json')
    if marker is None or marker['identity']!=identity:raise ValueError('F2_BATCH_NOT_ADMITTED')
    claim=dict(identity=identity,maximum_endpoint_fit_artifacts=4,started=True)
    raw=canonical_bytes(claim)
    # Exclusive child claim also blocks direct --child re-entry after partial completion.
    with (out/'execution-claim.json').open('xb') as file:
        file.write(canonical_bytes(dict(sha256=hashlib.sha256(raw).hexdigest(),value=json.loads(raw))))
        file.flush()
        import os
        os.fsync(file.fileno())
    parameters={};completed=[]
    def check():
        if monotonic()-started>=spec.wall_seconds:raise TimeoutError('F2_WALL_BUDGET_EXCEEDED')
    for task in plan.tasks:
        check();origin=str(task.origin)
        parameter,rows=fit_origin(data,plan,task,tables[origin],spec)
        parameter.update(bindings[origin]);parameter['f2_identity']=identity
        parameter=retained_value(parameter);rows=retained_value(rows)
        store.retain(out,origin+'-parameters.json',parameter)
        store.retain(out,origin+'-fit-evidence.json',rows)
        parameters[origin]=parameter;completed.append(origin)
        ledger=dict(completed=completed.copy(),endpoint_fit_artifacts=len(completed),booster_fits=0,
            point_cqr_fits=0,elapsed_seconds=monotonic()-started)
        store.retain(out,'resource-'+challenger_digest('f2-resource',ledger)+'.json',ledger)
    check()
    results=result_values(data,plan,predictions,evidence,parameters)
    for name,value in results.items():store.retain(out,name,retained_value(value))
    receipt=dict(status=results['summary.json']['status'],identity=identity,completed_origins=completed,
        elapsed_seconds=monotonic()-started,endpoint_fit_artifacts=len(parameters),booster_fits=0,point_cqr_fits=0,
        parameter_bytes=sum((out/(o+'-parameters.json')).stat().st_size for o in parameters),
        fit_evidence_bytes=sum((out/(o+'-fit-evidence.json')).stat().st_size for o in parameters),
        reused_model_bytes=sum((root/p).stat().st_size for p in ctx[-1] if p.endswith(('.txt','host-model.json'))),
        network_process_attempts=attempts,provider_calls=0,database_connections=0,planning_solves=0,production='LOCKED')
    store.retain(out,'execution.json',receipt)
    return receipt


def replay(root,identity,*,attempts):
    store,out,spec,ctx=admitted(root,identity)
    data,plan,predictions,tables,evidence,bindings,_=ctx
    parameters={}
    for task in plan.tasks:
        origin=str(task.origin)
        p=store.load(out,origin+'-parameters.json');rows=store.load(out,origin+'-fit-evidence.json')
        if p is None or rows is None:raise ValueError('F2_PARTIAL_MISSING_ORIGIN')
        if p['f2_identity']!=identity or any(p[k]!=v for k,v in bindings[origin].items()):raise ValueError('F2_PARAMETER_ARTIFACT_BINDING')
        validate_parameters(p,rows,data,plan,task,tables[origin],spec)
        parameters[origin]=p
    expected=result_values(data,plan,predictions,evidence,parameters)
    hashes={}
    for name,value in expected.items():
        retained=store.load(out,name)
        if canonical_bytes(retained_value(value))!=canonical_bytes(retained):raise ValueError('F2_REPLAY_OUTPUT_CHANGED:'+name)
        hashes[name]=sha(out/name)
    return dict(status='F2_READONLY_REPLAY_VERIFIED',identity=identity,origins=len(parameters),
        parameter_artifacts=len(parameters),booster_fits=0,point_cqr_fits=0,endpoint_fits=0,
        outputs=hashes,network_process_attempts=attempts,original_writes=0,production='LOCKED')
