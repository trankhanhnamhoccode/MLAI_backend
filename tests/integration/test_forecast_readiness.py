"""D2 linked HTTP/PostgreSQL eligibility, using only portable synthetic facts."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_readiness_context import (
    readiness, config, env, configure_baseline, read,
)
from tests.integration.test_planning_configuration_public import base
from app.application.contracts.model_serving import ServingPolicy
from app.application.contracts.common import RunReferenceInput
from app.application.contracts.auth import AuthError
from app.models import SalesDaily, ForecastRun, PlanningRun, Product, Ingredient, Recipe, SupplierTerm, InventoryLot
from app.models.model_serving import ModelServingConfiguration
from app.models.forecast_run_input import ForecastRunInput


@pytest.mark.parametrize('endpoint', ['readiness', 'planning-context', 'today'])
def test_all_censored_trained_get_returns_scoped_blocker(readiness, endpoint):
    c = readiness
    configure_baseline(c)
    second = uuid4()
    with Session(c[0][1]) as session:
        row = session.get(ModelServingConfiguration, c[1].store_id)
        row.configuration_json = ServingPolicy(mode='TRAINED', artifact_identity=None,
            dependency_versions=(), fallback_policy='ADR015_RECOGNIZED_ONLY').model_dump(mode='json')
        session.add(SalesDaily(store_id=c[1].store_id, product_id=c[2],
            sales_date=date(2026, 10, 9), quantity=4, is_stockout=True))
        session.add(Product(id=second,store_id=c[1].store_id,name='Second censored',selling_unit='piece',active=True))
        session.flush()
        session.add(SalesDaily(store_id=c[1].store_id,product_id=second,
            sales_date=date(2026,10,9),quantity=4,is_stockout=True))
        session.commit()
    response = (read(c, 'forecast') if endpoint == 'readiness' else
                c[0][5].get(base(c) + '/today', params={'section': 'readiness'}) if endpoint == 'today'
                else c[0][5].get(base(c) + '/planning-context'))
    assert response.status_code == 200, response.text
    value = response.json()['data']
    if endpoint in ('readiness', 'today'):
        if endpoint == 'today':
            section = value['sections']['readiness']
            assert section['availability'] == 'available'
            value = section['value']
        action = next(a for a in value['actions'] if a['action'] == 'forecast')
        assert not action['can_execute'] and action['availability'] == 'blocked'
        assert {b['entity_id'] for b in action['blockers'] if b['scope']=='PRODUCT'
                and b['code']=='CENSORED_HISTORY_NOT_USABLE'} == {str(c[2]),str(second)}
    else:
        assert not value['readiness']['can_generate']
        assert 'CENSORED_HISTORY_NOT_USABLE' in value['readiness']['reason_codes']
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ForecastRun)) == 0
        assert fresh.scalar(select(func.count()).select_from(PlanningRun)) == 0
        sales = fresh.scalars(select(SalesDaily)).all()
        assert len(sales)==2 and all(s.quantity == 4 and s.is_stockout is True for s in sales)


def test_sales_only_sparse_zero_get_no_compute_then_retained_baseline(readiness, monkeypatch):
    c = readiness
    configure_baseline(c)
    service = c[0][5].app.state.forecast_serving
    with Session(c[0][1]) as session:
        session.add_all([SalesDaily(store_id=c[1].store_id, product_id=c[2],
            sales_date=day, quantity=quantity, is_stockout=None)
            for day, quantity in [(date(2026,10,6), 0), (date(2026,10,9), 4)]])
        session.commit()
    with monkeypatch.context() as guard:
        def forbidden(*args, **kwargs):
            pytest.fail('GET attempted training/inference/solver/persistence execution')
        import app.infrastructure.forecast_model as model
        import scipy.optimize
        guard.setattr(model.lgb, 'train', forbidden)
        guard.setattr(model.lgb.Booster, 'predict', forbidden)
        guard.setattr(scipy.optimize, 'milp', forbidden)
        guard.setattr(service, 'serve', forbidden)
        response = read(c, 'forecast')
        assert response.status_code == 200, response.text
        action = response.json()['data']['actions'][0]
        assert action['can_execute']
        assert 'STOCKOUT_UNKNOWN' in {w['code'] for w in action['warnings']}
        assert not any(w['source'] in ('recipe','inventory','supplier','fees') for w in action['warnings'])
    with Session(c[0][1]) as fresh:
        for table in (Ingredient, Recipe, SupplierTerm, InventoryLot, ForecastRun, PlanningRun):
            assert fresh.scalar(select(func.count()).select_from(table)) == 0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 2
    preparation = service.prepare(c[1].store_id, date(2026,10,10), (c[2],))
    assessment = service.assess(preparation.prepared, preparation.serving)
    served = service.serve(preparation)
    assert assessment.actual_model_type == served.run.model_type == 'historical_quantile_baseline'
    assert len(served.run.predictions) == 7
    assert {p.p50 for p in served.run.predictions} == {2}
    reference = RunReferenceInput(store_id=c[1].store_id, run_id=served.run.id)
    metadata = service.execution.get_with_metadata(reference).execution
    assert set(metadata.warnings) == set(assessment.warnings)
    replay = service.execution.replay(reference)
    with Session(c[0][1]) as fresh:
        retained = fresh.get(ForecastRunInput, served.run.id).prepared_json
        assert len(retained['observations']) == 2
        assert retained['observations'][0]['quantity'] == '0'
        assert all(o['is_stockout'] is None for o in retained['observations'])
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 2
        fresh.scalar(select(SalesDaily).order_by(SalesDaily.sales_date)).quantity = 999
        fresh.commit()
    assert service.execution.replay(reference) == replay


def test_explicit_product_without_history_not_silently_omitted(readiness):
    c = readiness
    configure_baseline(c)
    missing = uuid4()
    with Session(c[0][1]) as session:
        session.add(Product(id=missing,store_id=c[1].store_id,name='No history',selling_unit='piece',active=True))
        session.add(SalesDaily(store_id=c[1].store_id,product_id=c[2],sales_date=date(2026,10,9),quantity=0))
        session.commit()
    service = c[0][5].app.state.forecast_serving
    with pytest.raises(AuthError, match='PRODUCT_HISTORY_MISSING'):
        service.prepare(c[1].store_id, date(2026,10,10), (c[2],missing))
    assert service.prepare(c[1].store_id,date(2026,10,10),(c[2],)).prepared.request.product_ids == (c[2],)
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ForecastRun)) == 0


@pytest.mark.parametrize('kind', ['corrupt', 'dependency'])
def test_linked_get_distinguishes_artifact_invalid_from_dependency_unavailable(readiness, tmp_path, kind):
    c = readiness
    configure_baseline(c)
    service = c[0][5].app.state.forecast_serving
    from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
    service.execution.artifacts = ForecastArtifactStore(tmp_path)
    candidate = 'a'*64
    (tmp_path/candidate).mkdir()
    with Session(c[0][1]) as session:
        row = session.get(ModelServingConfiguration,c[1].store_id)
        row.configuration_json = ServingPolicy(mode='TRAINED' if kind=='corrupt' else 'BASELINE',
            artifact_identity=candidate if kind=='corrupt' else None, dependency_versions=(),
            fallback_policy='ADR015_RECOGNIZED_ONLY').model_dump(mode='json')
        session.add(SalesDaily(store_id=c[1].store_id, product_id=c[2],
            sales_date=date(2026,10,9), quantity=4, is_stockout=False))
        session.commit()
    response = read(c,'forecast')
    assert response.status_code == 200, response.text
    action = response.json()['data']['actions'][0]
    assert not action['can_execute']
    if kind=='corrupt':
        assert action['data_status']=='invalid' and action['execution_status']=='available'
        assert 'MODEL_ARTIFACT_INVALID' in {b['code'] for b in action['blockers']}
    else:
        assert action['data_status']=='valid' and action['execution_status']=='unavailable'
        assert {b['code'] for b in action['blockers']}=={'EXECUTION_UNAVAILABLE'}
    assert 'BASELINE_FALLBACK' not in {w['code'] for w in action['warnings']}


def test_forecast_readiness_foreign_store_not_exposed(readiness):
    from tests.integration.test_auth_public import setup
    c = readiness
    foreign = setup(c[0], 'foreign-d2@example.test')
    response = c[0][5].get(f'/api/v1/stores/{foreign.store_id}/readiness', params={'actions':'forecast'})
    assert response.status_code==404 and response.json()['data'] is None
