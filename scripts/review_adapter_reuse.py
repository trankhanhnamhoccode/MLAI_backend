"""Copy-only F4.2 summary/archive audit; never executes benchmark workloads."""
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
from urllib.parse import urlsplit
import zipfile
from scripts.review_challenger_f4_1 import DEPENDENCIES

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/challenger/f4_2'
ZIP=ROOT/'runtime/shelfcash_F4_2_review.zip'


def sha(data):return hashlib.sha256(data).hexdigest()
def load(p):return json.loads(p.read_bytes())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')


def summarize():
    setup=load(BASE/'setup.json');receipt=load(BASE/'resource-receipt.json')
    rows=[load(BASE/f'planning-{i}-result.json')|dict(index=i) for i in range(6) if (BASE/f'planning-{i}-result.json').exists()]
    pairs=[]
    for indices in setup['pairs']:
        selected=[r for r in rows if r['index'] in indices]
        if len(selected)!=2:continue
        b=next(r for r in selected if r['arm']=='baseline');c=next(r for r in selected if r['arm']=='candidate')
        pairs.append(dict(indices=indices,baseline_seconds=b['wall_seconds'],candidate_seconds=c['wall_seconds'],
            speedup=b['wall_seconds']/c['wall_seconds'],same_selected_exact_option=b['selected_option']==c['selected_option'],
            baseline_execution=b['execution'],candidate_execution=c['execution'],baseline_solves=b['native_solve_count'],
            candidate_solves=c['native_solve_count'],baseline_vectors=b['enumerated_vectors'],candidate_vectors=c['enumerated_vectors']))
    stats={}
    for arm in ('baseline','candidate'):
        seconds=[r['wall_seconds'] for r in rows if r['arm']==arm]
        if seconds:stats[arm]=dict(median=statistics.median(seconds),minimum=min(seconds),maximum=max(seconds))
    fixed={a:load(BASE/f'fixed-{a}-result.json') for a in ('baseline','candidate')}
    summary=dict(classification='CURRENT FACT',experiment=setup['identity'],baseline_commit=setup['baseline_commit'],
        benchmark_status=receipt['status'],resource_receipt=receipt,pairs=pairs,planning_seconds=stats,fixed_baskets=fixed,
        planning_outputs=rows,optimization='One module-level TypeAdapter for static NonnegativeDecimal; identical validate_python(view), error mapping and Quantity construction.',
        correctness='Differential corpus/threads and serving/procurement/comparison/serialization regressions pass; fixed baskets0/3 have identical serialized SHA-256 across isolated arms. Full deadline-bound outputs may differ.',
        limits=['Three repetitions, one machine/fixture; no significance/SLA/general F3 attribution.',
            'OpenAPI schema generation overlapped the early benchmark (first pair), causing possible CPU contention; remaining paired results are retained too.',
            'Import/Assistant Python workloads in other worktrees were observed at final inspection; timing overlap is unknown. They were not touched. Machine was not certified idle.',
            'No cProfile/observer; every arm is a fresh process, OS cache uncontrolled; imports/startup excluded from timed full Planning but included in180s total.',
            'Fixed-basket results are two single measurements, not whole Planning latency; all fixed tasks/startup are inside compute resource receipt.',
            'Same policy4s and proof/search rules; faster construction may alter coverage/winner/proof. No forced output equivalence.',
            'Native forecast inference/training/network/provider/DB writes0; this shared host optimization does not compare C forecast quality to B.'],
        activation='NOT IMPLEMENTED',promotion='LOCKED',wip=True)
    write(BASE/'summary.json',summary);return summary


