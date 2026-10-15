"""Native admission/fault categories and legacy identity, no DB or fitting."""
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from copy import deepcopy
import hashlib
import json
import pytest
from pydantic import ValidationError
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.contracts.forecast_challenger import ChallengerInput,ChallengerError,ChallengerFailure,ChallengerOutput
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.forecast_challenger_validation import admit_input,validate_output
from app.application.forecast_serialization import serialize_prepared,restore_prepared,PREFIX
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.application.use_cases.planning_challenger import raw_matches,safe_failure
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from tests.fixtures.forecast_engine.planning_f4_setup import rebind_fixture


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    root=tmp_path_factory.mktemp('f4_native_no_train')
    storage=ChallengerStorage(root)
    value=rebind_fixture(storage,UUID(int=1),UUID(int=11),'cup',datetime.now(timezone.utc))
    service=ForecastChallenger(storage,enabled=True)
    output=service.execute(value).evidence.output
    return value,storage,service,output


def prepared(value,**changes):
    return PreparedForecastInput(schema_version=3,demand_policy='engine_native_reconstruction_v1',request=value.request,
        products=value.products,timezone=value.timezone,forecast_dates=value.forecast_dates,
        observations=tuple(o.model_dump(exclude={'available_at','source'}) for o in value.observations),**changes)


def test_raw_schema3_does_not_call_host_reconstruction(native,monkeypatch):
    value,*_=native
    import app.domain.forecasting.stockout as stockout
    def forbidden(*a,**k):raise AssertionError('Native boundary owns reconstruction')
    monkeypatch.setattr(stockout,'reconstruct',forbidden)
    p=prepared(value)
    assert raw_matches(p,value) and p.demand_records==()
    encoded=serialize_prepared(p)
    assert restore_prepared(json.loads(encoded.canonical_json),1,encoded.digest)==p


def test_legacy_v1_serialization_and_execution_metadata_exact(native):
    value,*_=native
    p=PreparedForecastInput(schema_version=1,request=value.request,products=value.products,timezone=value.timezone,
        forecast_dates=value.forecast_dates,observations=tuple(o.model_dump(exclude={'available_at','source','is_stockout'}) for o in value.observations))
    raw=p.model_dump(mode='json');raw.pop('demand_policy');raw.pop('demand_records')
    for row in raw['observations']:row.pop('is_stockout')
    for row,o in zip(raw['observations'],p.observations):row['quantity']=str(int(o.quantity))
    expected=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    assert serialize_prepared(p).canonical_json==expected
    assert serialize_prepared(p).digest==hashlib.sha256(PREFIX+expected.encode()).hexdigest()
    details=ExecutionDetails(selection_reason='BASELINE_SELECTED')
    assert details.model_dump(mode='json')==dict(schema_version=1,selection_reason='BASELINE_SELECTED',candidate_artifact_identity=None,
        postprocessing_version=1,raw_crossings=0,negative_values=0,warnings=[])


@pytest.mark.parametrize('change,code',[
    (lambda d:d.update(calendar=d['calendar'][:-1]),'CALENDAR_COVERAGE'),
    (lambda d:d['calendar'][0].update(closed=None),'INVALID_CHALLENGER_INPUT'),
    (lambda d:d.update(observations=[]),'PRODUCT_HISTORY_MISSING'),
    (lambda d:d['observations'][0].update(selling_unit='foreign'),'INVALID_CANONICAL_CAPTURE'),
    (lambda d:d['observations'][0].update(store_id=UUID(int=999)),'INVALID_CANONICAL_CAPTURE'),
    (lambda d:d['observations'][0].update(product_id=UUID(int=999)),'INVALID_CANONICAL_CAPTURE'),
    (lambda d:d.update(schema_version=2),'INVALID_CHALLENGER_INPUT'),
    (lambda d:d['calendar'][0].update(store_id=UUID(int=999)),'FOREIGN_CALENDAR'),
    (lambda d:d.update(mode='production'),'ARTIFACT_NOT_PRODUCTION_ELIGIBLE'),
])
def test_missing_unknown_foreign_and_production_rejected(native,change,code):
    value,storage,service,output=native
    data=value.model_dump(mode='python');change(data)
    with pytest.raises(ChallengerError) as caught:service._admit(data)
    assert caught.value.code==code


@pytest.mark.parametrize('field,value',[('p25','NaN'),('p50','Infinity'),('p25','999999'),('product_id',UUID(int=999))])
def test_bad_output_fails_validation(native,field,value):
    original,_,_,output=native
    raw=output.model_dump(mode='python');raw['forecast']['predictions'][0][field]=value
    with pytest.raises((ChallengerError,ValidationError)):
        validate_output(original,ChallengerOutput.model_validate(raw))


@pytest.mark.parametrize('category,code',[
    ('DATA_BLOCKED','CHALLENGER_DATA_BLOCKED'),('DEPENDENCY_MISMATCH','CHALLENGER_RUNTIME_UNAVAILABLE'),
    ('ARTIFACT_CORRUPTION','CHALLENGER_ARTIFACT_CORRUPT'),('TECHNICAL_FAILURE','CHALLENGER_TECHNICAL_FAILURE')])
def test_safe_reason_categories(category,code):
    assert safe_failure(ChallengerError(ChallengerFailure(category),'PRIVATE_INTERNAL_DETAIL')).code==code


