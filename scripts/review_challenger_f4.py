"""Copy-only F4 evidence audit/review ZIP. No benchmark, training, reset or staging."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
F4=ROOT/'runtime/challenger/f4'
ZIP=ROOT/'runtime/shelfcash_F4_review.zip'
F3='e7aa4b531b6f7ed3fb355856fa5145bac0c7472d2df3da6bce7b7fa00afa9586'
F3_VERIFY='88b89d8dd839b44927156335658e54bc1203ae28e2b243029f9173c889108199'
DEPENDENCIES=(
    'AGENTS.md','pyproject.toml','alembic/env.py',
    'app/main.py','app/api/planning_public.py','app/api/auth.py',
    'app/application/contracts/auth.py','app/application/use_cases/auth.py',
    'app/repositories/auth.py','app/infrastructure/database/auth_session.py',
    'app/domain/permissions.py','docs/AUTHORIZATION_CONTRACT_VI.md',
    'app/infrastructure/forecast_model.py',
    'app/application/contracts/common.py','app/application/contracts/forecast_challenger.py',
    'app/application/contracts/forecast.py','app/application/contracts/model_serving.py',
    'app/application/contracts/planning_public.py','app/application/contracts/decision_capture.py',
    'app/application/forecast_challenger_serialization.py','app/application/forecast_challenger_validation.py',
    'app/application/forecast_serialization.py','app/application/planning_serialization.py',
    'app/application/planning_retained_reads.py','app/application/planning_public_projection.py',
    'app/application/use_cases/forecast_challenger.py','app/application/use_cases/forecast_execution.py',
    'app/application/use_cases/forecast_trained_execution.py','app/application/use_cases/forecast.py',
    'app/application/use_cases/decision_pipeline_v2.py','app/application/use_cases/bom.py',
    'app/application/use_cases/serving.py','app/application/use_cases/procurement_v2.py',
    'app/application/use_cases/procurement_selection.py','app/infrastructure/forecast_challenger_runtime.py',
    'app/infrastructure/forecast_challenger_native.py','app/infrastructure/storage/forecast_challenger.py',
    'app/infrastructure/database/forecast_execution_session.py','app/infrastructure/database/decision_capture_v2.py',
    'app/infrastructure/planning_process.py','app/repositories/planning.py','app/repositories/forecast.py',
    'app/repositories/forecast_input.py','app/repositories/forecast_execution_metadata.py',
    'app/models/forecast_run.py','app/models/forecast_run_input.py','app/models/forecast_prediction.py',
    'app/models/planning_run.py','app/models/model_serving.py',
    'tests/planning_process_cases.py','tests/integration/test_planning_configuration_public.py',
    'tests/integration/test_readiness_context.py',
    'scripts/requirements-forecast-challenger.lock.txt',
    'vendor/forecast_challenger/pyproject.toml','vendor/forecast_challenger/shelfcash_forecast/snapshot_provenance.json')


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf-8').strip()


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def cases(path):
    result={}
    for case in ET.parse(path).iter('testcase'):
        assert not any(case.find(tag) is not None for tag in ('failure','error','skipped'))
        result[(case.attrib['classname'],case.attrib['name'])]=True
    return result


def audit():
    # Preserve original runtime inputs, not just their existence.
    original=json.loads((ROOT/'runtime/challenger/f3/preflight/preserved-before.json').read_bytes())
    changed=[p for p,h in original.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    setup=json.loads((ROOT/f'runtime/challenger/f3/experiments/{F3}/setup.json').read_bytes())['value']
    changed_inputs=[p for p,h in setup['inputs'].items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    replay=json.loads((ROOT/f'runtime/challenger/f3/verifications/{F3_VERIFY}/replay.json').read_bytes())['value']
    altered_cases=[p for p,h in replay['input_cases'].items() if sha(ROOT/f'runtime/challenger/f3/experiments/{F3}'/p)!=h]
    assert not changed and not changed_inputs and not altered_cases
    write(F4/'acceptance/preservation.json',dict(original_pre_f3_files=len(original),f3_upstream_inputs=len(setup['inputs']),
        f3_completed_case_hashes=len(replay['input_cases']),changed=changed,changed_inputs=changed_inputs,changed_cases=altered_cases,
        workbooks={p:h for p,h in setup['inputs'].items() if p.endswith('.xlsx')},
        f3_status='PARTIAL19/24; no resume or new case execution',originals_preserved=True))
    root=F4/'acceptance'
    units=cases(root/'final-unit-api.xml')
    # The whole current F4 module supersedes its older parameter names; do not
    # count renamed parametrizations or overlapping focused reruns twice.
    units={k:v for k,v in units.items() if k[0]!='tests.unit.test_planning_challenger'}
    units.update(cases(root/'final-f4-unit.xml'))
    pg=cases(root/'final-pg.xml')
    pg.update(cases(root/'final-strengthened.xml'));pg.update(cases(root/'final-trace.xml'))
    pg.update(cases(root/'native-revocation.xml'))
    assert len(units)==230 and len(pg)==18
    from app.infrastructure.planning_challenger_identity import integration_digest
    trace=json.loads((root/'native-trace.json').read_bytes())
    assert trace['acceptance_pin']['integration_code_digest']==integration_digest()
    import importlib.metadata as metadata
    from app.application.contracts.forecast_challenger import ENGINE_DISTRIBUTION,ENGINE_VERSION
    from app.infrastructure.forecast_challenger_runtime import current_runtime
    distribution=metadata.distribution(ENGINE_DISTRIBUTION)
    direct=json.loads(distribution.read_text('direct_url.json') or '{}')
    assert distribution.version==ENGINE_VERSION and not direct.get('dir_info',{}).get('editable',False)
    assert direct.get('archive_info') and 'site-packages' in Path(distribution.locate_file('')).parts
    write(root/'native-package.json',dict(distribution=ENGINE_DISTRIBUTION,version=distribution.version,
        non_editable=True,installed_in_site_packages=True,wheel_archive_hashes=direct['archive_info'].get('hashes'),
        runtime=current_runtime().model_dump(mode='json')))
    # Identity guard precedes the fresh read-only status connection.
    from app.config import Settings
    from scripts.dev import validate_reset_target,inspect_database
    url=json.loads((F4/'private/database.json').read_bytes())['url']
    settings=Settings(_env_file=None,environment='test',database_url=url)
    validate_reset_target(settings)
    state=inspect_database(settings)
    assert state['database']=='shelfcash_challenger_test' and state['current_user']=='shelfcash_challenger_tester'
    assert state['at_head'] and state['revisions']==['f4_20261016_metadata_v2']
    assert all(count==0 for name,count in state['tables'].items() if name!='alembic_version')
    write(root/'database.json',state|dict(host='127.0.0.1',port=5438,all_application_rows_after_cleanup=0))
    from sqlalchemy import create_engine,text
    engine=create_engine(url)
    try:
        with engine.connect() as connection:
            flags=connection.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
            assert not any(flags)
            assert not connection.scalar(text("SELECT bool_or(has_database_privilege(current_user,oid,'CONNECT')) FROM pg_database WHERE datname!=current_database() AND datallowconn"))
    finally:engine.dispose()
    report=dict(status='TARGETED_TECHNICAL_TEST_OPT_IN_VERIFIED',unit_api_unique=len(units),postgres_unique=len(pg),
        counts='205 unaffected unit/API + current25-case F4 module; PG union18. Overlapping reruns are not added.',
        native='Actual pinned non-editable package, synthetic constant artifact; no fitting/training.',
        public='C02 real session/Origin/CSRF -> PlanningExecution -> ForecastRun/PlanningRun -> C03/C08 -> fresh Session/process read.',
        exact_case=dict(purchase=0,fees=0,total=0,LOW_requested=54,BASE_requested=66,HIGH_requested=78,service='1/1 on all paths'),
        mock_faults=['lost COMMIT ACK after actual commit','dependency/native exception','integration code digest change'],
        actual_restart='Spawned owner claimed durably, parent terminated it; new worker instance recovered PROCESS_INTERRUPTED without inference; stale/terminal writes rejected.',
        limitations=['Not a full-suite run or host training/evaluation persistence rerun.',
            'No death-during-inference, HTTP server restart, browser E2E, production eligibility, accuracy or real-impact acceptance.',
            'Single profiling batch failed admission before any measured native/Planning stage; no optimization.'],
        fail_fix=['BE auth dependencies missing -> installed declared pyproject dependencies.',
            'Metadata DB schema1 constraint -> explicit schema2 constraint-only migration.',
            'Host serving-version reconciliation -> acceptance/2 binds the complete challenger pin.',
            'Test expected queued receipt after completion -> asserted existing terminal replay200/status instead.',
            'Safe challenger errors missing durable allowlist -> explicit sanitized codes; failed cases passed affected rerun.'],
        test_cases={'unit_api':['::'.join(k) for k in sorted(units)],'postgres':['::'.join(k) for k in sorted(pg)]},
        production='LOCKED',source_head=git('rev-parse','HEAD'),main=git('rev-parse','main'),merge_base=git('merge-base','HEAD','main'))
    write(root/'summary.json',report)
    files={}
    native=ROOT/'runtime/challenger/artifacts/0c3c2b7539c0050bdf52fbfffa56f6ddac03c68654b3462ad1d2f2626896d936'
    for p in native.iterdir():files[p.relative_to(ROOT).as_posix()]=sha(p)
    host=ROOT/'runtime/challenger/benchmarks/fits/12aceff4a568a50967aa253ead93d37a67b244b746f430b0da4af133a89bd0ad'
    for name in ('host-model.json','checkpoint.json'):files[(host/name).relative_to(ROOT).as_posix()]=sha(host/name)
    write(root/'source-artifacts.json',dict(not_bundled=files,wheel={p.name:sha(p) for p in (ROOT/'runtime/challenger/wheels').glob('*.whl')},
        setup='Build non-editable wheel from committed vendor snapshot. Copy exact retained fixture inputs; no fits or research promotion. See FULL_TEST_FLOW#forecast-f4.'))


def main():
    assert not git('diff','--cached','--name-only'),'Do not package/stage over another staged change'
    audit()
    review=F4/'review';review.mkdir(parents=True,exist_ok=True)
    changed=set(git('diff','--name-only','--diff-filter=ACMRT').splitlines())
    changed.update(git('ls-files','--others','--exclude-standard').splitlines())
    assert changed and all(not p.startswith('runtime/') for p in changed)
    inputs={p:'F4 change' for p in changed}
    for name in DEPENDENCIES:inputs.setdefault(name,'direct review dependency')
    evidence=['acceptance/summary.json','acceptance/database.json','acceptance/preservation.json','acceptance/source-artifacts.json',
        'acceptance/native-trace.json','acceptance/native-package.json','acceptance/host-native.json','acceptance/final-unit-api.xml',
        'acceptance/final-pg.xml','acceptance/final-strengthened.xml','acceptance/final-f4-unit.xml','acceptance/final-trace.xml','acceptance/native-revocation.xml',
        'profile/consumed.json','profile/receipt.json','profile/progress.json','openapi/comparison.json']
    for name in evidence:inputs['runtime/challenger/f4/'+name]='sanitized evidence'
    patch=subprocess.check_output(['git','diff','HEAD','--','docs'],cwd=ROOT)
    (review/'docs-delta.patch').write_bytes(patch)
    inputs['runtime/challenger/f4/review/docs-delta.patch']='canonical docs delta'
    readme='''F4 — gói review tạm, không phải ứng dụng standalone.

Đọc trước:
1. docs/features/FORECAST_ENGINE_INTEGRATION.md#forecast-f4 — boundary/gates/limits.
2. app/application/use_cases/planning_challenger.py và contracts/planning_challenger.py — pin, native, retention.
3. tests/integration/test_planning_challenger.py — public/worker/PG/fault/process acceptance.
4. runtime/challenger/f4/acceptance/summary.json, native-trace.json và profile/receipt.json.
5. docs/runbooks/FULL_TEST_FLOW.md#forecast-f4 — clone setup và exact test commands.

F3 commit5a8e0a8: PARTIAL19/24 synthetic. F4 source giữ WIP, không promote/push/deploy.
Default host; C0 chỉ test opt-in, C1 exploratory, production LOCKED, browser E2E chưa verify.
230 unit/API +18 PG unique, targeted coverage; không cộng các rerun trùng.
Profiling claim consumed: admission ARTIFACT_RUNTIME_MISMATCH, không có stage timing/Planning/native; không retry.
Manifest giữ relative paths, byte hashes và source/main/merge-base. Source files là bản sao nguyên byte.
ZIP không có .env/private config, credentials/session tokens, DB dump, workbook, model payload/wheel hoặc logs lớn.
Các model inputs không đóng gói và SHA-256 nằm trong acceptance/source-artifacts.json; vendor wheel có thể build từ clone.
Giữ repository clone để chạy; direct review dependencies không phải toàn bộ dependency closure.
Xóa ZIP chỉ xóa bản sao: source/evidence/manifest gốc nằm ngoài ZIP, không di chuyển hay xóa originals.
'''
    (review/'REVIEW_README.md').write_text(readme,encoding='utf-8')
    inputs['README_REVIEW.md']='read order/setup/limits'
    # Never package private runtime or opaque/model/workbook payloads.
    forbidden_suffixes={'.xlsx','.xls','.db','.sqlite','.sqlite3','.pkl','.pickle','.whl','.dll','.exe','.bin'}
    private=json.loads((F4/'private/database.json').read_bytes())['url']
    from sqlalchemy.engine import make_url
    known_secrets=[private,make_url(private).password]
    env=(F4/'private/compose.env').read_text()
    known_secrets.append(env.split('=',1)[1].strip())
    patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\b(?:ghp_|github_pat_|sk-or-v1-)[A-Za-z0-9_-]{20,}',
        rb'\bAKIA[0-9A-Z]{16}\b',rb'\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}']
    payload={};manifest=[]
    for name,purpose in sorted(inputs.items()):
        path=review/'REVIEW_README.md' if name=='README_REVIEW.md' else ROOT/name
        assert path.resolve().is_relative_to(ROOT.resolve()) and path.is_file() and not path.is_symlink()
        assert path.suffix.lower() not in forbidden_suffixes and '.env' not in path.name and '/private/' not in name
        assert path.stat().st_size<1024*1024,'Review member unexpectedly large'
        data=path.read_bytes()
        assert not any(secret and secret.encode() in data for secret in known_secrets),'Private credential detected'
        assert not any(re.search(pattern,data) for pattern in patterns),'Secret-shaped payload detected'
        payload[name]=data
        manifest.append(dict(path=name,source_path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),purpose=purpose))
    value=dict(schema='shelfcash_f4_review/1',source_head=git('rev-parse','HEAD'),main=git('rev-parse','main'),
        merge_base=git('merge-base','HEAD','main'),branch=git('branch','--show-current'),f4_state='UNCOMMITTED_WIP',
        changed_paths=sorted(changed),files=manifest,
        secret_check='Dedicated private URL/password/admin secret and credential signatures checked; no private runtime inputs included.',
        exclusions='Models/wheel/workbooks/private env/credentials/session tokens/DB dumps/large logs. Original inputs retained; see source-artifacts.json.')
    manifest_bytes=json.dumps(value,ensure_ascii=False,indent=2).encode()
    (review/'MANIFEST.json').write_bytes(manifest_bytes)
    (review/'MANIFEST.sha256').write_text(hashlib.sha256(manifest_bytes).hexdigest()+'  MANIFEST.json\n')
    payload['MANIFEST.json']=manifest_bytes;payload['MANIFEST.sha256']=(review/'MANIFEST.sha256').read_bytes()
    # The explicitly requested ZIP can be replaced; evidence/source are only copied.
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):archive.writestr(name,data)
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(set(archive.namelist()))==len(payload)
        for name,data in payload.items():assert archive.read(name)==data
    assert all((review/'REVIEW_README.md' if name=='README_REVIEW.md' else ROOT/name).read_bytes()==data
        for name,data in payload.items() if name not in {'MANIFEST.json','MANIFEST.sha256'})
    assert not git('ls-files','--','runtime/shelfcash_F4_review.zip')
    subprocess.run(['git','check-ignore','-q','runtime/shelfcash_F4_review.zip'],cwd=ROOT,check=True)
    assert not git('diff','--cached','--name-only')
    result=dict(path=str(ZIP),bytes=ZIP.stat().st_size,files=len(payload),sha256=sha(ZIP),
        crc='PASS',hashes='PASS',source_correspondence='PASS',secrets='PASS',git_ignored=True,staged=False,
        changed_files=len(changed),direct_dependencies=sum(p=='direct review dependency' for p in inputs.values()),
        originals_preserved=True)
    write(review/'verification.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
