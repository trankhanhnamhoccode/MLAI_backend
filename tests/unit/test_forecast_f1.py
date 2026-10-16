"""No-training regressions for F1 budget identities, source proof and exact diagnostics."""
from dataclasses import replace
from datetime import date,datetime,timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from app.application.contracts.forecast_benchmark import BenchmarkPlan,BenchmarkBudget,ARMS,DEMO_ABC_PROTOCOL_DIGEST
from app.application.forecast_benchmark_plan import restore_plan
from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
from app.domain.forecasting.diagnostics import Point,score,sensitivity
from tests.fixtures.forecast_engine.benchmark_setup import synthetic_benchmark

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('seconds',[300,300.0,250,250.0,299.125,0.25])
@pytest.mark.parametrize('version',[1,2,3])
def test_budget_roundtrip_preserves_only_resource_representation(seconds,version):
    _,base=synthetic_benchmark()
    raw=base.model_dump(mode='json')
    raw.update(harness_version=f'causal_benchmark/{version}',configuration_ids=list(ARMS[:2] if version==2 else ARMS))
    if version==3:
        raw['protocol_digest']=DEMO_ABC_PROTOCOL_DIGEST
        raw['tasks']=json.loads((ROOT/'tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json').read_bytes())['tasks']
    raw['budget']['wall_seconds']=seconds
    plan=restore_plan(raw,BenchmarkPlan)
    assert type(plan.budget.wall_seconds) is type(seconds)
    assert canonical_bytes(plan)==canonical_bytes(raw)
    changed=json.loads(canonical_bytes(plan));changed['budget']['wall_seconds']=seconds/2
    assert challenger_digest('experiment-plan',plan)!=challenger_digest('experiment-plan',restore_plan(changed,BenchmarkPlan))


@pytest.mark.parametrize('seconds',[0,-1,301,float('nan'),float('inf'),True,'300'])
def test_budget_invalid_values_reject_instead_of_rescuing_identity(seconds):
    with pytest.raises(ValidationError):BenchmarkBudget(wall_seconds=seconds)


def test_int_and_float_identities_are_distinct_no_broad_numeric_normalization():
    assert canonical_bytes(BenchmarkBudget(wall_seconds=300))!=canonical_bytes(BenchmarkBudget(wall_seconds=300.0))
    _,plan=synthetic_benchmark();raw=plan.model_dump(mode='json');raw['tasks'][0]['unexpected_numeric']=300
    with pytest.raises(ValidationError):restore_plan(raw,BenchmarkPlan)


