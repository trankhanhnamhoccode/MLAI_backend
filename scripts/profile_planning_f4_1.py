"""Preflight first; one separately claimed hard120s offline F4.1 experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/challenger/f4_1'
F3='e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586'
F3_REPLAY='88b89d8dd839b44927156335658e54bc1203ae28e2b243029f9173c889108199'
TOOLS=('scripts/profile_planning_f4_1.py','scripts/planning_profile_observer.py')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def sources():
    paths=sorted((ROOT/'app').rglob('*.py'))+[ROOT/p for p in TOOLS]
    paths.append(ROOT/'tests/fixtures/forecast_engine/planning_f4_setup.py')
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}


def claim(path,identity,start):
    from app.infrastructure.planning_process import current_process
    owner=current_process()
    with path.open('x',encoding='utf-8') as stream:
        json.dump(dict(identity=identity,parent_pid=os.getpid(),parent_process=owner.model_dump(mode='json'),compute_start=start,
            hard_wall_seconds=120,maximum_planning_executions=3,maximum_native_inferences=2,
            training=False,network=False,automatic_retry=False),stream)
        stream.flush();os.fsync(stream.fileno())


def verify_owner(value,identity):
    """A Windows venv launcher may be the immediate parent; verify the claim owner."""
    from app.application.contracts.planning_run import ProcessIdentity
    from app.infrastructure.planning_process import liveness
    if value.get('identity')!=identity or 'parent_process' not in value:
        raise RuntimeError('PROFILE_CLAIM_OWNER_INVALID')
    owner=ProcessIdentity.model_validate(value['parent_process'])
    if owner.pid!=value.get('parent_pid') or liveness(owner)!='ALIVE':
        raise RuntimeError('PROFILE_CLAIM_OWNER_NOT_ALIVE')


def prepare():
    started=perf_counter()
    from datetime import datetime,timezone
    from uuid import UUID,uuid4
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    from app.application.forecast_challenger_serialization import challenger_digest,canonical_bytes
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from tests.fixtures.forecast_engine.planning_f4_setup import rebind_fixture,SOURCE
    if (BASE/'compute-claim.json').exists():raise RuntimeError('F4_1_BATCH_ALREADY_CONSUMED')
    staging=BASE/'preflight'/str(uuid4());staging.mkdir(parents=True)
    storage=ChallengerStorage(staging/'native')
    value=rebind_fixture(storage,UUID(int=41001),UUID(int=41011),'cup',datetime.now(timezone.utc))
    admission_started=perf_counter()
    admitted,runtime,bundle,key=ForecastChallenger(storage,enabled=True)._admit(value)
    admission_seconds=perf_counter()-admission_started
    assert admitted==value and bundle.manifest.purpose=='synthetic_correctness'
    assert not (storage.root/'runs').exists()
    parent=ChallengerStorage(ROOT/'runtime/challenger').load_artifact(SOURCE)
    weights={f.name:f.digest for f in parent.manifest.files if f.name.startswith('model_q')}
    assert weights=={f.name:f.digest for f in bundle.manifest.files if f.name.startswith('model_q')}
    old_path=sorted((ROOT/'runtime/challenger/runs').glob('*/evidence.json'))[0]
    old=json.loads(old_path.read_bytes())
    old_artifact=ChallengerStorage(ROOT/'runtime/challenger').load_artifact(old['input']['artifact_identity'])
    old_reason=dict(selection='sorted(runs/*/evidence.json)[0], lexical cache hash, not eligibility',
        path=old_path.relative_to(ROOT).as_posix(),artifact=old['input']['artifact_identity'],
        old_adapter_digest=old_artifact.manifest.runtime.adapter_code_digest,
        current_adapter_digest=runtime.adapter_code_digest)
    store=BenchmarkStorage(ROOT/'runtime/challenger/f3')
    verified=store.load(ROOT/f'runtime/challenger/f3/verifications/{F3_REPLAY}','replay.json')['input_cases']
    selected=None
    for name in sorted(verified):
        path=ROOT/f'runtime/challenger/f3/experiments/{F3}'/name
        assert sha(path)==verified[name]
        case=store.load(path.parent,path.name)
        if case['snapshot']['fixture_id']=='scarce_purchase' and case['variant']=='B_COMMON' and case['snapshot']['origin']=='2026-06-24':
            selected=case;selected_path=path;break
    if selected is None:raise RuntimeError('RETAINED_F3_CASE_MISSING')
    raw=selected['selection']['comparison']['source']['input']
    request=ProcurementInputV2.model_validate(raw)
    assert challenger_digest('impact-planning-input',request)==selected['planning_input_digest']
    assert request.policy.computation_seconds==4 and request.policy.max_solves_per_strategy==2
    # Retained forecast-only ProcurementInput contains no actual labels.
    assert all('actual' not in p for p in raw['prepared']['forecast']['predictions'])
    write(staging/'planning-input.json',raw)
    (staging/'native-input.json').write_bytes(canonical_bytes(value))
    before=perf_counter()
    pins=sources()
    plan=dict(protocol='planning_profile_f4_1/1',source_head=git('rev-parse','HEAD'),main=git('rev-parse','main'),
        source=pins,runtime=runtime.model_dump(mode='json'),artifact=bundle.manifest.model_dump(mode='json'),
        parent_synthetic_artifact=SOURCE,booster_payload_hashes=weights,
        native_input_sha256=sha(staging/'native-input.json'),planning_input_sha256=sha(staging/'planning-input.json'),
        native_storage=storage.root.relative_to(ROOT).as_posix(),preflight_directory=staging.relative_to(ROOT).as_posix(),
        f3_case=selected_path.relative_to(ROOT).as_posix(),f3_case_sha256=sha(selected_path),
        planning_input_digest=selected['planning_input_digest'],planning_policy=request.policy.model_dump(mode='json'),
        original_selected_option=next((o for o in selected['selection']['comparison']['options'] if o['token']==selected['selection']['winner_token']),None),
        cases=['A: F3 June24 B_COMMON scarce_purchase, same input/policy; one offline Planning execution',
            'B: fresh-process first synthetic native execution; retained cache miss',
            'C: identical synthetic input/artifact/runtime; retained cache hit, no forced inference'],
        limits=dict(hard_compute_wall_seconds=120,maximum_planning_executions=3,maximum_native_inferences=2),
        exclusions='DB forecast persistence, capture/finalize and DB fresh read are N/A; native constant fixture differs from five-Product F3 Planning workload.',
        cold_definition='First inference in fresh child; OS file cache is uncontrolled and preflight ran in the parent.',
        old_mismatch=old_reason)
    identity=challenger_digest('f4.1-profile-plan',plan)
    out=BASE/'experiments'/identity;out.mkdir(parents=True,exist_ok=False)
    write(out/'setup.json',plan)
    preflight=dict(status='ADMISSION_AND_ARTIFACT_LOADING_VERIFIED_BEFORE_CLAIM',identity=identity,
        total_seconds=perf_counter()-started,admission_artifact_loading_seconds=admission_seconds,
        source_freeze_seconds=perf_counter()-before,planning_executions=0,native_inferences=0,
        source_head=plan['source_head'],artifact_identity=value.artifact_identity,runtime=plan['runtime'])
    write(out/'preflight.json',preflight)
    print(json.dumps(dict(identity=identity,preflight_seconds=preflight['total_seconds'],artifact=value.artifact_identity)))


def loaded(identity):
    from app.application.forecast_challenger_serialization import challenger_digest
    out=BASE/'experiments'/identity
    plan=json.loads((out/'setup.json').read_bytes())
    if challenger_digest('f4.1-profile-plan',plan)!=identity or sources()!=plan['source']:
        raise RuntimeError('FROZEN_SOURCE_OR_PLAN_CHANGED')
    staging=ROOT/plan['preflight_directory']
    for name,key in [('native-input.json','native_input_sha256'),('planning-input.json','planning_input_sha256')]:
        if sha(staging/name)!=plan[key]:raise RuntimeError('FROZEN_INPUT_CHANGED')
    return out,plan,staging


def child(identity):
    entry=perf_counter()
    global_claim=json.loads((BASE/'compute-claim.json').read_bytes())
    verify_owner(global_claim,identity)
    out,plan,staging=loaded(identity)
    with (out/'child-claim.json').open('x') as stream:json.dump(dict(pid=os.getpid(),entry=entry),stream)
    import platform
    platform.uname()
    from app.application.contracts.procurement_v2 import ProcurementInputV2
    from app.application.contracts.procurement_selection import WinnerSelection
    from app.application.contracts.forecast_challenger import ChallengerInput
    from app.application.forecast_challenger_serialization import canonical_bytes
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    from app.infrastructure.procurement_milp_v2 import NativeProductSearch
    from app.application.planning_impact import plan_forecast
    from scripts.planning_profile_observer import Observer,install
    import cProfile,pstats,lightgbm,socket
    imports_finished=perf_counter()
    attempts={'network':0,'training':0}
    def no_network(*args,**kwargs):attempts['network']+=1;raise RuntimeError('NETWORK_FORBIDDEN')
    def no_train(*args,**kwargs):attempts['training']+=1;raise RuntimeError('TRAINING_FORBIDDEN')
    socket.socket.connect=no_network;socket.socket.connect_ex=no_network;socket.create_connection=no_network
    lightgbm.train=no_train
    observer=Observer()
    def persist():write(out/'progress.json',observer.snapshot()|dict(attempts=attempts,elapsed_since_launch=perf_counter()-global_claim['compute_start']))
    install(observer,persist)
    profiler=cProfile.Profile(timer=perf_counter)
    profiler.enable()
    results={};status='PARTIAL';error=None
    try:
        observer.phase='A_F3_scarce_purchase'
        with observer.span('input_preparation_admission'):
            request=ProcurementInputV2.model_validate_json((staging/'planning-input.json').read_bytes())
        observer.resource('planning');persist()
        with observer.span('Planning_execution'):
            selection=plan_forecast(request,NativeProductSearch)
        option=next((o.model_dump(mode='json') for o in selection.comparison.options if o.token==selection.winner_token),None)
        # Exact winner facts exclude time/proof/search-status metadata, which can
        # change under observation with the unchanged cooperative deadline.
        fields=('basket','arrivals','outlay','products','ingredients','daily_products','daily_ingredients')
        original=plan['original_selected_option']
        results['A']=dict(winner=selection.winner_token,execution=selection.comparison.source.execution,
            strategy_statuses=[s.execution for s in selection.comparison.source.strategies],
            unique_exact_evaluations=selection.comparison.source.unique_exact_evaluations,
            exact_winner_facts_match_original=option is not None and original is not None and all(option[f]==original[f] for f in fields))
        with observer.span('result_serialization'):payload=selection.model_dump_json().encode()
        with observer.span('result_filesystem_persistence'):(out/'selection.json').write_bytes(payload)
        before=(observer.native_inferences,len(observer.events))
        with observer.span('retained_fresh_read_with_semantic_validation'):
            restored=WinnerSelection.model_validate_json((out/'selection.json').read_bytes())
            assert restored==selection
        assert before==(observer.native_inferences,len(observer.events))
        persist()
        service=ForecastChallenger(ChallengerStorage(ROOT/plan['native_storage']),enabled=True)
        with observer.span('native_input_preparation'):
            value=ChallengerInput.model_validate_json((staging/'native-input.json').read_bytes())
        native=[]
        for phase in ('B_native_cold','C_native_warm_cache'):
            observer.phase=phase
            with observer.span('admission_artifact_cache_execution'):
                result=service.execute(value)
            native.append(result)
            results[phase]=dict(reused=result.reused,cache_identity=result.evidence.cache_identity)
            persist()
        assert native[0].reused is False and native[1].reused is True and native[0].evidence==native[1].evidence
        with observer.span('forecast_result_serialization'):
            (out/'native-output.json').write_bytes(canonical_bytes(native[0].evidence.output))
        status='COMPLETE'
    except Exception as failure:
        error=dict(type=type(failure).__name__,code=getattr(failure,'code',None))
        raise
    finally:
        profiler.disable();observer.restore();persist()
        stats=pstats.Stats(profiler)
        rows=[]
        for (file,line,name),(primitive,calls,self_seconds,cumulative,callers) in stats.stats.items():
            path=Path(file)
            label=path.relative_to(ROOT).as_posix() if path.is_absolute() and path.is_relative_to(ROOT) else path.name
            rows.append(dict(file=label,line=line,function=name,calls=calls,primitive_calls=primitive,
                exclusive_seconds=self_seconds,inclusive_seconds=cumulative))
        write(out/'timings.json',observer.snapshot()|dict(status=status,error=error,results=results,attempts=attempts,
            startup=dict(launch_to_entry_seconds=entry-global_claim['compute_start'],entry_to_imports_seconds=imports_finished-entry),
            child_elapsed_seconds=perf_counter()-entry,functions=sorted(rows,key=lambda r:r['inclusive_seconds'],reverse=True)[:150],
            notable_calls=[r for r in rows if r['function'] in {'reconstruct','reconstruct_demand','validate_result','model_validate','model_validate_json','_evaluate','simulate','expand_bom'} or 'validate_python' in r['function']],
            caveats=plan['exclusions']+' Observer/cProfile overhead and scheduling count against the unchanged host4s policy; no uninstrumented latency inference.'))


def run(identity):
    if (BASE/'compute-claim.json').exists():
        raise RuntimeError('F4_1_BATCH_ALREADY_CONSUMED')
    verified_started=perf_counter()
    out,plan,staging=loaded(identity)
    from app.application.contracts.forecast_challenger import ChallengerInput
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    value=ChallengerInput.model_validate_json((staging/'native-input.json').read_bytes())
    _,runtime,bundle,_=ForecastChallenger(ChallengerStorage(ROOT/plan['native_storage']),enabled=True)._admit(value)
    assert runtime.model_dump(mode='json')==plan['runtime'] and bundle.manifest.model_dump(mode='json')==plan['artifact']
    write(out/'preclaim-verification.json',dict(status='PASS',seconds=perf_counter()-verified_started,native_inferences=0,planning_executions=0))
    start=perf_counter()
    claim(BASE/'compute-claim.json',identity,start)
    command=[sys.executable,'-B','-m','scripts.profile_planning_f4_1','child','--identity',identity]
    process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        stdout,stderr=process.communicate(timeout=max(0,120-(perf_counter()-start)))
        result=dict(status='COMPLETE' if process.returncode==0 else 'PARTIAL_ERROR',exit_code=process.returncode)
    except subprocess.TimeoutExpired:
        process.kill();stdout,stderr=process.communicate()
        result=dict(status='PARTIAL_HARD120S',exit_code=process.returncode)
    result.update(compute_wall_seconds=perf_counter()-start,identity=identity,automatic_retry=False,
        stderr_sha256=hashlib.sha256(stderr).hexdigest(),stderr_tail=stderr.decode('utf-8',errors='replace')[-1400:])
    write(out/'receipt.json',result)
    print(json.dumps(result))
    return process.returncode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','child']);parser.add_argument('--identity')
    args=parser.parse_args()
    if args.action=='prepare':prepare();return 0
    if not args.identity or len(args.identity)!=64 or any(c not in '0123456789abcdef' for c in args.identity):raise ValueError('Identity required')
    if args.action=='run':return run(args.identity)
    child(args.identity);return 0


if __name__=='__main__':raise SystemExit(main())
