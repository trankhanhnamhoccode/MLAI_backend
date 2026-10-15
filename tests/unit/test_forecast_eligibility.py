"""Choice/assessment parity, recognized-only fallback and scoped history blockers."""
import platform
import pytest
from pydantic import ValidationError

from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.contracts.model_serving import ServingPolicy, ServingRecord
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_serving import ForecastServing
from app.domain.forecasting.baseline import BaselineNotReadyError
from app.infrastructure.forecast_model import ModelBoundaryError
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore, ArtifactError
from scripts.forecast_demo import synthetic_input
from tests.unit.test_forecast_artifacts import artifact


def serving(mode='TRAINED', candidate=None):
    return ServingRecord(version='synthetic-d2', policy=ServingPolicy(mode=mode,
        artifact_identity=candidate, fallback_policy='ADR015_RECOGNIZED_ONLY',
        dependency_versions=(('baseline', '1'), ('serialization', '1'),
                             ('python', platform.python_version())) if mode=='BASELINE' else ()))


@pytest.mark.parametrize('candidate,reason', [(None, 'NO_ARTIFACT'), ('a'*64, 'ARTIFACT_MISSING')])
def test_recognized_absence_uses_same_choice_and_truthful_metadata(tmp_path, candidate, reason):
    service = ForecastServing(None, ForecastArtifactStore(tmp_path))
    prepared = synthetic_input(1, 1)
    record = serving(candidate=candidate)
    choice = service.choice(prepared, record)
    assessment = service.assess(prepared, record)
    assert assessment.can_execute and assessment.execution == choice.details
    assert assessment.execution.selection_reason == reason
    assert assessment.candidate_artifact_identity == candidate
    assert assessment.actual_model_type == 'historical_quantile_baseline'
    assert assessment.artifact_identity is None
    assert [w.code for w in assessment.warnings] == ['BASELINE_FALLBACK']


@pytest.mark.parametrize('count', [1, 28, 80])
def test_trained_history_and_selection_parity_without_assessment_inference(artifact, monkeypatch, count):
    store, identity, prepared, _, _ = artifact
    service = ForecastServing(None, store)
    def forbidden(*args, **kwargs):
        pytest.fail('Assessment must not train/infer/compute')
    import app.infrastructure.forecast_model as model
    monkeypatch.setattr(model.lgb.Booster, 'predict', forbidden)
    monkeypatch.setattr(model.lgb, 'train', forbidden)
    monkeypatch.setattr(service.execution, '_compute', forbidden)
    # Keep artifact scope/units/window compatibility, shorten only inference history.
    data = prepared.model_dump()
    rows = prepared.observations[-count:]
    data.update(observations=rows, request=prepared.request.model_dump() | {
        'history_start_date': rows[0].sales_date})
    prepared = PreparedForecastInput.model_validate(data)
    record = serving(candidate=identity)
    choice = service.choice(prepared, record)
    assessment = service.assess(prepared, record)
    assert assessment.can_execute and assessment.execution == choice.details
    if count < 80:
        assert choice.artifact is None and assessment.execution.selection_reason == 'NOT_READY_HISTORY'
    else:
        assert assessment.actual_model_type == ('lightgbm_quantile' if choice.artifact else 'historical_quantile_baseline')


@pytest.mark.parametrize('mode', ['BASELINE', 'TRAINED'])
@pytest.mark.parametrize('kind', ['missing', 'censored'])
def test_every_unusable_product_blocks_choice_with_scoped_assessment(tmp_path, mode, kind):
    service = ForecastServing(None, ForecastArtifactStore(tmp_path))
    original = synthetic_input(1, 2)
    data = original.model_dump()
    data.update(schema_version=2, demand_policy='causal_stockout_v1',
        observations=tuple(o.model_dump() | {'is_stockout': True} for o in original.observations)
                     if kind=='censored' else ())
    prepared = PreparedForecastInput.model_validate(data)
    assessment = service.assess(prepared, serving(mode))
    assert not assessment.can_execute and assessment.actual_model_type is None
    assert assessment.execution is None and assessment.failure_kind == 'HISTORY_UNUSABLE'
    assert {b.entity_id for b in assessment.blockers} == set(original.request.product_ids)
    assert {b.code for b in assessment.blockers} == {
        'CENSORED_HISTORY_NOT_USABLE' if kind=='censored' else 'PRODUCT_HISTORY_MISSING'}
    with pytest.raises(BaselineNotReadyError):
        service.choice(prepared, serving(mode))