def main():
    summary=summarize();setup=load(BASE/'setup.json')
    assert summary['benchmark_status']=='COMPLETE' and len(summary['pairs'])==3
    assert summary['resource_receipt']['planning_executions']==6
    assert summary['resource_receipt']['total_compute_wall_seconds']<180
    assert all(a['job_active_after']==0 and a['exit_code']==0 for a in summary['resource_receipt']['attempts'])
    assert git('rev-parse','HEAD')==setup['baseline_commit']
    assert git('rev-parse','main')=='b0db90cedd3962d8cb2e3f2dfe4696ec83b4e52a'
    assert not git('diff','--cached','--name-only')
    assert git('diff','--name-only','--','app').splitlines()==['app/application/use_cases/serving.py']
    assert sha((ROOT/'app/application/use_cases/serving.py').read_bytes())==setup['candidate_worktree_serving_sha256']
    assert sha((ROOT/'scripts/benchmark_adapter_reuse.py').read_bytes())==setup['driver_sha256']
    for arm in ('baseline','candidate'):
        for name,digest in setup[arm+'_source'].items():assert sha((BASE/'sources'/arm/name).read_bytes())==digest,name
    assert load(BASE/'openapi-check.json')['unchanged']
    # Historical evidence/source pins are preserved; no old replay or execution.
    preserved=load(ROOT/'runtime/challenger/f4_1/completion/preserved-before.json')
    for name,digest in preserved.items():assert sha((ROOT/name).read_bytes())==digest,name
    completion=ROOT/'runtime/challenger/f4_1/completion/experiments'/setup['previous_experiment']
    assert sha((completion/'setup.json').read_bytes())==setup['previous_setup_sha256']
    original=load(ROOT/'runtime/challenger/f3/preflight/preserved-before.json')
    for name,digest in original.items():assert sha((ROOT/name).read_bytes())==digest,name
    import xml.etree.ElementTree as ET
    counts={}
    for name in ('regressions.xml','tooling-tests.xml'):
        cases=list(ET.parse(BASE/name).iter('testcase'))
        assert all(not any(c.find(t) is not None for t in ('failure','error','skipped')) for c in cases)
        counts[name]=len(cases)
    write(BASE/'verification.json',dict(tests=counts,historical_files_unchanged=len(preserved),pre_f3_files_unchanged=len(original),
        no_api_delta=True,no_migration=True,no_stage=True,main_unchanged=True))
    write(BASE/'commands.json',dict(historical_benchmark=['.venv/Scripts/python.exe -B -m scripts.benchmark_adapter_reuse freeze',
        '.venv/Scripts/python.exe -B -m scripts.benchmark_adapter_reuse run'],warning='Consumed180s group; never rerun/reset.',
        tests=['.venv/Scripts/python.exe -B -m pytest tests/unit/test_serving_adapter_reuse.py tests/unit/test_serving.py tests/unit/test_serving_output_validation.py tests/unit/test_procurement_v2.py tests/unit/test_procurement_comparison.py tests/unit/test_forecast_serialization.py tests/unit/test_planning_profile_completion.py -q --tb=short --junitxml=runtime/challenger/f4_2/regressions.xml',
        '.venv/Scripts/python.exe -B -m pytest tests/unit/test_adapter_benchmark.py -q --tb=short --junitxml=runtime/challenger/f4_2/tooling-tests.xml'],
        review='.venv/Scripts/python.exe -B -m scripts.review_adapter_reuse',docs='git diff --check'))
    payload={}
    def add(p):payload[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    changed=set(git('diff','--name-only').splitlines())|set(git('ls-files','--others','--exclude-standard').splitlines())
    for name in sorted(changed|set(DEPENDENCIES)|{'app/application/use_cases/procurement.py','app/domain/decision/quantities.py',
        'tests/unit/test_serving.py','tests/unit/test_serving_output_validation.py','tests/unit/test_procurement_v2.py','tests/unit/test_procurement_comparison.py',
        'scripts/profile_windows_job.py','scripts/profile_planning_f4_1_completion.py'}):add(ROOT/name)
    for p in sorted(BASE.glob('*.json')):
        if not p.name.startswith('review-'):add(p)
    for name in ('regressions.xml','tooling-tests.xml'):add(BASE/name)
    add(BASE/'sources/baseline/app/application/use_cases/serving.py')
    add(BASE/'sources/candidate/app/application/use_cases/serving.py')
    payload['docs-delta.patch']=subprocess.check_output(['git','diff','--','docs'],cwd=ROOT)
    payload['README.md']=b'''# F4.2 temporary review
Read runtime/challenger/f4_2/summary.json, then canonical F4.2 docs/runbook.
Source change is only static TypeAdapter reuse in serving.py; fixed results retain hashes.
Read setup.json/source hashes, resource-receipt.json and every paired result.
Six full Planning runs, three per arm; no heavy instrumentation or forecast inference.
Whole deadline-bound outcomes/proof may differ; keep all pairs and CPU-contention caveat.
Baseline serving source is included; full baseline snapshot remains outside ZIP.
MANIFEST.json hashes every other payload. No weights/workbooks/secrets/DB or large logs.
Commands marked historical must not rerun/reset the consumed group.
All source/evidence and manifest/README remain outside ZIP; deleting ZIP removes only a copy.
F4.2 remains WIP. No activation, promotion, merge, push or deployment.
'''
    secrets=[];private=ROOT/'runtime/challenger/f4/private'
    if (private/'database.json').exists():
        value=urlsplit(load(private/'database.json')['url']).password
        if value:secrets.append(value.encode())
    if (private/'compose.env').exists():
        for line in (private/'compose.env').read_text().splitlines():
            if '=' in line and any(k in line.split('=',1)[0].upper() for k in ('PASSWORD','TOKEN','SECRET')):
                v=line.split('=',1)[1].strip().strip('"\'')
                if v:secrets.append(v.encode())
    patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'(?<![A-Za-z0-9])(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}',rb'postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:[^\s@]+@']
    for name,data in payload.items():
        assert not any(p in ('.env','private') for p in Path(name).parts),name
        assert Path(name).suffix.lower() not in ('.bin','.xlsx','.pkl','.db','.dump','.log','.whl'),name
        assert not any(v in data for v in secrets),name
        assert not any(re.search(p,data) for p in patterns),name
    manifest=dict(changed_paths=sorted(changed),entries=[dict(path=p,bytes=len(b),sha256=sha(b)) for p,b in sorted(payload.items())],self_excluded=True)
    payload['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
    (BASE/'review-MANIFEST.json').write_bytes(payload['MANIFEST.json']);(BASE/'review-README.md').write_bytes(payload['README.md'])
    assert subprocess.run(['git','check-ignore','-q',str(ZIP.relative_to(ROOT))],cwd=ROOT).returncode==0
    if ZIP.exists():
        prior=BASE/('prior-review-'+sha(ZIP.read_bytes())+'.zip')
        if not prior.exists():prior.write_bytes(ZIP.read_bytes())
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):archive.writestr(name,data)
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None and set(archive.namelist())==set(payload)
        for name,data in payload.items():assert archive.read(name)==data
        for row in json.loads(archive.read('MANIFEST.json'))['entries']:assert sha(archive.read(row['path']))==row['sha256']
    for name,data in payload.items():
        if name not in ('README.md','MANIFEST.json','docs-delta.patch'):assert (ROOT/name).read_bytes()==data,name
    result=dict(path=str(ZIP),bytes=ZIP.stat().st_size,files=len(payload),sha256=sha(ZIP.read_bytes()),
        crc='PASS',manifest='PASS',source_correspondence='PASS',secrets='PASS',ignored=True,staged=False,originals_preserved=True)
    write(BASE/'review-verification.json',result);print(json.dumps(result))


if __name__=='__main__':main()
