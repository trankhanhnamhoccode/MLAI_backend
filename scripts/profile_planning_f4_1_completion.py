"""New explicit F4.1 authorization; old claims untouched, no automatic retry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter,sleep
from scripts import profile_planning_f4_1 as original
from scripts.profile_windows_job import OwnedJob

ROOT=original.ROOT
GROUP=original.BASE/'completion'
PREVIOUS='b6ab729e05bc00c5d960ab1adcb4c91725fc3b31c01e9db226fb367a99230cd1'
EXTRA=('scripts/profile_planning_f4_1_completion.py','scripts/profile_windows_job.py')
original_sources=original.sources


def sources():return original_sources()|{p:original.sha(ROOT/p) for p in EXTRA}


def configure():
    original.BASE=GROUP;original.sources=sources


def command(identity,mode='child',claim=None):
    result=[sys.executable,'-B','-m','scripts.profile_planning_f4_1_completion',mode,'--identity',identity]
    if claim:result+=['--claim',str(claim)]
    return result


def probe_child(identity,claim,leaf=False):
    value=json.loads(claim.read_bytes());original.verify_owner(value,identity)
    from app.infrastructure.planning_process import current_process
    name='leaf' if leaf else 'probe'
    original.write(claim.parent/(name+'.json'),dict(process=current_process().model_dump(mode='json'),
        immediate_parent=os.getppid(),planning_executions=0,native_inferences=0))
    if not leaf:subprocess.Popen(command(identity,'probe-leaf',claim),cwd=ROOT)
    sleep(30)  # Noncompute tree intentionally terminated by its owning job.


def probe():
    started=perf_counter()
    from uuid import uuid4
    from app.infrastructure.planning_process import liveness
    directory=GROUP/'probes'/str(uuid4());directory.mkdir(parents=True)
    claim=directory/'owner.json';identity='f'*64
    original.claim(claim,identity,started)
    job=OwnedJob();process=None
    try:
        process=job.launch(command(identity,'probe',claim),ROOT)
        deadline=perf_counter()+15
        while not (directory/'leaf.json').exists() and process.poll() is None and perf_counter()<deadline:sleep(.02)
        assert (directory/'leaf.json').exists(),'Probe startup/descendant did not complete'
        members=job.active();assert members>=2
        job.terminate();stdout,stderr=process.communicate(timeout=5)
        for name in ('probe','leaf'):
            assert liveness(json.loads((directory/(name+'.json')).read_bytes())['process'])=='DEAD'
        result=dict(status='PASS',seconds=perf_counter()-started,job_active_before=members,
            job_active_after=job.active(),root_exited=process.poll() is not None,
            command=command(identity,'probe',claim),interpreter=sys.executable,
            suspended_assignment=True,kill_on_close=True,tree_timeout_termination_verified=True,
            planning_executions=0,native_inferences=0)
        original.write(directory/'result.json',result);print(json.dumps(dict(probe=str(directory),**result)))
        return directory
    finally:
        if job.active():job.terminate()
        job.close()
        if process is not None:process.communicate(timeout=5)


def prepare():
    started=perf_counter()
    if (GROUP/'compute-claim.json').exists():raise RuntimeError('COMPLETION_AUTHORIZATION_CONSUMED')
    if (GROUP/'prepared.json').exists():raise RuntimeError('COMPLETION_ALREADY_PREPARED')
    previous=ROOT/'runtime/challenger/f4_1/experiments'/PREVIOUS
    plan=json.loads((previous/'setup.json').read_bytes())
    from app.application.contracts.forecast_challenger import ChallengerInput
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    from app.application.forecast_challenger_serialization import challenger_digest
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    staging=ROOT/plan['preflight_directory']
    for filename,key in [('native-input.json','native_input_sha256'),('planning-input.json','planning_input_sha256')]:
        assert original.sha(staging/filename)==plan[key]
    request=ProcurementInputV2.model_validate_json((staging/'planning-input.json').read_bytes())
    assert request.policy.model_dump(mode='json')==plan['planning_policy']
    assert request.policy.computation_seconds==4 and request.policy.max_solves_per_strategy==2
    value=ChallengerInput.model_validate_json((staging/'native-input.json').read_bytes())
    storage=ChallengerStorage(ROOT/plan['native_storage'])
    assert not list((storage.root/'runs').glob('*/evidence.json')),'Cold cache must be empty'
    _,runtime,bundle,_=ForecastChallenger(storage,enabled=True)._admit(value)
    assert runtime.model_dump(mode='json')==plan['runtime'] and bundle.manifest.model_dump(mode='json')==plan['artifact']
    preflight_elapsed=perf_counter()-started
    probe_directory=probe()
    plan.update(source=sources(),authorization_group='F4_1_completion_explicit_20261016',
        previous_failed_experiment=PREVIOUS,previous_setup_sha256=original.sha(previous/'setup.json'),
        previous_receipt_sha256=original.sha(previous/'receipt.json'),startup_probe=probe_directory.relative_to(ROOT).as_posix(),
        retry_policy='No automatic retry. At most one manual startup-only retry allowed by user, with shared remaining ledger; current runner conservatively stops after one attempt.',
        process_tree='Suspended launcher assigned to kill-on-close Windows job before resume; owned tree terminated on deadline.',
        instrumentation_overhead='Observer and cProfile enabled; all overhead consumes unchanged solver4s; no uninstrumented control run.')
    identity=challenger_digest('f4.1-profile-plan',plan)
    out=GROUP/'experiments'/identity;out.mkdir(parents=True,exist_ok=False)
    original.write(out/'setup.json',plan)
    for path in (*original.TOOLS,*EXTRA):
        target=out/'executed-source'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
    original.write(out/'preflight.json',dict(status='PASS',preflight_seconds=preflight_elapsed,
        total_setup_and_probe_seconds=perf_counter()-started,probe=plan['startup_probe'],planning_executions=0,native_inferences=0,
        artifact=value.artifact_identity,runtime=plan['runtime']))
    original.write(GROUP/'prepared.json',dict(identity=identity))
    print(json.dumps(dict(identity=identity,preflight_seconds=preflight_elapsed,setup_seconds=perf_counter()-started)))


def run(identity):
    if (GROUP/'compute-claim.json').exists():raise RuntimeError('COMPLETION_AUTHORIZATION_CONSUMED')
    configure()
    started=perf_counter();out,plan,staging=original.loaded(identity)
    assert json.loads((GROUP/'prepared.json').read_bytes())['identity']==identity
    assert json.loads((ROOT/plan['startup_probe']/'result.json').read_bytes())['status']=='PASS'
    from app.application.contracts.forecast_challenger import ChallengerInput
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    value=ChallengerInput.model_validate_json((staging/'native-input.json').read_bytes())
    _,runtime,bundle,_=ForecastChallenger(ChallengerStorage(ROOT/plan['native_storage']),enabled=True)._admit(value)
    assert runtime.model_dump(mode='json')==plan['runtime'] and bundle.manifest.model_dump(mode='json')==plan['artifact']
    original.write(out/'preclaim-verification.json',dict(status='PASS',seconds=perf_counter()-started,planning_executions=0,native_inferences=0))
    job=OwnedJob();process=None;start=perf_counter()
    original.claim(GROUP/'compute-claim.json',identity,start)
    original.write(out/'attempt-1.json',dict(state='CLAIMED',start=start,hard_remaining_seconds=120,command=command(identity)))
    result=dict(identity=identity,attempts=1,automatic_retry=False)
    try:
        process=job.launch(command(identity),ROOT)
        try:
            stdout,stderr=process.communicate(timeout=max(0,120-(perf_counter()-start)))
            result.update(status='COMPLETE' if process.returncode==0 else 'PARTIAL_ERROR',exit_code=process.returncode)
        except subprocess.TimeoutExpired:
            job.terminate();stdout,stderr=process.communicate(timeout=5)
            result.update(status='PARTIAL_HARD120S',exit_code=process.returncode)
        result.update(compute_wall_seconds=perf_counter()-start,
            stderr_tail=stderr.decode('utf-8',errors='replace')[-2200:],stderr_sha256=__import__('hashlib').sha256(stderr).hexdigest())
    finally:
        if job.active():job.terminate()
        result['job_active_after']=job.active();job.close()
        if process is not None:process.communicate(timeout=5)
        result.setdefault('status','PARTIAL_STARTUP_ERROR')
        result.setdefault('compute_wall_seconds',perf_counter()-start)
        progress=json.loads((out/'progress.json').read_bytes()) if (out/'progress.json').exists() else None
        result['planning_executions']=progress['planning_executions'] if progress else None
        result['native_inferences']=progress['native_inferences'] if progress else None
        result['ledger']='One shared120s claim; no second attempt allocated. Unknown counters forbid retry.'
        original.write(out/'receipt.json',result)
        print(json.dumps(result))
    return result['status']!='COMPLETE'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','child','probe','probe-leaf'])
    parser.add_argument('--identity');parser.add_argument('--claim',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':prepare();return 0
    if not args.identity or len(args.identity)!=64 or any(c not in '0123456789abcdef' for c in args.identity):raise ValueError('Identity required')
    if args.action in ('probe','probe-leaf'):
        probe_child(args.identity,args.claim,args.action=='probe-leaf');return 0
    if args.action=='run':return run(args.identity)
    configure();original.child(args.identity);return 0


if __name__=='__main__':raise SystemExit(main())
