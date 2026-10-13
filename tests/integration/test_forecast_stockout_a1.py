"""Real trained execution and schema-1 replay alongside A1 schema-2 captures."""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.application.contracts.common import RunReferenceInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_evaluation import backtest
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases
from app.infrastructure.forecast_model import ModelBoundaryError, train_quantiles
from app.models import ForecastRun, ForecastRunInput, SalesDaily
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.domain.forecasting.baseline import BaselineNotReadyError
from tests.integration.test_forecast_trained_execution import setup
from tests.integration.test_readiness_context import readiness, config, env, known_facts, read


def test_real_trained_stockout_evidence_and_replay_after_live_change(setup):
    engine, original, cases, _ = setup
    start = original.request.history_start_date
    with Session(engine) as writer, writer.begin():
        for row in writer.scalars(select(SalesDaily)):
            row.is_stockout = False
            if row.sales_date in (start, start + timedelta(days=35)):
                row.is_stockout = True
                row.quantity = 1
    prepared = ForecastExecutionUseCases(engine).capture(original.request)
    report = backtest(prepared, 'SYNTHETIC')
    assert report.selected_family == 'lightgbm_quantile'
    identity = cases.artifacts.publish(train_quantiles(prepared), report)
    result = cases.execute(prepared.request, identity)
    assert result.model_type == 'lightgbm_quantile'
    reference = RunReferenceInput(store_id=prepared.request.store_id, run_id=result.id)
    replay = cases.replay(reference)
    assert {'CENSORED_HISTORY_EXCLUDED', 'DEMAND_RECONSTRUCTED'} <= {w.code for w in replay.warnings}
    with Session(engine) as fresh:
        saved = fresh.get(ForecastRunInput, result.id)
        assert saved.prepared_json == json.loads(serialize_prepared(prepared).canonical_json)
        assert saved.digest == serialize_prepared(prepared).digest
    with Session(engine) as writer, writer.begin():
        for row in writer.scalars(select(SalesDaily)):
            row.quantity = Decimal(999)
            row.is_stockout = None
    assert cases.replay(reference) == replay
    persisted = cases.replay_persisted(reference)
    assert persisted.input_fingerprint == result.input_fingerprint


def test_legacy_schema_1_exact_retention_and_replay_on_new_schema(setup):
    engine, prepared, trained, _ = setup
    # Same scope/observed values, exact old serialization; never attach v2 evidence.
    values = prepared.model_dump()
    values.update(schema_version=1, demand_policy='observed_sales_v1', demand_records=())
    legacy = type(prepared).model_validate(values)
    encoded = serialize_prepared(legacy)
    payload = json.loads(encoded.canonical_json)
    assert 'demand_policy' not in payload and 'demand_records' not in payload
    assert all('is_stockout' not in row for row in payload['observations'])
    service = ForecastExecutionUseCases(engine)
    result = service._execute_prepared(legacy)
    reference = RunReferenceInput(store_id=legacy.request.store_id, run_id=result.id)
    replay = service.replay(reference)
    assert replay.warnings == ()
    with Session(engine) as fresh:
        stored = fresh.get(ForecastRunInput, result.id)
        assert stored.prepared_json == payload and stored.digest == encoded.digest
    with Session(engine) as writer, writer.begin():
        for row in writer.scalars(select(SalesDaily)):
            row.quantity = 999
            row.is_stockout = False
    assert serialize_prepared(service.load_retained(reference)) == encoded
    assert service.replay(reference) == replay
    report = backtest(legacy, 'SYNTHETIC')
    identity = trained.artifacts.publish(train_quantiles(legacy), report)
    with pytest.raises(ModelBoundaryError, match='INCOMPATIBLE'):
        trained.execute(legacy.request, identity)


def test_stockout_only_change_breaks_serving_reuse_without_changing_quantity(readiness):
    c = readiness
    known_facts(c)
    serving = c[0][5].app.state.forecast_serving
    with Session(c[0][1]) as writer, writer.begin():
        writer.scalar(select(SalesDaily)).is_stockout = False
    first = serving.serve(serving.prepare(c[1].store_id, date(2026, 10, 10)))
    assert serving.serve(serving.prepare(c[1].store_id, date(2026, 10, 10))).reused
    with Session(c[0][1]) as writer, writer.begin():
        sale = writer.scalar(select(SalesDaily))
        assert sale.quantity == 0
        sale.is_stockout = None
    second = serving.serve(serving.prepare(c[1].store_id, date(2026, 10, 10)))
    assert not second.reused and first.run.id != second.run.id
    assert first.identity.prepared_digest != second.identity.prepared_digest
    assert [(p.product_id, p.forecast_date, p.p25, p.p50, p.p75) for p in first.run.predictions] == [
        (p.product_id, p.forecast_date, p.p25, p.p50, p.p75) for p in second.run.predictions]
    with Session(c[0][1]) as fresh:
        old = fresh.get(ForecastRunInput, first.run.id)
        new = fresh.get(ForecastRunInput, second.run.id)
        assert old.prepared_json['observations'][0]['is_stockout'] is False
        assert new.prepared_json['observations'][0]['is_stockout'] is None


def test_all_unsupported_censored_history_blocks_readiness_and_direct_execution(readiness):
    c = readiness
    known_facts(c)
    with Session(c[0][1]) as writer, writer.begin():
        writer.scalar(select(SalesDaily)).is_stockout = True
    response = read(c, 'forecast')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['actions'][0]['availability'] == 'blocked'
    assert 'CENSORED_HISTORY_NOT_USABLE' in {b['code'] for b in data['actions'][0]['blockers']}
    request = ForecastExecutionInput(store_id=c[1].store_id, product_ids=(c[2],),
        history_start_date=date(2026, 10, 9), cutoff_date=date(2026, 10, 9))
    with pytest.raises(BaselineNotReadyError):
        ForecastExecutionUseCases(c[0][1]).execute(request)
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ForecastRun)) == 0
        assert fresh.scalar(select(SalesDaily)).quantity == 0
