"""A/B action scope, dataset-bound declarations and distinct manifest identities."""
from decimal import Decimal
from pathlib import Path
import pytest

from app.application.contracts.demo_workbooks import AdmissionDeclarations
from app.application.contracts.forecast_benchmark import ARMS,ArmCheckpoint,BenchmarkPlan
from app.application.contracts.forecast_challenger import ChallengerError
from app.application.demo_workbook_normalization import normalize_demo
from app.application.demo_workbook_admission import assess
from app.application.forecast_benchmark_admission import admit_plan,holdout_dates
from app.application.forecast_benchmark_reporting import summary
from app.application.use_cases.forecast_baseline import run_historical_quantile_baseline
from app.application.use_cases.forecast_benchmark import load_protocol
from app.infrastructure.forecast_benchmark_features import prepared_at
from app.infrastructure import forecast_benchmark_training as training
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
from scripts import prepare_demo_benchmark as command
from tests.fixtures.forecast_engine.benchmark_setup import synthetic_benchmark
from tests.unit.test_demo_workbook_admission import bundle,xlsx,headers,OP_TABLES,CALENDAR_HEADERS
from app.infrastructure.demo_workbook_reader import discover_workbooks

ROOT=Path(__file__).resolve().parents[2]


def test_sales_menu_only_admits_host_scope_without_six_files(tmp_path):
    selected=tuple(b for b in bundle(tmp_path) if b.role in ('pos','menu'))
    data,issues=normalize_demo(selected,'UTC')
    config=AdmissionDeclarations(timezone='UTC',accept_five_single_item_scope=True,
        observation_availability='RETROSPECTIVE_NEXT_RUN_ASSUMPTION',source_revision=data.source_revision)
    manifest,_,projection,plan=assess(data,selected,config,issues,load_protocol(ROOT))
    assert projection is not None and projection.calendar==()
    assert manifest['forecast_AB']=='READY_DEMO_EXPLORATORY_INPUT'
    assert manifest['forecast_C']==manifest['E4']=='BLOCKED'
    assert plan.harness_version=='causal_benchmark/2' and plan.configuration_ids==ARMS[:2]


def test_count_sheet_date_and_extra_supplier_columns_are_content_driven(tmp_path):
    bundle(tmp_path)
    stock={3:headers(OP_TABLES['inventory'][2]),4:{'A':'46211','B':'Material','C':'2','D':'g'}}
    vendor={3:headers((*OP_TABLES['vendor_terms'][2],'shelf_life_days')),4:{'A':'Vendor','B':'Material','J':'5'}}
    purchase={3:headers(OP_TABLES['purchase_history'][2])}
    (tmp_path/'stock_vendor.xlsx').write_bytes(xlsx({'KiemKe_08-07':stock,'PNK tháng 7':purchase,'Vendor rules':vendor}))
    books=discover_workbooks(tmp_path);data,issues=normalize_demo(books)
    _,tables,_,_=assess(data,books,AdmissionDeclarations(),issues,load_protocol(ROOT))
    assert next(t for t in tables if t['kind']=='inventory')['sheet']=='KiemKe_08-07'
    vendor=next(t for t in tables if t['kind']=='vendor_terms')
    assert vendor['headers'][-1]=='shelf_life_days' and vendor['rows'][0][-1].raw=='5'


def test_hash_bound_declaration_cannot_apply_to_other_dataset(tmp_path,monkeypatch):
    bundle(tmp_path)
    monkeypatch.setattr(command,'BenchmarkStorage',lambda root:BenchmarkStorage(tmp_path/'owned-runtime'))
    config=AdmissionDeclarations(timezone='UTC',accept_five_single_item_scope=True,
        observation_availability='RETROSPECTIVE_NEXT_RUN_ASSUMPTION',source_revision='a'*64)
    with pytest.raises(ValueError,match='DECLARATION_DATASET_HASH_MISMATCH'): command.prepare(tmp_path,ROOT,config)


