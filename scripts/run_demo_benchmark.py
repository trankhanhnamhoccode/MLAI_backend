"""One hard-bounded offline A/B demo batch, or fresh-process replay without fitting.

Inputs are hash-checked admission envelopes. No application, provider or DB startup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic

ROOT=Path(__file__).resolve().parents[1]


def install_offline_guard():
    """Deny network and process launches before importing benchmark dependencies."""
    attempts=[]
    def guard(event,args):
        if event=='import' and any(args[0]==p or args[0].startswith(p+'.') for p in
                ('psycopg','sqlalchemy','httpx','requests','smtplib','app.main','app.db','app.infrastructure.database')):
            attempts.append('import:'+args[0])
            raise RuntimeError('OFFLINE_BENCHMARK_FORBIDDEN_IMPORT:'+args[0])
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):
            attempts.append(event)
            raise RuntimeError('OFFLINE_BENCHMARK_FORBIDDEN_IO:'+event)
    sys.addaudithook(guard)
    return attempts


def execute(admission:Path,mode:str):
    # Python 3.11 platform.uname() invokes `ver` on Windows. Populate its standard
    # library cache before forbidding child launches; no benchmark imports yet.
    import platform
    platform.uname()
    attempts=install_offline_guard()
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.application.contracts.forecast_benchmark import BenchmarkDataset,BenchmarkPlan,ARMS
    from app.application.use_cases.forecast_benchmark import ForecastBenchmark
    from app.application.forecast_challenger_serialization import challenger_digest
    storage=BenchmarkStorage(admission.parent)
    manifest=storage.load(admission.parent,admission.name)
    if manifest['forecast_AB']!='READY_DEMO_EXPLORATORY_INPUT': raise ValueError('AB_NOT_ADMITTED')
    config=manifest['declarations']
    if config['source_revision']!=manifest['source_revision']: raise ValueError('UNBOUND_DECLARATIONS')
    for source in storage.load(admission.parent,'sources.json'):
        for file in (source['path'],*source['aliases']):
            if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=source['sha256']: raise ValueError('DATASET_CHANGED')
    for file,digest in manifest['source_code_sha256'].items():
        if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=digest: raise ValueError('ADMISSION_SOURCE_CHANGED')
    data=BenchmarkDataset.model_validate(storage.load(admission.parent,'dataset.json'))
    plan=BenchmarkPlan.model_validate(storage.load(admission.parent,'plan.json'))
    if plan.harness_version!='causal_benchmark/2' or plan.configuration_ids!=ARMS[:2]: raise ValueError('AB_V2_REQUIRED')
    service=ForecastBenchmark(ROOT)
    identity,directory,_=service.freeze(data,plan)
    if mode=='run':
        # A consumed/partial batch must not restart after the hard deadline.
        marker=service.storage.load(directory,'bounded-batch-start.json')
        if marker is not None: raise ValueError('BATCH_ALREADY_ATTEMPTED_USE_REPLAY')
        service.storage.retain(directory,'bounded-batch-start.json',dict(hard_wall_seconds=300,admission=str(admission)))
        report=service.run(data,plan)
    else:
        report=service.replay(identity)
    receipt=dict(mode=mode,experiment_identity=identity,network_process_attempts=attempts,
        guard='Python audit denies DB/provider imports, socket connect/DNS and subprocess/os.system before benchmark imports',
        provider_calls=0,database_connections=0,planning_solves=0,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    service.storage.retain(directory,'offline-'+mode+'.json',receipt)
    service.storage.retain(directory,'demo-'+mode+'-result.json',report)
    return dict(status=report['status'],experiment_identity=identity,output=str(directory),
        completed_coverage=report.get('output_coverage'),replayed_arms=report.get('replayed_arms'),offline=receipt)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission',type=Path,required=True)
    parser.add_argument('--mode',choices=('run','replay'),default='run')
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.child:
        from app.application.forecast_challenger_serialization import canonical_bytes
        print(canonical_bytes(execute(args.admission.resolve(),args.mode)).decode())
        return 0
    started=monotonic()
    command=[sys.executable,'-m','scripts.run_demo_benchmark','--child','--admission',str(args.admission.resolve()),'--mode',args.mode]
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=300 if args.mode=='run' else 120)
        print(result.stdout,end='')
        if result.returncode: print(result.stderr,file=sys.stderr,end='')
        return result.returncode
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for its child. The child guard forbids grandchildren.
        print(json.dumps(dict(status='PARTIAL',reason='HARD_WALL_DEADLINE',mode=args.mode,elapsed_seconds=monotonic()-started)))
        return 2


if __name__=='__main__': raise SystemExit(main())
