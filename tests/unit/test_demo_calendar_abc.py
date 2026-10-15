"""Benchmark-only calendar authority and temporal gates; never operational writes."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from decimal import Decimal
import json
import pytest
from pydantic import ValidationError

from app.application.contracts.demo_calendar import DemoCalendarAssumption
from app.application.contracts.demo_workbooks import AdmissionDeclarations,DemoDataset
from app.application.contracts.forecast_benchmark import BenchmarkPlan,DEMO_ABC_PROTOCOL_DIGEST
from app.application.contracts.forecast_challenger import ChallengerInput,ChallengerError
from app.application.demo_calendar import assume_calendar
from app.application.demo_workbook_normalization import normalize_demo
from app.application.demo_workbook_admission import assess
from app.application.forecast_benchmark_admission import admit_plan,calendar_at_origin,holdout_dates
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.forecast_challenger_validation import admit_input
from app.application.use_cases.forecast_benchmark import load_protocol
from app.infrastructure.forecast_benchmark_features import NativeFrameCache
from tests.unit.test_demo_workbook_admission import bundle
from tests.fixtures.forecast_engine.benchmark_setup import synthetic_benchmark

ROOT=Path(__file__).resolve().parents[2]


def calendar_fixture(tmp_path):
    books=bundle(tmp_path)
    raw,issues=normalize_demo(books,'UTC')
    config=AdmissionDeclarations(timezone='UTC',accept_five_single_item_scope=True,
        observation_availability='RETROSPECTIVE_NEXT_RUN_ASSUMPTION',source_revision=raw.source_revision)
    _,_,data,_=assess(raw,books,config,issues,load_protocol(ROOT))
    digest=next(b.sha256 for b in books if b.role=='calendar')
    assumption=DemoCalendarAssumption(source_revision=raw.source_revision,calendar_file_sha256=digest,
        calendar_rows_digest=challenger_digest('demo-calendar-rows',raw.calendar),store_id=data.store_id,
        product_ids=tuple(p.product_id for p in data.products),timezone='UTC',recorded_at=datetime(2026,10,15,tzinfo=timezone.utc))
    return raw,data,assumption,digest


def test_calendar_assumption_keeps_raw_vintages_unknown_and_only_sourced_fields(tmp_path):
    raw,data,assumption,digest=calendar_fixture(tmp_path)
    result=assume_calendar(data,raw,assumption,digest)
    assert all(r.available_at is None for r in raw.calendar)
    assert result.observations==data.observations
    assert [(r.day,r.closed,r.holiday) for r in result.calendar]==[(r.day,r.closed,r.holiday) for r in raw.calendar]
    assert all(r.source.startswith('benchmark_assumed_calendar:') for r in result.calendar)
    assert assumption.actor_identifier is None and not assumption.historical_vintage_proof
    with pytest.raises(ValidationError):
        DemoCalendarAssumption.model_validate(assumption.model_dump(mode='python')|dict(fields=('closed','holiday','weather')))


@pytest.mark.parametrize('field,value',[('source_revision','a'*64),('calendar_file_sha256','a'*64),('calendar_rows_digest','a'*64),('timezone','Asia/Ho_Chi_Minh'),('product_ids',())])
def test_calendar_declaration_hash_scope_mismatch_rejects(tmp_path,field,value):
    raw,data,assumption,digest=calendar_fixture(tmp_path)
    with pytest.raises((ValueError,ValidationError)):
        changed=DemoCalendarAssumption.model_validate(assumption.model_dump(mode='python')|{field:value})
        assume_calendar(data,raw,changed,digest)


def test_missing_calendar_never_fills_open_and_conflicting_closure_rejects(tmp_path):
    raw,data,assumption,digest=calendar_fixture(tmp_path)
    changed=DemoDataset.model_validate(raw.model_dump(mode='python')|dict(calendar=raw.calendar[1:]))
    approved=DemoCalendarAssumption.model_validate(assumption.model_dump(mode='python')|dict(calendar_rows_digest=challenger_digest('demo-calendar-rows',changed.calendar)))
    result=assume_calendar(data,changed,approved,digest)
    with pytest.raises(ChallengerError,match='SOURCED_CALENDAR_NOT_AVAILABLE'):
        calendar_at_origin(result,max(o.sales_date for o in data.observations))
    changed=raw.model_dump(mode='python');changed['calendar'][2]['closed']=True
    changed=DemoDataset.model_validate(changed)
    approved=DemoCalendarAssumption.model_validate(assumption.model_dump(mode='python')|dict(calendar_rows_digest=challenger_digest('demo-calendar-rows',changed.calendar)))
    with pytest.raises(ValueError,match='SALES_CONFLICT'):assume_calendar(data,changed,approved,digest)


def test_projection_and_native_boundary_both_reject_production(tmp_path):
    raw,data,assumption,digest=calendar_fixture(tmp_path)
    with pytest.raises(ValueError,match='PRODUCTION_REJECTED'):assume_calendar(data,raw,assumption,digest,mode='production')
    result=assume_calendar(data,raw,assumption,digest)
    cutoff=max(o.sales_date for o in data.observations)
    value=ChallengerInput(mode='production',request=dict(store_id=data.store_id,product_ids=tuple(p.product_id for p in data.products),
        history_start_date=min(o.sales_date for o in data.observations),cutoff_date=cutoff),timezone='UTC',
        inference_at=datetime(2026,10,15,tzinfo=timezone.utc),products=data.products,observations=data.observations,
        forecast_dates=tuple(cutoff+timedelta(days=h) for h in range(1,8)),calendar=result.calendar,artifact_identity='a'*64)
    with pytest.raises(ChallengerError,match='BENCHMARK_CALENDAR_PRODUCTION_REJECTED'):admit_input(value)


@pytest.mark.parametrize('kind',['closed_unknown','holiday_unknown','formula'])
def test_unknown_or_formula_calendar_is_not_assumable(tmp_path,kind):
    raw,data,assumption,digest=calendar_fixture(tmp_path)
    changed=raw.model_dump(mode='python')
    if kind=='formula':changed['calendar'][0]['sources'][0]['formula']=True
    else:changed['calendar'][0]['closed' if kind=='closed_unknown' else 'holiday']=None
    changed=DemoDataset.model_validate(changed)
    approved=DemoCalendarAssumption.model_validate(assumption.model_dump(mode='python')|dict(calendar_rows_digest=challenger_digest('demo-calendar-rows',changed.calendar)))
    with pytest.raises(ValueError,match='INVALID_SOURCE'):assume_calendar(data,changed,approved,digest)


def protocol_plan(data):
    protocol=json.loads((ROOT/'tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json').read_bytes())
    return BenchmarkPlan(harness_version='causal_benchmark/3',protocol_digest=DEMO_ABC_PROTOCOL_DIGEST,
        dataset_digest=challenger_digest('dataset',data),tasks=protocol['tasks'])


def test_v3_windows_and_quarantine_freeze_configs_and_reject_overlap():
    data,_=synthetic_benchmark();plan=protocol_plan(data)
    admit_plan(data,plan);protocol=load_protocol(ROOT,plan)
    assert protocol['arm_configuration']==load_protocol(ROOT)['arm_configuration']
    assert len(holdout_dates(plan))==14
    raw=plan.model_dump(mode='python');raw['tasks'][0]['point_start']=raw['tasks'][0]['train_end']
    with pytest.raises(ChallengerError,match='FROZEN_WINDOWS'):admit_plan(data,BenchmarkPlan.model_validate(raw))


def test_per_product_native_84_day_gate_stays_strict(monkeypatch):
    import pandas as pd
    from shelfcash_forecast.config import ForecastConfig
    from app.infrastructure import forecast_benchmark_features as features
    data,_=synthetic_benchmark();plan=protocol_plan(data)
    # Global union84, each Product83: must not pass the per-Product check.
    first=plan.tasks[0].train_end-timedelta(days=100)
    table=pd.DataFrame([dict(product_key=str(p.product_id),target_date=first+timedelta(days=i+j))
        for j,p in enumerate(data.products) for i in range(83)])
    monkeypatch.setattr(features,'build_native_training_table',lambda *a:(table,0))
    with pytest.raises(ChallengerError,match='NATIVE_PRODUCT_TRAINING_DATES_INSUFFICIENT'):
        features.native_training_table(data,plan.tasks[0].train_end,plan,ForecastConfig(),None,None)


def test_future_labels_do_not_change_cached_native_prefix_and_cache_is_detached():
    from shelfcash_forecast.config import ForecastConfig
    from app.application.contracts.forecast_benchmark import BenchmarkDataset
    data,plan=synthetic_benchmark();origin=plan.tasks[0].origin;config=ForecastConfig();cache=NativeFrameCache()
    panel,frame=cache.get(data,origin,config)
    raw=data.model_dump(mode='python')
    for o in raw['observations']:
        if o['sales_date']>origin:o['quantity']=Decimal(999999)
    altered=BenchmarkDataset.model_validate(raw)
    after_panel,after=cache.get(altered,origin,config)
    assert panel.equals(after_panel) and frame.equals(after) and cache.hits==1
    frame['horizon']=99
    _,fresh=cache.get(data,origin,config)
    assert not (fresh.horizon==99).any()


def test_replay_restores_integral_frozen_budget_without_relaxing_validation():
    from scripts.verify_demo_abc import restore_frozen_demo_plan
    from app.application.forecast_challenger_serialization import canonical_bytes
    data,_=synthetic_benchmark();plan=protocol_plan(data)
    raw=json.loads(canonical_bytes(plan))
    assert type(raw['budget']['wall_seconds']) is int
    restored=restore_frozen_demo_plan(raw)
    assert canonical_bytes(restored)==canonical_bytes(raw)
    raw['budget']['wall_seconds']=301
    with pytest.raises(ValidationError):restore_frozen_demo_plan(raw)
    raw['budget']['wall_seconds']=300.0
    restored=restore_frozen_demo_plan(raw)
    assert type(restored.budget.wall_seconds) is float
