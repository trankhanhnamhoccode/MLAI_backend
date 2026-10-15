"""Opt-in F2 freeze, single300s batch, or no-fit fresh-process replay."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic

ROOT=Path(__file__).resolve().parents[1]


def child(mode,identity):
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    import lightgbm as lgb
    def forbidden(*a,**k):raise RuntimeError('F2_BOOSTER_TRAINING_FORBIDDEN')
    lgb.train=forbidden
    from app.infrastructure import forecast_f2_harness as harness
    if mode=='freeze':return harness.freeze(ROOT)
    if mode=='replay':
        import app.application.forecast_f2 as computation
        computation.fit_endpoints=forbidden
        computation.fit_origin=forbidden
        harness.fit_origin=forbidden
        return harness.replay(ROOT,identity,attempts=attempts)
    return harness.execute(ROOT,identity,attempts=attempts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable',action='store_true')
    parser.add_argument('mode',choices=('freeze','run','replay'))
    parser.add_argument('--identity')
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not args.enable:raise SystemExit('F2_OPT_IN_REQUIRED')
    if args.mode!='freeze' and not args.identity:parser.error('--identity required')
    if args.child:
        from app.application.forecast_challenger_serialization import canonical_bytes
        print(canonical_bytes(child(args.mode,args.identity)).decode('utf-8'),flush=True)
        return 0
    started=monotonic()
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
    storage=BenchmarkStorage(ROOT/'runtime/challenger/f2')
    if args.mode=='run':
        # Exclusive, global F2 marker: changed source/identity cannot open another fit batch.
        from app.infrastructure.forecast_f2_harness import admitted
        admitted(ROOT,args.identity)
        marker=dict(identity=args.identity,started_at=datetime.now(timezone.utc),hard_wall_seconds=300,
            maximum_booster_fits=0,maximum_point_cqr_fits=0,maximum_endpoint_fit_artifacts=4,batches=1)
        raw=canonical_bytes(marker)
        envelope=canonical_bytes(dict(sha256=hashlib.sha256(raw).hexdigest(),value=json.loads(raw)))
        storage.root.mkdir(parents=True,exist_ok=True)
        with (storage.root/'bounded-batch-start.json').open('xb') as file:
            file.write(envelope);file.flush()
            import os
            os.fsync(file.fileno())
    command=[sys.executable,'-B','-m','scripts.forecast_f2','--enable',args.mode,'--child']
    if args.identity:command+=['--identity',args.identity]
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',
            timeout=max(0.001,(300 if args.mode=='run' else 120)-(monotonic()-started)))
        if result.returncode:
            report=dict(status='PARTIAL' if args.mode=='run' else 'BLOCKED',mode=args.mode,identity=args.identity,
                reason='CHILD_FAILED',elapsed_seconds=monotonic()-started)
            print(json.dumps(report));print(result.stderr[-3000:],file=sys.stderr)
        else:
            report=json.loads(result.stdout);report['parent_elapsed_seconds']=monotonic()-started
            print(canonical_bytes(report).decode('utf-8'))
    except subprocess.TimeoutExpired:
        report=dict(status='PARTIAL',reason='HARD_WALL_DEADLINE',identity=args.identity,mode=args.mode,
            elapsed_seconds=monotonic()-started)
        print(json.dumps(report))
        result=None
    if args.identity:
        out=storage.path('experiments',args.identity)
        name=args.mode+'-receipt-'+challenger_digest('f2-receipt',report)+'.json'
        storage.retain(out,name,report)
    return result.returncode if result is not None else 2


if __name__=='__main__':raise SystemExit(main())
