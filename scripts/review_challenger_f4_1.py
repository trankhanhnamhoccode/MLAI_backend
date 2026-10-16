"""Copy-only review of consumed F4.1 evidence. Never imports the compute runner."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/challenger/f4_1'
IDENTITY='b6ab729e05bc00c5d960ab1adcb4c91725fc3b31c01e9db226fb367a99230cd1'
EXP=BASE/'experiments'/IDENTITY
ZIP=ROOT/'runtime/shelfcash_F4_1_review.zip'
CHANGED=(
    'scripts/planning_profile_observer.py','scripts/profile_planning_f4_1.py',
    'scripts/review_challenger_f4_1.py','tests/unit/test_planning_profile_observer.py',
    'docs/CURRENT_STATE.md','docs/ROADMAP.md','docs/features/FORECAST_ENGINE_INTEGRATION.md',
    'docs/runbooks/FULL_TEST_FLOW.md')
DEPENDENCIES=(
    'AGENTS.md','pyproject.toml','scripts/profile_planning_f4.py',
    'scripts/requirements-forecast-challenger-f4-test.lock.txt',
    'tests/fixtures/forecast_engine/planning_f4_setup.py',
    'app/infrastructure/planning_process.py','app/application/contracts/planning_run.py',
    'app/application/planning_impact.py','app/application/contracts/procurement_v2.py',
    'app/application/contracts/procurement_selection.py','app/application/contracts/common.py',
    'app/application/contracts/forecast_challenger.py',
    'app/application/forecast_challenger_serialization.py',
    'app/application/forecast_challenger_validation.py',
    'app/application/use_cases/forecast_challenger.py',
    'app/infrastructure/storage/forecast_challenger.py',
    'app/infrastructure/forecast_challenger_native.py',
    'app/infrastructure/forecast_challenger_runtime.py',
    'app/application/use_cases/bom.py','app/application/use_cases/serving.py',
    'app/application/use_cases/procurement_v2.py','app/application/use_cases/procurement_selection.py',
    'app/application/procurement_v2_validation.py','app/application/serving_validation.py',
    'app/domain/decision/serving.py',
    'app/infrastructure/procurement_milp.py','app/infrastructure/procurement_milp_v2.py',
    'vendor/forecast_challenger/shelfcash_forecast/snapshot_provenance.json')


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_bytes())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def write(path,value):path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def main():
    inspection=read(BASE/'resume-inspection.json')
    for name,digest in inspection['preserved_hashes'].items():
        assert sha((ROOT/name).read_bytes())==digest,name
    plan=read(EXP/'setup.json');receipt=read(EXP/'receipt.json')
    assert receipt['status']=='PARTIAL_ERROR' and receipt['exit_code']==1
    assert not any((EXP/name).exists() for name in ('child-claim.json','progress.json','timings.json','selection.json','native-output.json'))
    assert read(BASE/'compute-claim.json')['identity']==IDENTITY
    # Frozen executed source must stay recoverable; app source has not changed.
    for name,digest in plan['source'].items():
        source=EXP/'executed-source'/name if name.startswith('scripts/') else ROOT/name
        assert sha(source.read_bytes())==digest,name
    staging=ROOT/plan['preflight_directory']
    for name,key in [('native-input.json','native_input_sha256'),('planning-input.json','planning_input_sha256')]:
        assert sha((staging/name).read_bytes())==plan[key]
    for item in plan['artifact']['files']:
        artifact=ROOT/plan['native_storage']/'artifacts'/read(EXP/'preflight.json')['artifact_identity']
        assert sha((artifact/item['name']).read_bytes())==item['digest']
    # Verify preserved historical inputs without execution/replay/admission.
    original=read(ROOT/'runtime/challenger/f3/preflight/preserved-before.json')
    for name,digest in original.items():assert sha((ROOT/name).read_bytes())==digest,name
    f3='e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586'
    f3root=ROOT/'runtime/challenger/f3/experiments'/f3
    inputs=read(f3root/'setup.json')['value']['inputs']
    for name,digest in inputs.items():assert sha((ROOT/name).read_bytes())==digest,name
    replay=read(ROOT/'runtime/challenger/f3/verifications/88b89d8dd839b44927156335658e54bc1203ae28e2b243029f9173c889108199/replay.json')['value']
    for name,digest in replay['input_cases'].items():assert sha((f3root/name).read_bytes())==digest,name
    assert git('rev-parse','HEAD')=='8f4d90838cfe7898cf3fbbe0e0784ca136dad8cf'
    assert git('rev-parse','main')=='b0db90cedd3962d8cb2e3f2dfe4696ec83b4e52a'
    assert not git('diff','HEAD','--','app','vendor','alembic')
    assert not git('diff','--cached','--name-only')
    actual=set(git('diff','--name-only').splitlines())|set(git('ls-files','--others','--exclude-standard').splitlines())
    assert actual==set(CHANGED),(actual,set(CHANGED))
    checks={}
    for filename in ('final-tests.xml','final-observer-tests.xml'):
        cases=list(ET.parse(BASE/filename).iter('testcase'))
        assert all(not any(c.find(t) is not None for t in ('failure','error','skipped')) for c in cases)
        checks[filename]=len(cases)
    summary=dict(classification='CURRENT FACT',f4_commit=git('rev-parse','HEAD'),f4_1='WIP, uncommitted',
        experiment=IDENTITY,status=receipt['status'],technical_test_only_acceptance='VERIFIED (historical F4 evidence)',
        profiling='UNRESOLVED',product_activation='NOT IMPLEMENTED',production_promotion='LOCKED',
        artifact=read(EXP/'preflight.json')['artifact_identity'],runtime=plan['runtime'],
        preflight_seconds=read(EXP/'preflight.json')['total_seconds'],
        preclaim_seconds=read(EXP/'preclaim-verification.json')['seconds'],
        compute_wall_seconds=receipt['compute_wall_seconds'],batch_claims=1,
        planning_executions=0,native_inferences=0,native_solves=0,
        execution_count_basis=inspection['count_basis'],
        business_stage_timings=None,business_stage_function_counts=None,cache_hits_misses=None,
        db_stages='N/A: excluded offline workload',
        finding='Startup immediate-parent PID assertion failed; noncompute venv probe reproduced distinct owner and immediate parent. No F3 performance cause established.',
        fix='Tooling only: ProcessIdentity/liveness owner verification, exclusive claims, early consumed guard; not compute-verified.',
        tests=checks,unique_targeted_tests=41,
        test_scope='40 passed in targeted group, then16 affected observer tests passed after one added consumed-guard regression; overlap counted once. No Planning/inference/DB.',
        remaining='Separate explicit new compute authorization and frozen source required for stage profiling; representative C performance/real quality, product activation and browser E2E remain unverified.',
        preserved=dict(pre_f3_files=len(original),f3_upstream_inputs=len(inputs),f3_cases=len(replay['input_cases']),
            workbook_hashes={p:h for p,h in inputs.items() if p.endswith('.xlsx')},old_f4_receipt_unchanged=True,old_f4_zip_unchanged=True),
        prohibitions_observed=dict(retry=False,reset=False,train=False,new_benchmark=False,network_provider=False,commit_f4_1=False,push=False,stage_zip=False))
    write(BASE/'summary.json',summary)
    commands=dict(historical_compute=['.venv/Scripts/python.exe -B -m scripts.profile_planning_f4_1 prepare',
        '.venv/Scripts/python.exe -B -m scripts.profile_planning_f4_1 run --identity '+IDENTITY],
        warning='Consumed. These commands are provenance, not instructions to rerun.',
        verification=['.venv/Scripts/python.exe -B -m pytest tests/unit/test_planning_profile_observer.py tests/unit/test_forecast_serialization.py tests/unit/test_forecast_stockout.py tests/unit/test_forecast_model_contracts.py tests/unit/test_planning_public_contract.py -q --tb=short --junitxml=runtime/challenger/f4_1/final-tests.xml',
            '.venv/Scripts/python.exe -B -m pytest tests/unit/test_planning_profile_observer.py -q --tb=short --junitxml=runtime/challenger/f4_1/final-observer-tests.xml',
            'git diff --check','.venv/Scripts/python.exe -B -m scripts.review_challenger_f4_1'])
    write(BASE/'commands.json',commands)
    files={}
    def add(path):
        key=path.relative_to(ROOT).as_posix();assert key not in files
        files[key]=path.read_bytes()
    for name in (*CHANGED,*DEPENDENCIES):add(ROOT/name)
    for name in ('setup.json','preflight.json','preclaim-verification.json','receipt.json'):add(EXP/name)
    for path in sorted((EXP/'executed-source').rglob('*.py')):add(path)
    for name in ('compute-claim.json','resume-inspection.json','startup-probe.json','summary.json','commands.json','final-tests.xml','final-observer-tests.xml'):add(BASE/name)
    for name in ('runtime/challenger/f4/profile/receipt.json','runtime/challenger/f4/acceptance/native-package.json'):add(ROOT/name)
    files['README.md']=('''# F4.1 temporary review copy

Read runtime/challenger/f4_1/summary.json first, then the canonical F4 section in
docs/features/FORECAST_ENGINE_INTEGRATION.md and the runbook in docs/runbooks/FULL_TEST_FLOW.md.
The experiment setup/preflight/receipt and compute-claim are original evidence.
All business timings are UNMEASURED; compute failed before Planning/native inference.
Read startup-probe.json and final-*-tests.xml for noncompute verification only.
Review scripts/profile_planning_f4_1.py and planning_profile_observer.py plus tests.
executed-source/ retains exact pre-fix tooling; current source is fixed WIP, not an executed batch.
commands.json marks consumed compute commands as historical; do not rerun/reset.
MANIFEST.json gives every other payload path, SHA-256 and size (manifest excludes itself).
Selected dependencies aid inspection; this is not a standalone runnable/model package.
No model weights, workbook, credentials, DB or large logs are supplied.
Deleting this ZIP removes only a transfer copy; all source/evidence originals remain outside it.
''').encode()
    # Scan both recognizable secret formats and exact locally configured secrets.
    secrets=[]
    private=ROOT/'runtime/challenger/f4/private'
    if (private/'database.json').exists():
        password=urlsplit(read(private/'database.json')['url']).password
        if password:secrets.append(password.encode())
    if (private/'compose.env').exists():
        for line in (private/'compose.env').read_text().splitlines():
            if '=' in line and any(k in line.split('=',1)[0].upper() for k in ('PASSWORD','SECRET','TOKEN')):
                value=line.split('=',1)[1].strip().strip('"\'')
                if value:secrets.append(value.encode())
    patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'(?<![A-Za-z0-9])(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}',rb'postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:[^\s@]+@']
    for name,data in files.items():
        assert not any(part in ('.env','private') for part in Path(name).parts),name
        assert Path(name).suffix.lower() not in ('.xlsx','.xls','.bin','.pkl','.joblib','.db','.sqlite','.dump','.log','.whl'),name
        assert not any(secret in data for secret in secrets),f'Known secret in {name}'
        assert not any(re.search(pattern,data) for pattern in patterns),f'Secret signature in {name}'
    manifest=dict(schema=1,entries=[dict(path=p,sha256=sha(b),bytes=len(b)) for p,b in sorted(files.items())],
        changed_paths=list(CHANGED),checks=dict(secrets='PASS: known private credentials and secret signatures',source_correspondence='All disk-backed payloads copied byte-for-byte',no_business_source_delta=True),
        self_hash='Manifest excludes itself; archive checksum is in external review-verification.json')
    files['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
    (BASE/'review-README.md').write_bytes(files['README.md'])
    (BASE/'review-MANIFEST.json').write_bytes(files['MANIFEST.json'])
    assert subprocess.run(['git','check-ignore','-q',str(ZIP.relative_to(ROOT))],cwd=ROOT).returncode==0
    # Keep a previous transfer copy if this copy-only tool is invoked again.
    if ZIP.exists():
        previous=BASE/('previous-review-'+sha(ZIP.read_bytes())+'.zip')
        if not previous.exists():previous.write_bytes(ZIP.read_bytes())
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):archive.writestr(name,data)
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())==set(files)
        for name,data in files.items():assert archive.read(name)==data,name
        for entry in json.loads(archive.read('MANIFEST.json'))['entries']:
            data=archive.read(entry['path'])
            assert sha(data)==entry['sha256'] and len(data)==entry['bytes'],entry['path']
    for name,data in files.items():
        if name not in ('MANIFEST.json','README.md'):assert (ROOT/name).read_bytes()==data,name
    for name,digest in inspection['preserved_hashes'].items():assert sha((ROOT/name).read_bytes())==digest,name
    assert not git('diff','--cached','--name-only')
    result=dict(path=str(ZIP),bytes=ZIP.stat().st_size,files=len(files),sha256=sha(ZIP.read_bytes()),
        crc='PASS',manifest_hashes='PASS',source_correspondence='PASS',secrets='PASS',ignored=True,staged=False,
        original_evidence_preserved=True,profiling='UNRESOLVED',compute_rerun=False)
    write(BASE/'review-verification.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