def test_calendar_conflict_blocks_only_its_consumer(tmp_path):
    bundle(tmp_path)
    rows={3:headers(CALENDAR_HEADERS),4:{'A':'46023','C':'FALSE','D':'FALSE'},
          5:{'A':'46023','C':'TRUE','D':'TRUE'},6:{'A':'bad-date','C':'FALSE','D':'FALSE'}}
    (tmp_path/'calendar.xlsx').write_bytes(xlsx({'Calendar + Weather':rows}))
    books=discover_workbooks(tmp_path);data,issues=normalize_demo(books,'UTC')
    config=AdmissionDeclarations(timezone='UTC',accept_five_single_item_scope=True,
        observation_availability='RETROSPECTIVE_NEXT_RUN_ASSUMPTION',source_revision=data.source_revision)
    manifest,_,projection,_=assess(data,books,config,issues,load_protocol(ROOT))
    assert {f.area for f in issues}=={'FORECAST_C'}
    assert projection is not None and manifest['forecast_AB']=='READY_DEMO_EXPLORATORY_INPUT'


@pytest.mark.parametrize('operation',[
    "import sqlalchemy", "import socket; socket.socket().connect(('127.0.0.1',5432))",
    "import subprocess; subprocess.run(['python','--version'])"])
def test_offline_guard_denies_db_network_and_grandchildren(operation):
    import subprocess,sys
    code='from scripts.run_demo_benchmark import install_offline_guard\ninstall_offline_guard()\n'+operation
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and 'OFFLINE_BENCHMARK_FORBIDDEN_' in result.stderr


def test_v2_ab_selection_uses_common_masks_and_never_claims_c():
    data,old=synthetic_benchmark()
    plan=BenchmarkPlan.model_validate(old.model_dump(mode='python')|dict(harness_version='causal_benchmark/2',configuration_ids=ARMS[:2]))
    admit_plan(data,plan)
    checkpoints=[]
    for task in plan.tasks:
        result=run_historical_quantile_baseline(prepared_at(data,task.origin,exclude=holdout_dates(plan)))
        for arm in plan.configuration_ids:
            rows=training.raw_records(data,task,arm,result)
            checkpoints.append(ArmCheckpoint(arm=arm,origin=task.origin,identity='a'*64,status='COMPLETED',reason=None,
                predictions=rows,input_digest='a'*64,training_seconds=Decimal(0),inference_seconds=Decimal(0)))
    report=summary(data,plan,tuple(checkpoints),complete=True)
    assert report['paired_tasks']==56 and report['selected_by_validation_only']==ARMS[0]
    assert report['status']=='EXPLORATORY' and report['comparison_arms']==ARMS[:2]
    assert not report['challenger_evidence'] and not report['challenger_strict_improvement']
    assert report['metrics'] and report['masks']['censored_lower_bound']==2
    with pytest.raises(ChallengerError,match='FROZEN_PROTOCOL_OR_ARMS_CHANGED'):
        admit_plan(data,BenchmarkPlan.model_validate(plan.model_dump(mode='python')|dict(configuration_ids=ARMS)))


def test_v2_fit_identity_pins_merged_host_and_v1_keeps_its_boundary(monkeypatch):
    data,v1=synthetic_benchmark()
    v2=BenchmarkPlan.model_validate(v1.model_dump(mode='python')|dict(harness_version='causal_benchmark/2',configuration_ids=ARMS[:2]))
    config=load_protocol(ROOT)['arm_configuration'][ARMS[0]]
    before=[training.fit_identity(data,p,p.tasks[0],ARMS[0],config) for p in (v1,v2)]
    monkeypatch.setattr(training,'host_source_identity',lambda:'b'*64)
    after=[training.fit_identity(data,p,p.tasks[0],ARMS[0],config) for p in (v1,v2)]
    assert before[0]==after[0] and before[1]!=after[1]