def test_stockout_projection_preserves_observations_and_causal_support(tmp_path):
    service = ForecastServing(None, ForecastArtifactStore(tmp_path))
    original = synthetic_input(5, 1)
    data = original.model_dump()
    flags = (False, False, False, True, None)
    data.update(schema_version=2, demand_policy='causal_stockout_v1',
        observations=tuple(o.model_dump() | {'is_stockout': flag}
                           for o, flag in zip(original.observations, flags)))
    prepared = PreparedForecastInput.model_validate(data)
    before = serialize_prepared(prepared)
    assessment = service.assess(prepared, serving('BASELINE'))
    expected = service.execution._compute(prepared, service.choice(prepared, serving('BASELINE')))
    assert set(assessment.warnings) == set(expected.details.warnings)
    assert {w.code for w in assessment.warnings} == {'STOCKOUT_UNKNOWN', 'DEMAND_RECONSTRUCTED'}
    assert serialize_prepared(prepared) == before
    reconstructed = next(r for r in prepared.demand_records if r.method == 'PAST_MEDIAN')
    assert reconstructed.evidence_dates == tuple(o.sales_date for o in prepared.observations[:3])
    assert prepared.observations[-1].is_stockout is None


@pytest.mark.parametrize('kind', ['corrupt', 'incompatible', 'dependency', 'runtime'])
def test_artifact_and_dependency_failures_never_become_fallback(artifact, monkeypatch, kind):
    store, identity, prepared, _, _ = artifact
    service = ForecastServing(None, store)
    if kind == 'corrupt':
        (store.root / identity / 'p25.txt').write_bytes(b'corrupt')
    elif kind == 'incompatible':
        data = prepared.model_dump()
        # Existing observed schema-1 artifact cannot consume schema-2 demand policy.
        data.update(schema_version=2, demand_policy='causal_stockout_v1')
        prepared = PreparedForecastInput.model_validate(data)
    elif kind == 'dependency':
        import app.infrastructure.storage.forecast_artifacts as artifacts
        monkeypatch.setattr(artifacts.lgb, '__version__', 'incompatible-runtime')
    else:
        from pathlib import Path
        read_bytes = Path.read_bytes
        def unavailable(path):
            if path == store.root / identity / 'manifest.json':
                raise PermissionError('injected unavailable artifact storage')
            return read_bytes(path)
        monkeypatch.setattr(Path, 'read_bytes', unavailable)
    assessment = service.assess(prepared, serving(candidate=identity))
    assert not assessment.can_execute and assessment.execution is None
    assert assessment.actual_model_type is None
    assert assessment.failure_kind == ({'dependency':'DEPENDENCY_UNAVAILABLE',
        'runtime':'RUNTIME_UNAVAILABLE'}.get(kind,'ARTIFACT_INVALID'))
    assert assessment.blockers[0].code == ('EXECUTION_UNAVAILABLE' if kind in ('dependency','runtime') else 'MODEL_ARTIFACT_INVALID')
    assert 'BASELINE_FALLBACK' not in {w.code for w in assessment.warnings}
    with pytest.raises((ArtifactError, ModelBoundaryError)):
        service.choice(prepared, serving(candidate=identity))


@pytest.mark.parametrize('error', [RuntimeError('programming bug'), OSError('technical unavailable')])
def test_unexpected_failures_are_not_classified_as_missing_history(tmp_path, monkeypatch, error):
    service = ForecastServing(None, ForecastArtifactStore(tmp_path))
    def reject(*args):
        raise error
    monkeypatch.setattr(service.execution.artifacts, 'load', reject)
    with pytest.raises(type(error)):
        service.assess(synthetic_input(1, 1), serving(candidate='a'*64))


def test_invalid_capture_rejected_before_choice_not_sanitized_as_data_missing(tmp_path):
    service = ForecastServing(None, ForecastArtifactStore(tmp_path))
    prepared = synthetic_input(1, 1)
    data = prepared.model_dump()
    data['observations'] = (prepared.observations[0], prepared.observations[0])
    # Public Pydantic boundaries reject malformed input; choice also revalidates.
    invalid = prepared.model_copy(update={'observations': data['observations']})
    with pytest.raises(ValidationError):
        service.assess(invalid, serving())
