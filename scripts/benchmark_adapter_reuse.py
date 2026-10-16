"""Isolated checkpoint/candidate source, one180s claim, no forecast inference."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/challenger/f4_2'
PREVIOUS='540bb41e97f5d95092362e17fb7e91d3162c0894d2a4791a9c0010b4e12d6850'
SERVING='app/application/use_cases/serving.py'
ORDER=['baseline','candidate','candidate','baseline','baseline','candidate']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2),encoding='utf-8')
def load(path):return json.loads(path.read_bytes())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def tree(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*.py') if '__pycache__' not in p.parts}


def freeze():
    start=perf_counter()
    if (BASE/'setup.json').exists():raise RuntimeError('ALREADY_FROZEN')
    head=git('rev-parse','HEAD');snapshot=BASE/'sources/baseline'
    snapshot.mkdir(parents=True,exist_ok=False)
    raw=subprocess.check_output(['git','archive','--format=tar',head,'app','scripts'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            assert not member.issym() and not member.islnk() and (snapshot/member.name).resolve().is_relative_to(snapshot.resolve())
        archive.extractall(snapshot,filter='data')
    candidate=BASE/'sources/candidate';shutil.copytree(snapshot,candidate)
    shutil.copy2(ROOT/SERVING,candidate/SERVING)
    before=tree(snapshot);after=tree(candidate)
    assert before.keys()==after.keys() and [p for p in before if before[p]!=after[p]]==[SERVING]
    prior=ROOT/'runtime/challenger/f4_1/completion/experiments'/PREVIOUS
    plan=load(prior/'setup.json');staging=ROOT/plan['preflight_directory']
    assert sha(staging/'planning-input.json')==plan['planning_input_sha256']
    (BASE/'planning-input.json').write_bytes((staging/'planning-input.json').read_bytes())
    # No native/model payload is copied or needed. Retained forecast arrays only.
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    request=ProcurementInputV2.model_validate_json((BASE/'planning-input.json').read_bytes())
    assert request.policy.computation_seconds==4 and request.policy.max_solves_per_strategy==2
    assert request.policy.model_dump(mode='json')==plan['planning_policy']
    assert all(o.bound.maximum_packs==4 for o in request.offers) and len(request.offers)==1
    from app.infrastructure.forecast_challenger_runtime import current_runtime
    from app.infrastructure.planning_challenger_identity import integration_digest
    setup=dict(protocol='adapter_reuse_paired/1',baseline_commit=head,baseline_source=before,candidate_source=after,
        candidate_worktree_serving_sha256=sha(ROOT/SERVING),driver_sha256=sha(Path(__file__)),
        job_helper_sha256=sha(ROOT/'scripts/profile_windows_job.py'),interpreter=sys.executable,
        runtime=current_runtime().model_dump(mode='json'),integration_digest=integration_digest(),
        input_sha256=sha(BASE/'planning-input.json'),previous_experiment=PREVIOUS,previous_setup_sha256=sha(prior/'setup.json'),
        fixed_baskets=[[0],[3]],order=ORDER,pairs=[[0,1],[2,3],[4,5]],
        limits=dict(hard_compute_seconds=180,full_planning_executions=6,per_arm=3,native_forecast_inferences=0),
        policy=plan['planning_policy'],instrumentation='No cProfile or observer wraps; perf_counter around full Planning only.',
        cold_warm='Every fixed/Planning task uses a fresh subprocess with arm-specific app path. OS cache uncontrolled; no model inference/cache workload.',
        retry='None automatic; one startup-only retry permitted by user but not implemented.',preflight_seconds=perf_counter()-start)
    identity=hashlib.sha256(json.dumps(setup,sort_keys=True).encode()).hexdigest();setup['identity']=identity
    write(BASE/'setup.json',setup)
    print(json.dumps(dict(identity=identity,preflight_seconds=setup['preflight_seconds'],baseline=head)))


def worker(action,arm,slot):
    # Driver is imported by absolute path; all app imports are forced to the pinned arm.
    source=BASE/'sources'/arm
    sys.path.insert(0,str(source))
    setup=load(BASE/'setup.json')
    assert tree(source)==setup[arm+'_source']
    claim=load(BASE/'compute-claim.json')
    from app.application.contracts.planning_run import ProcessIdentity
    from app.infrastructure.planning_process import liveness,current_process
    assert liveness(ProcessIdentity.model_validate(claim['parent_process']))=='ALIVE'
    with (BASE/(slot+'-claim.json')).open('x') as stream:json.dump(dict(owner=current_process().model_dump(mode='json'),arm=arm,action=action),stream)
    import app.application.use_cases.serving as serving
    assert Path(serving.__file__).resolve()==(source/SERVING).resolve()
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    from app.application.use_cases.procurement_v2 import evaluate_basket_v2
    from app.application.planning_impact import plan_forecast
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    # Fail before any attempt to call a provider, train or native forecast inference.
    import socket
    def forbidden(*args,**kwargs):raise RuntimeError('FORBIDDEN_NETWORK_TRAIN_FORECAST')
    socket.socket.connect=forbidden;socket.socket.connect_ex=forbidden;socket.create_connection=forbidden
    import lightgbm
    lightgbm.train=forbidden
    import app.application.use_cases.forecast_challenger as challenger
    challenger.infer_native=forbidden
    request=ProcurementInputV2.model_validate_json((BASE/'planning-input.json').read_bytes())
    assert request.policy.model_dump(mode='json')==setup['policy']
    write(BASE/(slot+'-progress.json'),dict(business_started=True,planning_started=action=='planning',arm=arm,action=action))
    if action=='fixed':
        results=[]
        for counts in setup['fixed_baskets']:
            start=perf_counter();value=evaluate_basket_v2(request,tuple(counts));elapsed=perf_counter()-start
            payload=value.model_dump_json() if value is not None else 'null'
            (BASE/(slot+'-basket-'+str(counts[0])+'.json')).write_text(payload,encoding='utf-8')
            results.append(dict(counts=counts,elapsed_seconds=elapsed,output_sha256=hashlib.sha256(payload.encode()).hexdigest()))
        write(BASE/(slot+'-result.json'),dict(arm=arm,action=action,baskets=results,source=str(source)))
    else:
        start=perf_counter();selection=plan_forecast(request,NativeProductSearch);elapsed=perf_counter()-start
        result=selection.comparison.source
        option=next((o for o in selection.comparison.options if o.token==selection.winner_token),None)
        write(BASE/(slot+'-result.json'),dict(arm=arm,action=action,wall_seconds=elapsed,
            execution=result.execution,winner=selection.winner_token,reason=selection.reason,proof=selection.proof,
            native_solve_count=sum(len(s.solver) for s in result.strategies),
            enumerated_vectors=sum(s.enumerated_vectors for s in result.strategies),
            exact_evaluations=result.unique_exact_evaluations,procurement_elapsed_seconds=result.elapsed_seconds,
            deadline_overrun_seconds=result.deadline_overrun_seconds,
            strategies=[dict(strategy=s.strategy,execution=s.execution,termination=s.termination,proof=s.proof,
                search_complete=s.search_complete,enumerated_vectors=s.enumerated_vectors,customer_pass=s.customer_pass,
                construction_pass=s.construction_pass,customer_gaps=[g.model_dump(mode='json') for g in s.customer_gaps],
                construction_gaps=[g.model_dump(mode='json') for g in s.construction_gaps]) for s in result.strategies],
            selected_option=option.model_dump(mode='json') if option else None,
            policy=result.input.policy.model_dump(mode='json'),source=str(source)))
        (BASE/(slot+'-selection.json')).write_text(selection.model_dump_json(),encoding='utf-8')


def run():
    if (BASE/'compute-claim.json').exists():raise RuntimeError('F4_2_BUDGET_CONSUMED')
    setup=load(BASE/'setup.json')
    assert sha(Path(__file__))==setup['driver_sha256'] and sha(ROOT/SERVING)==setup['candidate_worktree_serving_sha256']
    assert sha(BASE/'planning-input.json')==setup['input_sha256']
    for arm in ('baseline','candidate'):assert tree(BASE/'sources'/arm)==setup[arm+'_source']
    from scripts.profile_windows_job import OwnedJob
    from app.infrastructure.planning_process import current_process
    # Same job/launcher helper verified by the noncompute F4.1 probe and focused test.
    assert sha(ROOT/'scripts/profile_windows_job.py')==setup['job_helper_sha256']
    start=perf_counter();owner=current_process()
    with (BASE/'compute-claim.json').open('x') as stream:
        json.dump(dict(identity=setup['identity'],parent_process=owner.model_dump(mode='json'),start=start,limits=setup['limits']),stream)
        stream.flush();os.fsync(stream.fileno())
    ledger=dict(identity=setup['identity'],status='PARTIAL',attempts=[],planning_executions=0,native_forecast_inferences=0)
    tasks=[('fixed','baseline','fixed-baseline'),('fixed','candidate','fixed-candidate')]
    tasks += [('planning',arm,'planning-'+str(i)) for i,arm in enumerate(setup['order'])]
    try:
        for action,arm,slot in tasks:
            remaining=180-(perf_counter()-start)
            if remaining<=0:ledger['status']='PARTIAL_HARD180S';break
            if action=='planning' and ledger['planning_executions']>=6:raise RuntimeError('PLANNING_CAP')
            job=OwnedJob();process=None;task_start=perf_counter()
            attempt=dict(action=action,arm=arm,slot=slot,remaining_at_launch=remaining)
            ledger['attempts'].append(attempt);write(BASE/'resource-receipt.json',ledger)
            try:
                cmd=[sys.executable,'-B',str(Path(__file__).resolve()),action,'--arm',arm,'--slot',slot]
                process=job.launch(cmd,BASE/'sources'/arm)
                try:stdout,stderr=process.communicate(timeout=max(0,180-(perf_counter()-start)))
                except subprocess.TimeoutExpired:
                    job.terminate();stdout,stderr=process.communicate(timeout=5);ledger['status']='PARTIAL_HARD180S'
                attempt.update(exit_code=process.returncode,elapsed_seconds=perf_counter()-task_start,
                    stderr=stderr.decode(errors='replace')[-2000:])
            finally:
                if job.active():job.terminate()
                attempt['job_active_after']=job.active();job.close()
                progress=load(BASE/(slot+'-progress.json')) if (BASE/(slot+'-progress.json')).exists() else None
                attempt['business_progress']=progress
                if progress and progress['planning_started']:ledger['planning_executions']+=1
                attempt['compute_elapsed_total']=perf_counter()-start
                write(BASE/'resource-receipt.json',ledger)
            if process.returncode!=0:break
            if slot=='fixed-candidate':
                baseline=load(BASE/'fixed-baseline-result.json')['baskets']
                candidate=load(BASE/'fixed-candidate-result.json')['baskets']
                if [(r['counts'],r['output_sha256']) for r in baseline]!=[(r['counts'],r['output_sha256']) for r in candidate]:
                    ledger['status']='BLOCKED_FIXED_OUTPUT_MISMATCH';break
        else:ledger['status']='COMPLETE'
    finally:
        ledger['total_compute_wall_seconds']=perf_counter()-start
        ledger['retry_count']=0
        write(BASE/'resource-receipt.json',ledger);print(json.dumps(ledger))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','run','fixed','planning'])
    parser.add_argument('--arm',choices=['baseline','candidate']);parser.add_argument('--slot');args=parser.parse_args()
    if args.action=='freeze':freeze()
    elif args.action=='run':run()
    else:worker(args.action,args.arm,args.slot)


if __name__=='__main__':main()
