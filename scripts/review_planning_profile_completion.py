"""Read/hash/copy completion evidence; no replay, admission, Planning or inference."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
import zipfile
from scripts.review_challenger_f4_1 import DEPENDENCIES

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/challenger/f4_1/completion'
ZIP=ROOT/'runtime/shelfcash_F4_1_completion_review.zip'
CHANGED=(
    'docs/CURRENT_STATE.md','docs/ROADMAP.md','docs/features/FORECAST_ENGINE_INTEGRATION.md',
    'docs/runbooks/FULL_TEST_FLOW.md','scripts/planning_profile_observer.py',
    'scripts/profile_planning_f4_1.py','scripts/review_challenger_f4_1.py',
    'tests/unit/test_planning_profile_observer.py','scripts/profile_windows_job.py',
    'scripts/profile_planning_f4_1_completion.py','tests/unit/test_planning_profile_completion.py',
    'scripts/review_planning_profile_completion.py')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_bytes())
def write(path,value):path.write_text(json.dumps(value,indent=2),encoding='utf-8')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    identity=load(BASE/'prepared.json')['identity'];out=BASE/'experiments'/identity
    plan=load(out/'setup.json');receipt=load(out/'receipt.json');timings=load(out/'timings.json')
    assert receipt['status']=='COMPLETE' and receipt['attempts']==1
    assert receipt['compute_wall_seconds']<120 and receipt['job_active_after']==0
    assert receipt['planning_executions']==receipt['native_inferences']==1
    assert timings['attempts']==dict(network=0,training=0)
    assert timings['cache']==dict(hit=2,miss=1)
    assert not timings['events']
    assert load(BASE/'compute-claim.json')['identity']==identity
    assert len(list(out.glob('attempt-*.json')))==1
    preserved=load(BASE/'preserved-before.json')
    for name,digest in preserved.items():assert sha(ROOT/name)==digest,name
    for name,digest in plan['source'].items():assert sha(ROOT/name)==digest,name
    for path in (out/'executed-source').rglob('*.py'):
        name=path.relative_to(out/'executed-source').as_posix()
        assert sha(path)==plan['source'][name]
    old=ROOT/'runtime/challenger/f4_1/experiments'/plan['previous_failed_experiment']
    assert sha(old/'receipt.json')==plan['previous_receipt_sha256']
    assert sha(old/'setup.json')==plan['previous_setup_sha256']
    assert load(old/'receipt.json')['status']=='PARTIAL_ERROR'
    staging=ROOT/plan['preflight_directory']
    for name,key in [('planning-input.json','planning_input_sha256'),('native-input.json','native_input_sha256')]:
        assert sha(staging/name)==plan[key]
    artifact=load(out/'preflight.json')['artifact']
    for row in plan['artifact']['files']:
        assert sha(ROOT/plan['native_storage']/'artifacts'/artifact/row['name'])==row['digest']
    f3root=ROOT/'runtime/challenger/f3'
    originals=load(f3root/'preflight/preserved-before.json')
    for name,digest in originals.items():assert sha(ROOT/name)==digest,name
    f3='e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586'
    inputs=load(f3root/'experiments'/f3/'setup.json')['value']['inputs']
    for name,digest in inputs.items():assert sha(ROOT/name)==digest,name
    replay=load(f3root/'verifications/88b89d8dd839b44927156335658e54bc1203ae28e2b243029f9173c889108199/replay.json')['value']
    for name,digest in replay['input_cases'].items():assert sha(f3root/'experiments'/f3/name)==digest,name
    testcases=list(ET.parse(BASE/'tests.xml').iter('testcase'))
    assert len(testcases)==7 and all(not any(c.find(t) is not None for t in ('failure','error','skipped')) for c in testcases)
    assert git('rev-parse','HEAD')=='8f4d90838cfe7898cf3fbbe0e0784ca136dad8cf'
    assert git('rev-parse','main')=='b0db90cedd3962d8cb2e3f2dfe4696ec83b4e52a'
    assert not git('diff','HEAD','--','app','vendor','alembic')
    assert not git('diff','--cached','--name-only')
    changed=set(git('diff','--name-only').splitlines())|set(git('ls-files','--others','--exclude-standard').splitlines())
    assert changed==set(CHANGED),(changed,set(CHANGED))
    process_command="Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'profile_planning_f4_1' } | Select-Object ProcessId,ParentProcessId | ConvertTo-Json"
    running=subprocess.check_output(['powershell','-NoProfile','-Command',process_command],text=True).strip()
    assert not running,running
    write(BASE/'preservation.json',dict(checked_preexisting_f4_1_files=len(preserved),pre_f3_files=len(originals),
        f3_inputs=len(inputs),f3_cases=len(replay['input_cases']),workbooks={p:h for p,h in inputs.items() if p.endswith('.xlsx')},
        all_hashes_unchanged=True,profiling_processes_found=0,app_vendor_migrations_unchanged=True,
        main_unchanged=True,staged_paths=[],tests=7,old_transfer_zips='Already absent before continuation; original source/evidence preserved.'))
    write(BASE/'commands.json',dict(compute_historical_only=[
        '.venv/Scripts/python.exe -B -m scripts.profile_planning_f4_1_completion prepare',
        '.venv/Scripts/python.exe -B -m scripts.profile_planning_f4_1_completion run --identity '+identity],
        warning='Authorization group is consumed. No rerun/reset. One attempt, no retry.',
        verification=[
        '.venv/Scripts/python.exe -B -m pytest tests/unit/test_planning_profile_completion.py tests/unit/test_planning_profile_observer.py::test_limits_reject_before_extra_execution tests/unit/test_planning_profile_observer.py::test_actual_install_restores_host_aliases_without_execution -q --tb=short --junitxml=runtime/challenger/f4_1/completion/tests.xml',
        'git diff --check','.venv/Scripts/python.exe -B -m scripts.review_planning_profile_completion']))
    write(BASE/'resource-ledger.json',dict(authorization_group=plan['authorization_group'],
        claim_sha256=sha(BASE/'compute-claim.json'),experiment=identity,state='CONSUMED_COMPLETE',
        shared_limits=dict(compute_wall_seconds=120,planning_executions=3,native_forecast_inferences=2),
        attempts=[dict(attempt=1,status=receipt['status'],elapsed_seconds=receipt['compute_wall_seconds'],
            planning_executions=receipt['planning_executions'],native_forecast_inferences=receipt['native_inferences'],
            receipt_sha256=sha(out/'receipt.json'),owned_job_active_after=0)],
        total_compute_seconds=receipt['compute_wall_seconds'],retry_count=0,
        unused_wall_seconds=120-receipt['compute_wall_seconds'],
        unused_budget_policy='Not reallocated; authorization group consumed and runner rejects repeat execution.',
        noncompute_preflight=load(out/'preflight.json'),noncompute_preclaim=load(out/'preclaim-verification.json')))
    payload={}
    def add(path):
        name=path.relative_to(ROOT).as_posix()
        if name in payload:assert payload[name]==path.read_bytes()
        else:payload[name]=path.read_bytes()
    for name in (*CHANGED,*DEPENDENCIES,
        'app/application/use_cases/procurement.py','app/application/contracts/serving.py',
        'app/application/contracts/procurement_comparison.py','app/application/contracts/bom.py',
        'app/application/procurement_comparison_facts.py','app/application/use_cases/procurement_comparison.py',
        'app/domain/decision/quantities.py','app/domain/decision/procurement.py',
        'app/domain/decision/procurement_policy.py','app/application/procurement_solver_v2.py',
        'app/application/procurement_solver.py'):add(ROOT/name)
    for path in sorted(out.glob('*.json')):add(path)
    for path in sorted((out/'executed-source').rglob('*.py')):add(path)
    for name in ('setup.json','preflight.json','preclaim-verification.json','receipt.json'):add(old/name)
    for path in sorted((old/'executed-source').rglob('*.py')):add(path)
    for name in ('compute-claim.json','prepared.json','preserved-before.json','preservation.json','summary.json','commands.json','resource-ledger.json','tests.xml'):add(BASE/name)
    for path in sorted((ROOT/plan['startup_probe']).glob('*.json')):add(path)
    add(ROOT/'runtime/challenger/f4_1/compute-claim.json')
    add(ROOT/'runtime/challenger/f4_1/startup-probe.json')
    add(ROOT/'runtime/challenger/f4/profile/receipt.json')
    add(ROOT/'runtime/challenger/f4/acceptance/native-package.json')
    payload['README.md']=b'''# F4.1 completion review (temporary copy)

Read runtime/challenger/f4_1/completion/summary.json, then the canonical F4.1
analysis in docs/features/FORECAST_ENGINE_INTEGRATION.md and commands/runbook.
Experiment540bb41e...6850 ran one attempt,21.53s,1 Planning/1 inference/0 solves.
Profiling COMPLETE is limited to the frozen offline subset. Planning INCOMPLETE,
null winner, and exact_winner_facts_match_original=false are retained, not hidden.
Do not add nested timings or infer trained-C/DB latency or general F3 causes.
Review the controller, Windows job helper, observer, tests and original timings.
The old mismatch/startup-failure receipts and old/new frozen source are distinct.
commands.json compute commands are historical: all three authorization claims remain consumed.
MANIFEST.json lists payload SHA-256/size (excluding itself); external verification
records archive SHA-256. Selected dependencies aid review, not standalone execution.
No model payloads, workbook, private config, DB dump or large logs are bundled.
All original source/evidence and this README/manifest remain outside the ZIP;
deleting it removes only a transfer copy. No activation, promotion or business optimization.
'''
    secrets=[]
    private=ROOT/'runtime/challenger/f4/private'
    if (private/'database.json').exists():
        password=urlsplit(load(private/'database.json')['url']).password
        if password:secrets.append(password.encode())
    if (private/'compose.env').exists():
        for line in (private/'compose.env').read_text().splitlines():
            if '=' in line and any(k in line.split('=',1)[0].upper() for k in ('PASSWORD','SECRET','TOKEN')):
                value=line.split('=',1)[1].strip().strip('"\'')
                if value:secrets.append(value.encode())
    patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'(?<![A-Za-z0-9])(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}',rb'postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:[^\s@]+@']
    for name,data in payload.items():
        assert not any(p in ('.env','private') for p in Path(name).parts)
        assert Path(name).suffix.lower() not in ('.xlsx','.bin','.pkl','.db','.dump','.log','.whl','.joblib','.sqlite')
        assert not any(v in data for v in secrets),f'Known secret in {name}'
        assert not any(re.search(p,data) for p in patterns),f'Secret signature in {name}'
    manifest=dict(schema=1,changed_paths=list(CHANGED),entries=[dict(path=p,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for p,b in sorted(payload.items())],self_excluded=True)
    payload['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
    (BASE/'review-README.md').write_bytes(payload['README.md'])
    (BASE/'review-MANIFEST.json').write_bytes(payload['MANIFEST.json'])
    assert subprocess.run(['git','check-ignore','-q',str(ZIP.relative_to(ROOT))],cwd=ROOT).returncode==0
    if ZIP.exists():
        previous=BASE/('previous-review-'+sha(ZIP)+'.zip')
        if not previous.exists():previous.write_bytes(ZIP.read_bytes())
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):archive.writestr(name,data)
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None and set(archive.namelist())==set(payload)
        for row in json.loads(archive.read('MANIFEST.json'))['entries']:
            data=archive.read(row['path'])
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        for name,data in payload.items():assert archive.read(name)==data
    for name,data in payload.items():
        if name not in ('README.md','MANIFEST.json'):assert (ROOT/name).read_bytes()==data,name
    for name,digest in preserved.items():assert sha(ROOT/name)==digest,name
    result=dict(path=str(ZIP),bytes=ZIP.stat().st_size,files=len(payload),sha256=sha(ZIP),
        crc='PASS',manifest_hashes='PASS',source_correspondence='PASS',secrets='PASS',ignored=True,staged=False,
        originals_preserved=True,compute_attempts=1,profiling='COMPLETE_FOR_FROZEN_OFFLINE_SUBSET',planning='INCOMPLETE')
    write(BASE/'review-verification.json',result);print(json.dumps(result))


if __name__=='__main__':main()
