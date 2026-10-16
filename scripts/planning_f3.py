"""Freeze/run one F3 batch300s; replay completed fixed baskets in a fresh120s process."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import subprocess,sys
from time import monotonic
ROOT=Path(__file__).resolve().parents[1]


def child(mode,identity):
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    import lightgbm
    def forbidden(*args,**kwargs):raise RuntimeError('F3_FORBIDDEN_FIT_OR_PROCUREMENT_REPLAY')
    lightgbm.train=forbidden
    import app.application.forecast_f2 as endpoint
    endpoint.fit_origin=forbidden;endpoint.fit_endpoints=forbidden
    from app.infrastructure import planning_f3 as harness
    if mode=='freeze':return harness.freeze(ROOT)
    if mode=='replay':
        import app.application.planning_impact as impact
        import app.infrastructure.procurement_milp_v2 as native
        import scipy.optimize
        impact.execute_procurement_v2=forbidden;native.NativeProductSearch=forbidden;scipy.optimize.milp=forbidden
        return harness.replay(ROOT,identity,attempts=attempts)
    return harness.execute(ROOT,identity,attempts=attempts)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--enable',action='store_true')
    parser.add_argument('mode',choices=('freeze','run','replay'));parser.add_argument('--identity')
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not args.enable:raise SystemExit('F3_OPT_IN_REQUIRED')
    if args.mode!='freeze' and not args.identity:parser.error('--identity required')
    if args.child:
        from app.application.forecast_challenger_serialization import canonical_bytes
        print(canonical_bytes(child(args.mode,args.identity)).decode(),flush=True);return 0
    started=monotonic()
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
    store=BenchmarkStorage(ROOT/'runtime/challenger/f3')
    if args.mode=='run':
        from app.infrastructure.planning_f3 import load
        load(ROOT,args.identity)
        marker=canonical_bytes(dict(identity=args.identity,started_at=datetime.now(timezone.utc),wall_seconds=300,
            maximum_runs=24,maximum_native_solves=144,forecast_fits=0,batches=1))
        store.root.mkdir(parents=True,exist_ok=True)
        with (store.root/'bounded-batch-start.json').open('xb') as file:
            file.write(canonical_bytes(dict(sha256=hashlib.sha256(marker).hexdigest(),value=json.loads(marker))))
            file.flush();os.fsync(file.fileno())
    command=[sys.executable,'-B','-m','scripts.planning_f3','--enable',args.mode,'--child']
    if args.identity:command+=['--identity',args.identity]
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',
            timeout=max(.001,(300 if args.mode=='run' else 120)-(monotonic()-started)))
        if result.returncode:
            report=dict(status='PARTIAL' if args.mode=='run' else 'BLOCKED',identity=args.identity,reason='CHILD_FAILED',mode=args.mode)
            print(result.stderr[-3000:],file=sys.stderr)
        else:report=json.loads(result.stdout)
        code=result.returncode
    except subprocess.TimeoutExpired:
        report=dict(status='PARTIAL',identity=args.identity,mode=args.mode,reason='HARD_WALL_DEADLINE')
        code=2
    report['parent_elapsed_seconds']=monotonic()-started
    if args.identity:
        out=store.path('experiments',args.identity)
        store.retain(out,args.mode+'-'+challenger_digest('f3-receipt',report)+'.json',report)
    print(canonical_bytes(report).decode());return code


if __name__=='__main__':raise SystemExit(main())
