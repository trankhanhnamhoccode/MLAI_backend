"""120s read-only semantic verification of every retained F3 case, including PARTIAL.

Uses E4's dedicated verifier pattern: strict result validators already re-evaluate
retained candidate/journal baskets. Avoid reconstructing the entire graph repeatedly.
This verifier has its own source receipt, separate from frozen execution source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic
ROOT=Path(__file__).resolve().parents[1]


def verify(identity):
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    def forbidden(*a,**k):raise RuntimeError('F3_REPLAY_CANNOT_GENERATE_OR_FIT')
    import lightgbm,scipy.optimize
    lightgbm.train=forbidden;scipy.optimize.milp=forbidden
    import app.application.forecast_f2 as endpoint
    endpoint.fit_origin=forbidden;endpoint.fit_endpoints=forbidden
    import app.application.planning_impact as impact
    impact.execute_procurement_v2=forbidden
    import app.infrastructure.procurement_milp_v2 as native
    native.NativeProductSearch=forbidden
    from app.infrastructure import planning_f3 as harness
    from app.application.contracts.planning_f3 import F3Run
    from app.application.planning_f3 import summarize,mass_balance,cost_balance
    from app.application.use_cases.procurement_selection import projected,selection_facts
    from app.application.forecast_challenger_serialization import challenger_digest
    store,out,plan,data=harness.load(ROOT,identity)
    harness.plan_forecast=forbidden
    runs=[];missing=[];noncomplete=[];ledgers=0;inputs={};started=monotonic()
    for origin,fixture,variant in plan.run_order:
        key,request,snap,binding,input_digest,snapshot_digest=harness.case_input(plan,origin,fixture,variant,identity)
        name='case-'+key+'.json';raw=store.load(out,name)
        label=dict(origin=origin,fixture=fixture,variant=variant)
        if raw is None:missing.append(label);continue
        inputs[name]=hashlib.sha256((out/name).read_bytes()).hexdigest()
        # Full schema validation invokes exact retained basket/journal, comparison,
        # serving and selector checks. No model_construct/copy or weakened schema.
        run=F3Run.model_validate(raw)
        if (run.identity,run.planning_input_digest,run.snapshot_digest,run.binding,run.snapshot,run.variant,run.f2_identity)!=(key,input_digest,snapshot_digest,binding,snap,variant,harness.F2):
            raise ValueError('F3_RETAINED_IDENTITY_CHANGED')
        if run.selection is not None and run.selection.comparison.source.input!=request:
            raise ValueError('F3_RETAINED_REQUEST_CHANGED')
        runs.append(run)
        if run.status!='COMPLETED' or run.selection is None:noncomplete.append(label|dict(status=run.status));continue
        s=run.selection;c=s.comparison
        if (c.options,c.bindings,c.deltas,c.diagnostics)!=projected(c.source):raise ValueError('F3_COMPARISON_CHANGED')
        if (s.winner_token,s.eligible_tokens,s.rejected,s.reason)!=selection_facts(c):raise ValueError('F3_WINNER_CHANGED')
        for strategy in c.source.strategies:
            if strategy.candidate is not None:
                cost_balance(request,strategy.candidate);mass_balance(strategy.candidate.evaluation)
        realized=impact.realized_evaluation(data,binding.checkpoint,s)
        if realized!=run.realized:raise ValueError('F3_REALIZED_CHANGED')
        if realized.simulation is not None:mass_balance(realized.simulation);ledgers+=1
    report=dict(status='F3_COMPLETED_CASES_SEMANTIC_REPLAY_VERIFIED',identity=identity,
        verified_cases=len(runs)-len(noncomplete),expected_cases=24,realized_ledgers=ledgers,missing=missing,noncomplete=noncomplete,
        computation='Strict schema exact checks re-evaluate retained candidate/journal baskets and selector; separate fixed-winning-basket actual serving. No candidate generation or re-optimization.',
        source='Frozen F3 execution source hashes validated unchanged; this verifier has a separate source hash.',
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),input_cases=inputs,
        procurement_solves=0,forecast_fits=0,network_process_attempts=attempts,original_writes=0,
        elapsed_seconds=monotonic()-started,production='LOCKED')
    summary=summarize(runs,plan)
    summary.update(identity=identity,missing=missing,noncomplete=noncomplete,
        projection='Read-only projection of retained cases after strict semantic verification; not a resumed batch.',
        oracles={f:store.load(out,'oracle-'+f+'.json') for f in ('stock_only','scarce_purchase')})
    key=challenger_digest('f3-readonly-verification',report)
    destination=store.path('verifications',key)
    store.retain(destination,'replay.json',report);store.retain(destination,'metrics.json',summary)
    return dict(status=report['status'],identity=identity,verified_cases=report['verified_cases'],expected_cases=24,
        realized_ledgers=ledgers,missing=len(missing),noncomplete=len(noncomplete),procurement_solves=0,forecast_fits=0,
        elapsed_seconds=report['elapsed_seconds'],output=str(destination))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--identity',required=True)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    if args.child:
        from app.application.forecast_challenger_serialization import canonical_bytes
        print(canonical_bytes(verify(args.identity)).decode());return 0
    started=monotonic()
    try:
        result=subprocess.run([sys.executable,'-B','-m','scripts.verify_planning_f3','--identity',args.identity,'--child'],
            cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
        print(result.stdout,end='')
        if result.returncode:print(result.stderr[-3000:],file=sys.stderr)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(json.dumps(dict(status='REPLAY_PARTIAL',identity=args.identity,reason='HARD120S_REPLAY_DEADLINE',elapsed_seconds=monotonic()-started)))
        return 2


if __name__=='__main__':raise SystemExit(main())