def test_disabled_and_native_dependency_and_bug_never_fallback(native,monkeypatch):
    value,storage,service,_=native
    with pytest.raises(ChallengerError,match='CHALLENGER_DISABLED'):ForecastChallenger(storage).execute(value)
    import app.application.use_cases.forecast_challenger as module
    _,runtime,bundle,_=service._admit(value)
    for error,category in [(ImportError('missing'),ChallengerFailure.DEPENDENCY_MISMATCH),
                           (RuntimeError('bug'),ChallengerFailure.TECHNICAL_FAILURE)]:
        def fault(*a,**k):raise error
        monkeypatch.setattr(module,'infer_native',fault)
        with pytest.raises(ChallengerError) as caught:service._compute(value,bundle,runtime)
        assert caught.value.category==category


def test_artifact_bytes_changed_rejected(native,tmp_path):
    value,storage,service,_=native
    import shutil
    target=tmp_path/'clone';shutil.copytree(storage.root,target)
    clone=ChallengerStorage(target)
    bundle=clone.load_artifact(value.artifact_identity)
    (bundle.directory/'model_q25.txt').write_bytes(b'corrupt synthetic test copy')
    with pytest.raises(ChallengerError) as caught:ForecastChallenger(clone,enabled=True)._admit(value)
    assert caught.value.category==ChallengerFailure.ARTIFACT_CORRUPTION


@pytest.mark.parametrize('purpose',['research_candidate','production'])
def test_test_pin_does_not_admit_other_artifact_purposes(native,purpose):
    from app.application.contracts.planning_challenger import ChallengerTestPin
    value,storage,service,output=native
    data=output.artifact.model_dump(mode='python');data['purpose']=purpose
    with pytest.raises(ValidationError,match='unpromoted synthetic'):
        ChallengerTestPin(input=value,artifact=data,runtime=output.runtime,integration_code_digest='1'*64)


def test_artifact_runtime_mismatch_is_not_fallback(native,tmp_path):
    from app.application.contracts.forecast_challenger import ChallengerArtifact
    value,storage,service,output=native
    bundle=storage.load_artifact(value.artifact_identity)
    raw=bundle.manifest.model_dump(mode='python');raw['runtime']['adapter_code_digest']='0'*64
    manifest=ChallengerArtifact.model_validate(raw)
    target=ChallengerStorage(tmp_path/'mismatch')
    identity=target.publish_artifact(manifest,{f.name:(bundle.directory/f.name).read_bytes() for f in manifest.files})
    changed=ChallengerInput.model_validate(value.model_dump()|dict(artifact_identity=identity))
    with pytest.raises(ChallengerError,match='ARTIFACT_RUNTIME_MISMATCH'):
        ForecastChallenger(target,enabled=True)._admit(changed)


def test_host_baseline_and_retained_lightgbm_without_challenger_package(monkeypatch,tmp_path):
    """One frozen host inference regression, not a benchmark execution or fit."""
    import sys
    import lightgbm as lgb
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.infrastructure.forecast_model import QuantileModel,predict_quantiles
    from app.application.forecast_challenger_serialization import challenger_digest
    from app.application.use_cases.forecast_serving import ForecastServing
    from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
    from tests.unit.test_forecast_eligibility import serving
    from scripts.forecast_demo import synthetic_input
    def forbidden(*a,**k):raise AssertionError('Host must neither fit nor call C')
    monkeypatch.setattr(lgb,'train',forbidden)
    monkeypatch.setattr(ForecastChallenger,'_admit',forbidden)
    for name in tuple(sys.modules):
        if name=='shelfcash_forecast' or name.startswith('shelfcash_forecast.'):
            monkeypatch.delitem(sys.modules,name)
    monkeypatch.setitem(sys.modules,'shelfcash_forecast',None)
    host=ForecastServing(None,ForecastArtifactStore(tmp_path))
    baseline=synthetic_input(1,1)
    chosen=host.choice(baseline,serving('BASELINE'))
    assert host.execution._compute(baseline,chosen).result.model_type=='historical_quantile_baseline'
    root=Path('runtime/challenger/benchmarks')
    directory=root/'fits/12aceff4a568a50967aa253ead93d37a67b244b746f430b0da4af133a89bd0ad'
    store=BenchmarkStorage(root)
    retained=store.load(directory,'host-model.json');checkpoint=store.load(directory,'checkpoint.json')
    assert retained is not None and checkpoint['status']=='COMPLETED'
    capture=restore_prepared(retained['prepared'],1,retained['input_digest'])
    assert challenger_digest('host-artifact',retained['files'])==checkpoint['artifact_identity']
    boosters=tuple(lgb.Booster(model_str=retained['files'][f'p{q}.txt']) for q in (25,50,75))
    output,_,_=predict_quantiles(QuantileModel(capture,boosters),capture)
    expected={(UUID(r['product_id']),r['target_date']):(r['p25'],r['p50'],r['p75']) for r in checkpoint['predictions']}
    assert len(output.predictions)==14
    from decimal import Decimal
    assert all((p.p25,p.p50,p.p75)==tuple(Decimal(v) for v in expected[p.product_id,str(p.forecast_date)]) for p in output.predictions)
    out=Path('runtime/challenger/f4/acceptance');out.mkdir(parents=True,exist_ok=True)
    (out/'host-native.json').write_text(json.dumps(dict(status='PASS',native_host_predictions=14,fits=0,
        challenger_package_import_blocked=True,retained_input_sha256=hashlib.sha256((directory/'host-model.json').read_bytes()).hexdigest(),
        source_path=directory.as_posix(),scope='Single frozen host model inference equality, not a benchmark rerun or full host persistence acceptance.')))
