"""Native fixture admission/replay plus explicitly mocked failure boundaries; no DB."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.application.contracts.forecast_challenger import (
    ArtifactFile, ChallengerArtifact, ChallengerError, ChallengerFailure as Failure,
    ChallengerInput, ChallengerOutput,
)
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.forecast_challenger_validation import admit_input, validate_output
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.forecast_challenger_native import infer_native
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from tests.fixtures.forecast_engine.native_setup import create_native_fixture


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    root = tmp_path_factory.mktemp('challenger_native')
    value = create_native_fixture(root)
    storage = ChallengerStorage(root)
    service = ForecastChallenger(storage, enabled=True)
    result = service.execute(value)
    return root, value, storage, service, result


def change_input(value, change):
    data = value.model_dump(mode='python')
    change(data)
    return data


def reject(service, data, category, code):
    with pytest.raises(ChallengerError) as caught:
        service.execute(data)
    assert (caught.value.category, caught.value.code) == (category, code)


def variant(native, *, fields=None, native_change=None):
    _, value, storage, _, _ = native
    old = storage.load_artifact(value.artifact_identity)
    files = {f.name: (old.directory / f.name).read_bytes() for f in old.manifest.files}
    data = old.manifest.model_dump(mode='python')
    if fields:
        data.update(fields)
    if native_change:
        name, mutate = native_change
        payload = json.loads(files[name])
        mutate(payload)
        files[name] = canonical_bytes(payload)
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in files.items() if n != 'artifact_checksums.json'}
    files['artifact_checksums.json'] = canonical_bytes({'algorithm': 'sha256', 'files': hashes})
    data.update(files=tuple(ArtifactFile(name=n, digest=hashlib.sha256(b).hexdigest()) for n, b in files.items()),
        config_digest=hashes['preprocessing_config.json'], feature_digest=hashes['feature_schema.json'],
        postprocess_digest=challenger_digest('postprocess', {'point': hashes['point_corrector.json'],
            'cqr': hashes['calibrator.json'], 'policy': 'native_stack_weather_excluded/1'}))
    manifest = ChallengerArtifact.model_validate(data)
    identity = storage.publish_artifact(manifest, files)
    values = value.model_dump(mode='python')
    values['artifact_identity'] = identity
    return ChallengerInput.model_validate(values)


def test_native_stage_result_and_canonical_reconstruction(native):
    _, value, _, _, result = native
    output = result.evidence.output
    assert result.reused is False
    assert len(output.forecast.predictions) == 14
    assert output.forecast.model_type == 'forecast_engine_challenger'
    assert output.artifact.purpose == 'synthetic_correctness'
    assert output.artifact.production_available_at is None
    assert output.input_digest == challenger_digest('input', value)
    pid = value.request.product_ids[0]
    records = {r.day: r for r in output.reconstruction if r.product_id == pid}
    first = value.request.history_start_date
    assert records[first].stockout is True and records[first].observed_sales == 0
    assert not records[first].applied and records[first].feature_demand is None
    assert records[first + timedelta(days=1)].observed_sales == 0
    assert records[first + timedelta(days=2)].stockout is None
    assert records[first + timedelta(days=2)].feature_demand == 10
    assert not records[first + timedelta(days=6)].row_observed
    assert records[first + timedelta(days=6)].observed_sales is None
    reconstructed = records[first + timedelta(days=43)]
    assert reconstructed.observed_sales == 2 and reconstructed.demand_proxy == 10
    assert reconstructed.applied and reconstructed.latest_reference < reconstructed.day
    assert next(o for o in value.observations if o.product_id == pid and
                o.sales_date == reconstructed.day).quantity == 2


def test_quantile_crossing_repair_and_cqr_are_separate_native(native):
    _, value, _, _, result = native
    output = result.evidence.output
    prediction = output.forecast.predictions[0]
    interval, diagnostic = output.cqr[0], output.native_predictions[0]
    assert diagnostic.raw_crossing and diagnostic.model_raw == (Decimal('2'), Decimal('0'), Decimal('-2'))
    assert diagnostic.quantity_raw[0] > diagnostic.quantity_raw[2]
    assert diagnostic.repaired[0] <= diagnostic.repaired[1] <= diagnostic.repaired[2]
    assert prediction.p25 == diagnostic.repaired[0] + diagnostic.point_offset
    assert interval.lower < prediction.p25 < prediction.p50 < prediction.p75 < interval.upper
    assert diagnostic.point_offset == 1 and interval.correction == 2
    last = [p for p in output.forecast.predictions if p.forecast_date == value.forecast_dates[-1]]
    assert all(p.p25 == p.p50 == p.p75 == 0 for p in last)


def test_native_matches_pinned_public_predict_demand(native):
    """Independent public-stage caller equivalence for the composed adapter path."""
    import pandas as pd
    from shelfcash_forecast.pipeline.inference_pipeline import predict_demand
    _, value, storage, _, result = native
    bundle = storage.load_artifact(value.artifact_identity)
    sales = pd.DataFrame([{'date': str(o.sales_date), 'store_id': str(o.store_id),
        'product_id': str(o.product_id), 'product_name': str(o.product_id),
        'quantity_sold': float(o.quantity), 'unit': o.selling_unit, 'is_stockout': o.is_stockout}
        for o in value.observations])
    calendar = pd.DataFrame([{'date': str(c.day), 'is_store_closed': c.closed, 'is_holiday': c.holiday}
                             for c in value.calendar])
    package = predict_demand({'sales_history': sales, 'calendar_features': calendar}, bundle.directory,
                            str(value.request.cutoff_date), 7, execution_mode='backtest_replay')
    expected = {(str(p.product_id), p.forecast_date): p for p in result.evidence.output.forecast.predictions}
    intervals = {(str(p.product_id), p.forecast_date): p for p in result.evidence.output.cqr}
    for row in package.predictions:
        p = expected[row.product_id, row.target_date]
        assert (p.p25, p.p50, p.p75) == tuple(Decimal(str(v)) for v in (row.p25, row.p50, row.p75))
        interval = intervals[row.product_id, row.target_date]
        assert (interval.lower, interval.upper) == (Decimal(str(row.interval_lower)), Decimal(str(row.interval_upper)))


@pytest.mark.parametrize('change,category,code', [
    (lambda d: d.update(quantity_basis='be_reconstructed_demand'), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d.update(reconstruction_policy='causal_stockout_v1'), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d.update(demand_records=[]), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d['observations'][0].update(store_id='00000000-0000-0000-0000-000000000002'), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d['observations'][0].update(product_id='00000000-0000-0000-0000-000000000099'), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d['observations'][0].update(selling_unit='kg'), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d['observations'][0].update(is_stockout=0), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d.update(observations=d['observations'] + (d['observations'][0],)), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d.update(forecast_dates=d['forecast_dates'][:-1]), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d.update(calendar=d['calendar'][:-1]), Failure.DATA_BLOCKED, 'CALENDAR_COVERAGE'),
    (lambda d: d['calendar'][0].update(closed=None), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d['calendar'][0].update(source=''), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d['calendar'][3].update(closed=True), Failure.DATA_BLOCKED, 'CLOSED_DAY_OBSERVATION_CONFLICT'),
    (lambda d: d['calendar'][0].update(available_at=d['inference_at']+timedelta(days=1)), Failure.DATA_BLOCKED, 'CALENDAR_NOT_AVAILABLE'),
    (lambda d: d['observations'][0].update(available_at=d['inference_at']+timedelta(days=1)), Failure.DATA_BLOCKED, 'OBSERVATION_NOT_AVAILABLE'),
    (lambda d: d['observations'][0].update(sales_date=d['request']['cutoff_date']+timedelta(days=1)), Failure.UNSUPPORTED, 'INVALID_CANONICAL_CAPTURE'),
    (lambda d: d.update(weather=[{'kind': 'forecast'}]), Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT'),
    (lambda d: d.update(mode='production'), Failure.DATA_BLOCKED, 'ARTIFACT_NOT_PRODUCTION_ELIGIBLE'),
])
def test_detached_admission_guards(native, change, category, code):
    _, value, _, service, _ = native
    reject(service, change_input(value, change), category, code)


@pytest.mark.parametrize('component', ['training', 'point_fit', 'calibration'])
def test_future_artifact_labels_block_before_native(native, component):
    _, value, storage, service, _ = native
    a = storage.load_artifact(value.artifact_identity).manifest
    window = getattr(a, component).model_dump(mode='python')
    window['end'] = value.request.cutoff_date + timedelta(days=1)
    reject(service, variant(native, fields={component: window}), Failure.DATA_BLOCKED, 'ARTIFACT_LABELS_NOT_AVAILABLE')


def test_artifact_publication_after_inference_is_blocked(native):
    _, value, _, service, _ = native
    reject(service, variant(native, fields={'available_at': value.inference_at+timedelta(seconds=1)}),
           Failure.DATA_BLOCKED, 'ARTIFACT_NOT_AVAILABLE')


@pytest.mark.parametrize('change,category,code', [
    (('feature_schema.json', lambda d: d.update(schema_version='2.0')), Failure.UNSUPPORTED, 'FEATURE_SCHEMA_UNSUPPORTED'),
    (('feature_schema.json', lambda d: d['features'].pop()), Failure.UNSUPPORTED, 'FEATURE_SCHEMA_UNSUPPORTED'),
    (('category_mappings.json', lambda d: d['product_key'].update({'foreign': 99})), Failure.UNSUPPORTED, 'CATEGORY_SCOPE_MISMATCH'),
    (('model_metadata.json', lambda d: d['runtime_versions'].update(lightgbm_version='4.7.0')), Failure.DEPENDENCY_MISMATCH, 'NATIVE_DEPENDENCY_MISMATCH'),
    (('point_corrector.json', lambda d: d.update(model_id='unrelated')), Failure.ARTIFACT_CORRUPTION, 'POSTPROCESS_BINDING_MISMATCH'),
    (('calibrator.json', lambda d: d.update(semantics_version='old_cqr')), Failure.ARTIFACT_CORRUPTION, 'POSTPROCESS_BINDING_MISMATCH'),
])
def test_pinned_but_incompatible_native_manifest(native, change, category, code):
    _, _, _, service, _ = native
    reject(service, variant(native, native_change=change), category, code)


def test_missing_and_corrupt_bytes_never_fallback_or_reuse(native, tmp_path):
    root, value, _, _, _ = native
    target = tmp_path / 'copy'
    shutil.copytree(root, target)
    service = ForecastChallenger(ChallengerStorage(target), enabled=True)
    path = target / 'artifacts' / value.artifact_identity / 'model_q25.txt'
    original = path.read_bytes()
    path.write_bytes(original + b'corrupt')
    reject(service, value, Failure.ARTIFACT_CORRUPTION, 'ARTIFACT_CHECKSUM_MISMATCH')
    path.unlink()  # only this disposable fixture copy
    reject(service, value, Failure.ARTIFACT_CORRUPTION, 'ARTIFACT_FILE_SET')
    data = change_input(value, lambda d: d.update(artifact_identity='0'*64))
    reject(service, data, Failure.TECHNICAL_FAILURE, 'PINNED_ARTIFACT_MISSING')


def test_raw_unknown_zero_and_missing_do_not_need_fake_stockout(native):
    _, value, storage, _, _ = native
    data = value.model_dump(mode='python')
    for row in data['observations']:
        row['is_stockout'] = None
    unknown = ChallengerInput.model_validate(data)
    output = infer_native(unknown, storage.load_artifact(value.artifact_identity), current_runtime())
    assert 'STOCKOUT_INFORMATION_MISSING' in output.warnings
    assert all(r.stockout is None for r in output.reconstruction)
    assert all(not r.applied for r in output.reconstruction)


def test_off_has_no_engine_import_db_or_host_mutation(native, monkeypatch):
    _, value, storage, _, _ = native
    def unexpected():
        raise AssertionError('OFF must stop before runtime/native/filesystem work')
    monkeypatch.setattr('app.application.use_cases.forecast_challenger.current_runtime', unexpected)
    reject(ForecastChallenger(storage), value, Failure.UNSUPPORTED, 'CHALLENGER_DISABLED')
    # Host composition never imports/constructs the new adapter.
    source = (Path(__file__).resolve().parents[2] / 'app/main.py').read_text(encoding='utf-8')
    assert 'forecast_challenger' not in source


def test_cache_identity_scope_facts_artifact_and_decimal_equivalence(native):
    _, value, _, service, result = native
    assert service.execute(value).reused
    original = challenger_digest('input', value)
    scaled = value.model_dump(mode='python')
    scaled['observations'][1]['quantity'] = Decimal('0.000')
    assert challenger_digest('input', ChallengerInput.model_validate(scaled)) == original
    for field, change in [
        ('stockout', lambda d: d['observations'][2].update(is_stockout=None)),
        ('calendar', lambda d: d['calendar'][3].update(holiday=True)),
        ('artifact', lambda d: d.update(artifact_identity='0'*64)),
        ('quantity', lambda d: d['observations'][2].update(quantity='20')),
    ]:
        changed = ChallengerInput.model_validate(change_input(value, change))
        assert challenger_digest('input', changed) != original, field
    before = canonical_bytes(value)
    assert canonical_bytes(service.replay(result.evidence.cache_identity).evidence.input) == before


def test_fresh_process_replays_exact_retained_bytes_without_live_input(native):
    root, _, _, _, result = native
    code = "from pathlib import Path; from app.application.use_cases.forecast_challenger import ForecastChallenger; from app.infrastructure.storage.forecast_challenger import ChallengerStorage; import sys; r=ForecastChallenger(ChallengerStorage(Path(sys.argv[1])),enabled=True).replay(sys.argv[2]); print(r.evidence.cache_identity)"
    output = subprocess.run([sys.executable, '-c', code, str(root), result.evidence.cache_identity],
                            capture_output=True, text=True, check=True)
    assert output.stdout.strip() == result.evidence.cache_identity


def test_retained_corruption_is_detected_and_never_rewritten(native, tmp_path):
    root, value, _, _, result = native
    target = tmp_path / 'copy'
    shutil.copytree(root, target)
    path = target / 'runs' / result.evidence.cache_identity / 'evidence.json'
    raw = path.read_bytes()
    path.write_bytes(raw + b' ')
    corrupt = path.read_bytes()
    service = ForecastChallenger(ChallengerStorage(target), enabled=True)
    reject(service, value, Failure.ARTIFACT_CORRUPTION, 'EVIDENCE_DIGEST_MISMATCH')
    assert path.read_bytes() == corrupt


def test_mocked_runtime_mismatch_blocks_replay(native, monkeypatch):
    _, value, _, service, result = native
    current = current_runtime()
    altered = current.model_copy(update={'python': '0.0.0'})
    monkeypatch.setattr('app.application.use_cases.forecast_challenger.current_runtime', lambda: altered)
    reject(service, value, Failure.DEPENDENCY_MISMATCH, 'ARTIFACT_RUNTIME_MISMATCH')
    with pytest.raises(ChallengerError, match='ARTIFACT_RUNTIME_MISMATCH'):
        service.replay(result.evidence.cache_identity)


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_mocked_nonfinite_raw_native_cannot_be_repaired_into_success(native, monkeypatch, bad):
    _, value, storage, _, _ = native
    from shelfcash_forecast.models.predictor import predict_raw_quantiles
    def faulty(*args):
        frame = predict_raw_quantiles(*args)
        frame['model_q25_raw'] = bad
        return frame
    monkeypatch.setattr('shelfcash_forecast.models.predictor.predict_raw_quantiles', faulty)
    with pytest.raises(ChallengerError, match='NONFINITE_NATIVE_VALUE'):
        infer_native(value, storage.load_artifact(value.artifact_identity), current_runtime())


@pytest.mark.parametrize('field,bad', [('p25', '-1'), ('p25', '999'), ('p50', 'NaN')])
def test_final_negative_crossing_nonfinite_output_rejected(native, field, bad):
    _, value, _, _, result = native
    data = result.evidence.output.model_dump(mode='python')
    data['forecast']['predictions'][0][field] = bad
    with pytest.raises(ValidationError):
        ChallengerOutput.model_validate(data)


def test_missing_output_coverage_rejected(native):
    _, value, _, _, result = native
    data = result.evidence.output.model_dump(mode='python')
    data['forecast']['predictions'] = data['forecast']['predictions'][:-1]
    with pytest.raises(ChallengerError, match='NATIVE_OUTPUT_COVERAGE'):
        validate_output(value, ChallengerOutput.model_validate(data))


@pytest.mark.parametrize('field,value_', [('store_id', '00000000-0000-0000-0000-000000000002'),
                                       ('unit', 'kg')])
def test_mocked_native_output_scope_and_unit_reject(native, monkeypatch, field, value_):
    _, value, storage, _, _ = native
    from shelfcash_forecast.pipeline.inference_pipeline import build_forecast_package
    def faulty(*args):
        package = build_forecast_package(*args)
        package.predictions[0] = package.predictions[0].model_copy(update={field: value_})
        return package
    monkeypatch.setattr('shelfcash_forecast.pipeline.inference_pipeline.build_forecast_package', faulty)
    with pytest.raises(ChallengerError, match='NATIVE_OUTPUT_SCOPE_OR_UNIT'):
        infer_native(value, storage.load_artifact(value.artifact_identity), current_runtime())


def test_modified_installed_dependency_pin_is_rejected(native, monkeypatch):
    import app.infrastructure.forecast_challenger_runtime as module
    actual = module.metadata.version
    monkeypatch.setattr(module.metadata, 'version',
                        lambda name: '99.0' if name == 'pandas' else actual(name))
    with pytest.raises(ChallengerError, match='DEPENDENCY_VERSION_MISMATCH'):
        current_runtime()


def test_store_scope_and_new_artifact_never_share_cache(native):
    _, value, _, service, result = native
    data = value.model_dump(mode='python')
    foreign = '00000000-0000-0000-0000-000000000002'
    data['request']['store_id'] = foreign
    for row in data['observations']:
        row['store_id'] = foreign
    for row in data['calendar']:
        row['store_id'] = foreign
    other = ChallengerInput.model_validate(data)
    assert challenger_digest('input', other) != result.evidence.output.input_digest
    reject(service, other, Failure.UNSUPPORTED, 'ARTIFACT_SCOPE_OR_UNIT_MISMATCH')
    modified = variant(native, native_change=('calibrator.json', lambda d: d['global_value'].update(correction=3)))
    rerun = service.execute(modified)
    assert not rerun.reused and rerun.evidence.cache_identity != result.evidence.cache_identity
    assert rerun.evidence.output.forecast.predictions == result.evidence.output.forecast.predictions
    assert rerun.evidence.output.cqr[0].lower != result.evidence.output.cqr[0].lower


def test_mocked_inference_error_is_not_baseline_fallback(native, monkeypatch):
    _, value, storage, _, _ = native
    def faulty(*args):
        raise ValueError('private native details must not be exposed')
    monkeypatch.setattr('shelfcash_forecast.models.predictor.predict_raw_quantiles', faulty)
    with pytest.raises(ChallengerError) as caught:
        infer_native(value, storage.load_artifact(value.artifact_identity), current_runtime())
    assert str(caught.value) == 'NATIVE_INFERENCE_FAILED'
    assert caught.value.category == Failure.TECHNICAL_FAILURE


def test_research_exposure_cannot_be_promoted_by_metadata(native):
    _, _, _, service, _ = native
    reject(service, variant(native, fields={'purpose': 'research_candidate', 'holdout_status': 'EXPOSED',
                                           'promotion_status': 'promoted'}),
           Failure.DATA_BLOCKED, 'RESEARCH_PROMOTION_CONFLICT')


def test_input_numeric_scale_order_and_timezone_normalize_identity(native):
    from datetime import timezone
    _, value, _, _, _ = native
    changed = value.model_dump(mode='python')
    changed['observations'] = tuple(reversed(changed['observations']))
    changed['calendar'] = tuple(reversed(changed['calendar']))
    changed['products'] = tuple(reversed(changed['products']))
    changed['forecast_dates'] = tuple(reversed(changed['forecast_dates']))
    changed['inference_at'] = changed['inference_at'].astimezone(timezone(timedelta(hours=7)))
    changed['observations'][0]['quantity'] = Decimal('10.0000')
    assert challenger_digest('input', ChallengerInput.model_validate(changed)) == challenger_digest('input', value)


def test_reconstruction_lineage_and_coverage_reject_forged_evidence(native):
    _, value, _, _, result = native
    data = result.evidence.output.model_dump(mode='python')
    data['reconstruction'] = data['reconstruction'][:-1]
    with pytest.raises(ChallengerError, match='RECONSTRUCTION_COVERAGE'):
        validate_output(value, ChallengerOutput.model_validate(data))

    data = result.evidence.output.model_dump(mode='python')
    row = next(r for r in data['reconstruction'] if r['applied'])
    row['latest_reference'] = row['day']
    with pytest.raises(ChallengerError, match='RECONSTRUCTION_SUPPORT_LEAKAGE'):
        validate_output(value, ChallengerOutput.model_validate(data))


def test_off_fresh_process_does_not_import_native_or_operational_composition(tmp_path):
    code = "from pathlib import Path; import sys; from app.application.use_cases.forecast_challenger import ForecastChallenger; from app.infrastructure.storage.forecast_challenger import ChallengerStorage; from app.application.contracts.forecast_challenger import ChallengerError; s=ForecastChallenger(ChallengerStorage(Path(sys.argv[1])));\ntry: s.execute(None)\nexcept ChallengerError as e: assert e.code=='CHALLENGER_DISABLED'\nelse: raise AssertionError('must reject')\nassert not any(n in sys.modules for n in ('pandas','lightgbm','sqlalchemy','fastapi','app.main','openai')); print('OFF_ISOLATION_VERIFIED')"
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            check=True, text=True, capture_output=True)
    assert result.stdout.strip() == 'OFF_ISOLATION_VERIFIED'


@pytest.mark.parametrize('error,category,code', [
    (ImportError('private loader details'), Failure.DEPENDENCY_MISMATCH, 'NATIVE_DEPENDENCY_UNAVAILABLE'),
    (RuntimeError('private computation details'), Failure.TECHNICAL_FAILURE, 'NATIVE_TECHNICAL_FAILURE'),
])
def test_unexpected_native_failures_are_typed_not_success(native, monkeypatch, error, category, code):
    _, value, storage, _, _ = native
    def fail(*args):
        raise error
    monkeypatch.setattr('app.application.use_cases.forecast_challenger.infer_native', fail)
    with pytest.raises(ChallengerError) as caught:
        ForecastChallenger._compute(value, storage.load_artifact(value.artifact_identity), current_runtime())
    assert caught.value.category == category and caught.value.code == code


def test_existing_host_preparation_retains_schema2_raw_sales_and_sparse_dates(native):
    from app.application.forecast_preparation import prepare_observations
    from app.application.forecast_serialization import serialize_prepared, restore_prepared
    from app.repositories.readiness import ReadinessFacts
    _, value, _, _, _ = native
    snapshot = {'stores': [{'timezone': value.timezone}],
        'products': [{'id': str(p.product_id), 'selling_unit': p.selling_unit, 'active': True}
                     for p in value.products],
        'sales_daily': [{'product_id': str(o.product_id), 'sales_date': str(o.sales_date),
                         'quantity': str(o.quantity), 'is_stockout': o.is_stockout}
                        for o in value.observations]}
    snapshot['sales_daily'].append({'product_id': str(value.request.product_ids[0]),
        'sales_date': str(value.forecast_dates[0]), 'quantity': '999', 'is_stockout': False})
    facts = ReadinessFacts(snapshot=snapshot, defaults=None, cap=None, serving=None, saved=())
    prepared = prepare_observations(facts, value.request.store_id, value.forecast_dates[0],
                                    value.request.product_ids)
    assert prepared.schema_version == 2 and prepared.demand_policy == 'causal_stockout_v1'
    assert prepared.request.cutoff_date == value.request.cutoff_date
    assert len(prepared.observations) == len(value.observations)
    for left, right in zip(prepared.observations, value.observations, strict=True):
        assert (left.product_id, left.sales_date, left.quantity, left.is_stockout) == (
            right.product_id, right.sales_date, right.quantity, right.is_stockout)
    encoded = serialize_prepared(prepared)
    assert restore_prepared(json.loads(encoded.canonical_json), 1, encoded.digest) == prepared
