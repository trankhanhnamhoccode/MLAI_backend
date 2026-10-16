"""Freeze/run/replay the explicit /3 demo protocol; one forecast batch, no Planning."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic

ROOT=Path(__file__).resolve().parents[1]
INPUTS='57249b1b53513eb9d5ea34304d4e3197271d08ccfa77341634e01efcba0b8f3a'


def execute(mode:str):
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    from app.application.contracts.demo_calendar import DemoCalendarAssumption
    from app.application.contracts.forecast_benchmark import BenchmarkDataset,BenchmarkPlan,DEMO_ABC_PROTOCOL_DIGEST
    from app.application.forecast_challenger_serialization import challenger_digest,canonical_bytes
    from app.application.use_cases.forecast_benchmark import ForecastBenchmark
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    storage=BenchmarkStorage(ROOT/'runtime/challenger/demo-abc')
    inputs=storage.path('inputs',INPUTS)
    declaration=DemoCalendarAssumption.model_validate(storage.load(inputs,'calendar-assumption.json'))
    data=BenchmarkDataset.model_validate(storage.load(inputs,'dataset.json'))
    sources=storage.load(inputs,'sources.json')
    for row in sources:
        for file in (row['path'],*row['aliases']):
            if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=row['sha256']: raise ValueError('DATASET_HASH_CHANGED')
    if not all(c.source=='benchmark_assumed_calendar:'+challenger_digest('demo-calendar-assumption',declaration) for c in data.calendar):
        raise ValueError('CALENDAR_DECLARATION_NOT_BOUND')
    supports=[storage.load(inputs,p.name) for p in inputs.glob('support-*.json')]
    if not supports or not all(s['status']=='SUPPORT_VERIFIED_NO_FITS' and s['booster_fits']==0 for s in supports):
        raise ValueError('EXACT_NATIVE_SUPPORT_REQUIRED')
    support=supports[-1]
    if support['source_revision']!=data.source_revision or support['declaration_digest']!=challenger_digest('demo-calendar-assumption',declaration):
        raise ValueError('SUPPORT_SCOPE_MISMATCH')
    protocol=json.loads((ROOT/'tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json').read_bytes())
    plan=BenchmarkPlan(harness_version='causal_benchmark/3',protocol_digest=DEMO_ABC_PROTOCOL_DIGEST,
        dataset_digest=challenger_digest('dataset',data),tasks=protocol['tasks'])
    if [t.model_dump(mode='json') for t in plan.tasks]!=[r['proposed_windows'] for r in support['rows']]:
        raise ValueError('SUPPORT_WINDOWS_CHANGED')
    service=ForecastBenchmark(ROOT)
    identity,directory,_=service.freeze(data,plan)
    code_files=('scripts/run_demo_abc.py','scripts/prepare_demo_abc.py','scripts/run_demo_benchmark.py',
        'app/application/contracts/demo_calendar.py','app/application/demo_calendar.py',
        'tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json')
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in code_files}
    receipt=dict(experiment_identity=identity,source=hashes,calendar_assumption=declaration,
        native_support=support,dataset_digest=plan.dataset_digest,protocol_digest=plan.protocol_digest,
        planned_booster_fits=24,planned_postprocess_fits=8,forecast_tasks_per_arm=140,hard_wall_seconds=300,
        forecast_repeats=1,production='LOCKED',planning_solves=0)
    service.storage.retain(directory,'demo-freeze.json',receipt)
    if mode=='freeze':return dict(status='FROZEN_BEFORE_FITS',experiment_identity=identity,output=str(directory))
    if mode=='run':
        if service.storage.load(directory,'bounded-batch-start.json') is not None: raise ValueError('BATCH_ALREADY_ATTEMPTED')
        service.storage.retain(directory,'bounded-batch-start.json',dict(hard_wall_seconds=300,inputs=INPUTS))
        report=service.run(data,plan)
    else:
        import lightgbm as lgb
        def forbidden(*a,**k):raise RuntimeError('REPLAY_CANNOT_RETRAIN')
        lgb.train=forbidden
        report=service.replay(identity)
    # Own runner receipts use content addresses; source changes never overwrite older evidence.
    offline=dict(mode=mode,source=hashes,network_process_attempts=attempts,provider_calls=0,database_connections=0,
        planning_solves=0,retrain_permitted=mode=='run')
    key=challenger_digest('demo-abc-offline',offline)
    service.storage.retain(directory,'offline-'+key+'.json',offline)
    print(canonical_bytes(dict(status=report['status'],experiment_identity=identity,output=str(directory),
        coverage=report.get('output_coverage'),exclusions=report.get('exclusions'),replayed_arms=report.get('replayed_arms'),offline=offline)).decode(),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','run','replay'))
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.child:
        result=execute(args.mode)
        if args.mode=='freeze':print(json.dumps(result))
        return 2 if result['status']=='INCOMPLETE' else 0
    started=monotonic()
    command=[sys.executable,'-m','scripts.run_demo_abc',args.mode,'--child']
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=300 if args.mode=='run' else 120)
        print(result.stdout,end='')
        if result.returncode:print(result.stderr,file=sys.stderr,end='')
        return result.returncode
    except subprocess.TimeoutExpired:
        print(json.dumps(dict(status='PARTIAL',reason='HARD_WALL_DEADLINE',mode=args.mode,elapsed_seconds=monotonic()-started)))
        return 2


if __name__=='__main__':raise SystemExit(main())
