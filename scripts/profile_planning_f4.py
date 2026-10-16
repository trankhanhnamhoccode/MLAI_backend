"""One consumed, hard-120s F4 profiling batch; never resumes an F3 execution."""
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runtime/challenger/f4/profile'
F3 = 'e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586'


def child():
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    from app.application.contracts.forecast_challenger import ChallengerEvidence
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure import planning_f3 as h
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    from app.application.planning_impact import plan_forecast
    from app.application.contracts.procurement_selection import WinnerSelection
    import lightgbm
    def forbidden(*a, **k): raise RuntimeError('F4_PROFILE_TRAINING_FORBIDDEN')
    lightgbm.train = forbidden
    timings = {}
    def timed(label, call):
        start = perf_counter()
        value = call()
        timings[label] = perf_counter()-start
        (OUT/'progress.json').write_text(json.dumps(timings, indent=2))
        return value
    profiler = cProfile.Profile()
    profiler.enable()
    storage = ChallengerStorage(ROOT/'runtime/challenger')
    evidence_path = sorted((ROOT/'runtime/challenger/runs').glob('*/evidence.json'))[0]
    evidence = timed('retained_native_input_validation', lambda: ChallengerEvidence.model_validate_json(evidence_path.read_bytes()))
    service = ForecastChallenger(storage, enabled=True)
    for temperature in ('cold', 'warm'):
        admitted = timed(temperature+'_admission_artifact_load', lambda: service._admit(evidence.input))
        value,runtime,bundle,key=admitted
        timed(temperature+'_native_inference', lambda: service._compute(value,bundle,runtime))
    store, directory, plan, data = timed('f3_preparation_admission', lambda: h.load(ROOT,F3))
    origin, fixture, variant = next(x for x in plan.run_order if x[1]=='stock_only')
    _, request, *_ = timed('planning_request_validation', lambda: h.case_input(plan,origin,fixture,variant,F3))
    selection = timed('planning_execution_1', lambda: plan_forecast(request,NativeProductSearch))
    payload = timed('serialization', lambda: selection.model_dump_json().encode())
    timed('storage_write', lambda: (OUT/'selection.json').write_bytes(payload))
    restored = timed('storage_read_validation', lambda: WinnerSelection.model_validate_json((OUT/'selection.json').read_bytes()))
    assert restored == selection
    profiler.disable()
    stats = pstats.Stats(profiler)
    rows = [dict(file=Path(file).name,line=line,function=name,calls=nc,primitive_calls=cc,
                 exclusive_seconds=tt,cumulative_seconds=ct)
            for (file,line,name),(cc,nc,tt,ct,callers) in stats.stats.items()]
    report = dict(status='COMPLETE',planning_executions=1,training_calls=0,timings=timings,
        functions=sorted(rows,key=lambda r:r['cumulative_seconds'],reverse=True)[:100],
        exclusive_total_seconds=sum(r['exclusive_seconds'] for r in rows),
        categories={category:sum(r['exclusive_seconds'] for r in rows if any(token in r['file'] or token in r['function'] for token in tokens))
            for category,tokens in {'bom':['bom'], 'procurement':['procurement'], 'exact_serving_fefo':['serving','fefo'],
                'validation':['validation','model_validate','validate_python','validate_json'],
                'native_solver':['milp','_highs','_core']}.items()},
        native_input_path=evidence_path.relative_to(ROOT).as_posix(),native_input_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        limits='One cold/warm pair and one stock-only Planning execution; categories may overlap. No DB profiling. Not an SLA or explanation of all F3 incomplete cases.')
    (OUT/'summary.json').write_text(json.dumps(report,indent=2))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if '--child' in sys.argv:
        child();return 0
    with (OUT/'consumed.json').open('x') as stream:
        json.dump(dict(wall_seconds=120,maximum_planning_executions=3,automatic_retry=False),stream)
    start=perf_counter()
    try:
        result=subprocess.run([sys.executable,'-B','-m','scripts.profile_planning_f4','--child'],cwd=ROOT,
                              capture_output=True,text=True,timeout=120)
        receipt=dict(exit_code=result.returncode,elapsed_seconds=perf_counter()-start,
                     stderr_tail=result.stderr[-2500:])
    except subprocess.TimeoutExpired:
        receipt=dict(status='PARTIAL_HARD120S',elapsed_seconds=perf_counter()-start)
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))
    return receipt.get('exit_code',2)


if __name__=='__main__':raise SystemExit(main())
