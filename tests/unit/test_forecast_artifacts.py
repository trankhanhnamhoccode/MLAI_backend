import json
from pathlib import Path

import pytest

from app.application.use_cases.forecast_evaluation import backtest
from app.infrastructure.forecast_model import train_quantiles, predict_quantiles
from app.infrastructure.storage.forecast_artifacts import (
    ForecastArtifactStore, ArtifactError, ArtifactMissingError, _identity,
)
from scripts.forecast_demo import synthetic_input


@pytest.fixture
def artifact(tmp_path):
    prepared = synthetic_input(80,1)
    store = ForecastArtifactStore(tmp_path/'artifacts')
    report = backtest(prepared,'SYNTHETIC')
    model = train_quantiles(prepared)
    identity = store.publish(model,report)
    return store,identity,prepared,model,report


def test_artifact_is_immutable_repeatable_and_load_replays_exactly(artifact):
    store,identity,prepared,model,report = artifact
    before = {p.name:p.read_bytes() for p in (store.root/identity).iterdir()}
    assert store.publish(model,report) == identity
    assert {p.name:p.read_bytes() for p in (store.root/identity).iterdir()} == before
    loaded = store.load(identity)
    assert predict_quantiles(loaded.model,prepared,identity) == predict_quantiles(model,prepared,identity)
    assert loaded.manifest.training_fingerprint == report.input_fingerprint


@pytest.mark.parametrize('name', ['manifest.json','p25.txt','p50.txt','p75.txt'])
def test_hash_corruption_is_error(artifact,name):
    store,identity,*_ = artifact
    path = store.root/identity/name
    path.write_bytes(path.read_bytes()+b'corrupt')
    with pytest.raises(ArtifactError):
        store.load(identity)


def test_missing_vs_invalid_key(artifact):
    store,_,*_ = artifact
    with pytest.raises(ArtifactMissingError):
        store.load('0'*64)
    with pytest.raises(ArtifactError,match='INVALID_ARTIFACT_IDENTITY'):
        store.load('../outside')


def test_version_incompatible_even_with_rehashed_manifest(artifact):
    store,identity,*_ = artifact
    path = store.root/identity/'manifest.json'
    payload = json.loads(path.read_bytes())
    payload['feature_version'] = 2
    data = json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    new_identity = _identity(data)
    directory = store.root/identity
    directory.rename(store.root/new_identity)
    (store.root/new_identity/'manifest.json').write_bytes(data)
    with pytest.raises(ArtifactError,match='ARTIFACT_INVALID_OR_INCOMPATIBLE'):
        store.load(new_identity)


def test_failed_publish_never_leaves_readable_partial_directory(tmp_path,monkeypatch):
    import app.infrastructure.storage.forecast_artifacts as module
    store = ForecastArtifactStore(tmp_path/'artifacts')
    prepared = synthetic_input(50,1)
    report = backtest(prepared,'SYNTHETIC')
    def reject(*args):
        raise OSError('injected rename failure')
    monkeypatch.setattr(module.os,'rename',reject)
    with pytest.raises(ArtifactError,match='ARTIFACT_PUBLICATION_FAILED'):
        store.publish(train_quantiles(prepared),report)
    assert not list(store.root.iterdir())


def test_invalid_model_text_with_matching_hash_fails_load(artifact):
    import hashlib
    store,identity,*_ = artifact
    payload = json.loads((store.root/identity/'manifest.json').read_bytes())
    payload['files'][0]['digest'] = hashlib.sha256(b'not a LightGBM model').hexdigest()
    data = json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    new_identity = _identity(data)
    (store.root/identity).rename(store.root/new_identity)
    (store.root/new_identity/'manifest.json').write_bytes(data)
    (store.root/new_identity/'p25.txt').write_bytes(b'not a LightGBM model')
    with pytest.raises(ArtifactError):
        store.load(new_identity)


def test_failed_file_flush_keeps_no_readable_artifact(tmp_path,monkeypatch):
    import app.infrastructure.storage.forecast_artifacts as module
    store = ForecastArtifactStore(tmp_path/'artifacts')
    prepared = synthetic_input(50,1)
    def reject(*args):
        raise OSError('injected write/flush failure')
    monkeypatch.setattr(module.os,'fsync',reject)
    with pytest.raises(ArtifactError,match='ARTIFACT_PUBLICATION_FAILED'):
        store.publish(train_quantiles(prepared),backtest(prepared,'SYNTHETIC'))
    assert not list(store.root.iterdir())


def test_staging_cleanup_failure_does_not_mask_primary(tmp_path,monkeypatch):
    import app.infrastructure.storage.forecast_artifacts as module
    store = ForecastArtifactStore(tmp_path/'artifacts')
    prepared = synthetic_input(50,1)
    def reject_rename(*args):
        raise OSError('publication primary')
    def reject_cleanup(*args):
        raise ValueError('cleanup secondary')
    monkeypatch.setattr(module.os,'rename',reject_rename)
    monkeypatch.setattr(module.shutil,'rmtree',reject_cleanup)
    with pytest.raises(ArtifactError,match='ARTIFACT_PUBLICATION_FAILED') as error:
        store.publish(train_quantiles(prepared),backtest(prepared,'SYNTHETIC'))
    assert isinstance(error.value.__cause__,OSError)
    assert any('cleanup' in note for note in error.value.__notes__)
    assert all(p.name.startswith('.pending-') for p in store.root.iterdir())