def test_historical_snapshot_hash_and_git_proof_both_required(tmp_path,monkeypatch):
    from scripts import forecast_replay_source as source
    experiment='a'*64;commit='b'*40
    environment=tmp_path/'runtime/challenger/benchmarks/experiments'/experiment/'environment.json'
    environment.parent.mkdir(parents=True);environment.write_bytes(b'original environment')
    monkeypatch.setattr(source,'git_sources',lambda *args:{'app/example.py':b'original\n'})
    raw=b'original\r\n'
    manifest=dict(schema_version=1,git_commit=commit,experiment=experiment,environment_sha256=hashlib.sha256(environment.read_bytes()).hexdigest(),
        files={'app/example.py':hashlib.sha256(raw).hexdigest()})
    snapshot=tmp_path/source.digest(manifest);(snapshot/'app').mkdir(parents=True)
    (snapshot/'app/example.py').write_bytes(raw);(snapshot/'source.json').write_text(json.dumps(manifest),encoding='utf-8')
    assert source.verify(tmp_path,snapshot,experiment)==manifest
    (snapshot/'app/example.py').write_bytes(b'tampered\n')
    with pytest.raises(ValueError,match='SOURCE_HASH'):source.verify(tmp_path,snapshot,experiment)
    with pytest.raises(ValueError,match='SOURCE_IDENTITY'):source.verify(tmp_path,snapshot,'c'*64)
    # Re-signing a modified snapshot cannot substitute for the trusted Git source.
    manifest['files']['app/example.py']=hashlib.sha256(b'tampered\n').hexdigest()
    resigned=tmp_path/source.digest(manifest)
    (resigned/'app').mkdir(parents=True)
    (resigned/'app/example.py').write_bytes(b'tampered\n')
    (resigned/'source.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='SOURCE_GIT_MISMATCH'):source.verify(tmp_path,resigned,experiment)


def test_plan_tamper_changes_pinned_experiment_identity():
    _,base=synthetic_benchmark();raw=base.model_dump(mode='json');raw['budget']['wall_seconds']=300
    original=restore_plan(raw,BenchmarkPlan);original_id=challenger_digest('experiment',original)
    raw['budget']['wall_seconds']=299
    assert challenger_digest('experiment',restore_plan(raw,BenchmarkPlan))!=original_id
    raw['dataset_digest']='f'*64
    from app.application.forecast_benchmark_admission import admit_plan
    data,_=synthetic_benchmark()
    with pytest.raises(ValueError,match='DATASET_DIGEST_MISMATCH'):admit_plan(data,restore_plan(raw,BenchmarkPlan))


def test_artifact_bytes_tamper_rejects_without_training(tmp_path):
    from app.application.contracts.forecast_challenger import ChallengerArtifact,RuntimeIdentity,FitWindow,ArtifactFile
    from app.infrastructure.storage.forecast_challenger import CORE_FILES,ChallengerStorage
    files={name:b'{}' for name in CORE_FILES if name!='artifact_checksums.json'}
    checksums={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}
    files['artifact_checksums.json']=canonical_bytes(dict(algorithm='sha256',files=checksums))
    now=datetime(2026,10,15,tzinfo=timezone.utc);window=FitWindow(start=date(2026,1,1),end=date(2026,1,2),labels_available_at=now)
    manifest=ChallengerArtifact(model_version='fake-byte-integrity-only',purpose='synthetic_correctness',holdout_status='SYNTHETIC_ONLY',
        promotion_status='trained_candidate',production_available_at=None,store_id=UUID(int=1),products=(),timezone='UTC',
        runtime=RuntimeIdentity(adapter_code_digest='a'*64,python='test',platform='test',machine='test',dependencies=()),
        training=window,point_fit=window,calibration=window,fitted_at=now,published_at=now,available_at=now,
        publication_basis='local_snapshot_admission',config_digest='b'*64,feature_digest='b'*64,postprocess_digest='b'*64,
        files=tuple(ArtifactFile(name=n,digest=hashlib.sha256(v).hexdigest()) for n,v in files.items()))
    storage=ChallengerStorage(tmp_path);identity=storage.publish_artifact(manifest,files)
    (storage.load_artifact(identity).directory/'model_q25.txt').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='ARTIFACT_CHECKSUM_MISMATCH'):storage.load_artifact(identity)


def point(y,q,*,h=1,target='2026-06-30'):
    return Point('p','ly','2026-06-24',target,'holdout',h,F(y),tuple(map(F,q)))


def test_independent_metrics_literal_ties_zero_denominator_and_cqr_separation():
    p=point(10,(5,10,15));q=point(0,(0,2,3),h=2)
    m=score((p,q))
    assert m['mae']==1 and m['wape']==F(1,5) and m['bias']==1
    assert m['pinball']==(F(5,8),F(1,2),F(1))
    assert m['quantile_coverage']==1 and m['below_p25']==0 and m['above_p75']==0
    assert m['at_or_below_p50']==1 and m['median_ties']==1 and m['lower_ties']==1
    assert m['cqr_coverage'] is None and score((q,))['wape'] is None
    assert score((replace(p,interval=(F(9),F(11))),))['cqr_width']==2


def test_sensitivity_never_changes_official_mask_and_detects_single_date_effect():
    closed=point(0,(9,10,11),h=6);other=point(5,(4,5,6),target='2026-07-01')
    c=(replace(closed,quantiles=(F(0),)*3),replace(other,quantiles=(F(6),)*3))
    result=sensitivity({'A':(closed,other),'B':(closed,other),'C':c})
    assert result['net_B_minus_C_absolute_error']==9
    assert result['horizon6_share_of_net']==F(10,9)
    assert result['subsets']['without_horizon6']['B']['mae']==0
    assert result['subsets']['without_horizon6']['C']['mae']==1
    assert closed.quantiles==(9,10,11)
