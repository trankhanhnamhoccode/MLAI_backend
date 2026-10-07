"""S1.4 schema-only fixtures on real PostgreSQL, not engine outputs."""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scripts.dev import migration_config
from test_supplier_operational_constraints import engine, parents

HEAD = "0008_forecast_execution_meta"
TABLES = {"forecast_runs", "forecast_predictions", "decision_runs"}
STARTED = datetime(2026, 10, 1, 0, tzinfo=timezone.utc)
FINISHED = datetime(2026, 10, 1, 1, tzinfo=timezone.utc)


def forecast_values(ids, **changes):
    return dict(store_id=ids["store"], status="COMPLETED",
                training_start_date=date(2026, 7, 1), training_end_date=date(2026, 9, 30),
                forecast_start_date=date(2026, 10, 1), forecast_end_date=date(2026, 10, 7),
                model_type="persistence_fixture", model_version="fixture-v1",
                artifact_key=None, metrics_json={"MAE": "2.125"},
                input_fingerprint="a" * 64, started_at=STARTED, completed_at=FINISHED) | changes


def saved_forecast(engine, ids, **changes):
    from app.models import ForecastRun
    with Session(engine) as session:
        row = ForecastRun(**forecast_values(ids, **changes))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    return identifier


def decision_values(ids, run_id, **changes):
    snapshot = {"forecast": {"id": str(run_id), "p50": "100"},
                "recipe": {"id": "fixture-recipe", "version": 2, "quantity": "80"},
                "inventory": {"ingredient_id": str(ids["ingredient"]), "on_hand": "20", "unit": "ml"},
                "supplier_term": {"version": 3, "pack_cost": "384000", "lead_time_days": 2},
                "constraint": {"type": "BUDGET_LIMIT", "numeric_value": "7000000"}}
    package = {"fixture_only": True, "evaluations": [
        {"strategy": strategy, "fixture_metric": index}
        for index, strategy in enumerate(["LEAN", "BALANCED", "PROTECTED"])],
        "recommendation": "BALANCED", "warnings": []}
    return dict(store_id=ids["store"], forecast_run_id=run_id, status="COMPLETED",
                planning_start_date=date(2026, 10, 1), planning_end_date=date(2026, 10, 7),
                package_schema_version=1, input_fingerprint="b" * 64,
                input_snapshot_json=snapshot, decision_package_json=package,
                recommended_strategy="BALANCED", started_at=STARTED, completed_at=FINISHED) | changes


def test_fresh_migration_exact_tables_and_downgrade(engine):
    before = set(inspect(engine).get_table_names())
    assert len(before) == 19 and TABLES <= before
    assert not {"import_jobs", "mapping_profiles", "purchase_orders", "what_if_runs"} & before
    with engine.connect() as fresh:
        assert fresh.scalar(text("SELECT current_database()")) == "shelfcash_test"
        assert fresh.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert fresh.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('forecast_runs'::regclass,'forecast_predictions'::regclass,'decision_runs'::regclass)")) == 0
    command.downgrade(migration_config(), "0005_data_semantics_correction")
    assert set(inspect(engine).get_table_names()) == before - TABLES - {"forecast_run_inputs", "forecast_execution_metadata"}
    command.upgrade(migration_config(), "head")
    assert set(inspect(engine).get_table_names()) == before


@pytest.mark.parametrize("status", ["RUNNING", "COMPLETED", "FAILED"])
def test_forecast_commit_close_reload(engine, status):
    from app.models import ForecastRun
    ids = parents(engine)
    changes = dict(status=status)
    if status == "COMPLETED":
        changes["artifact_key"] = "models/persistence-fixture-v1.bin"
    if status == "RUNNING":
        changes.update(completed_at=None, input_fingerprint=None)
    elif status == "FAILED":
        changes.update(error_code="INSUFFICIENT_HISTORY", error_summary="Known fixture failure", input_fingerprint=None)
    identifier = saved_forecast(engine, ids, **changes)
    with Session(engine) as fresh:
        row = fresh.get(ForecastRun, identifier)
        for key, expected in forecast_values(ids, **changes).items():
            assert getattr(row, key) == expected
        assert row.created_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("changes", [
    {"status": "QUEUED"}, {"store_id": uuid4()},
    {"training_start_date": date(2026, 10, 1)}, {"forecast_end_date": date(2026, 9, 30)},
    {"model_type": " "}, {"model_version": ""}, {"input_fingerprint": None},
    {"input_fingerprint": " "}, {"completed_at": None},
    {"completed_at": datetime(2026, 9, 30, tzinfo=timezone.utc)},
    {"error_code": "FALSE_FAILURE"}, {"metrics_json": []},
    {"status": "RUNNING"}, {"status": "FAILED", "input_fingerprint": None},
])
def test_forecast_constraints(engine, changes):
    from app.models import ForecastRun
    ids = parents(engine)
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(ForecastRun(**forecast_values(ids, **changes)))
        session.commit()


def prediction_values(ids, run_id, **changes):
    return dict(forecast_run_id=run_id, store_id=ids["store"], product_id=ids["product"],
                forecast_date=date(2026, 10, 1), p25=Decimal("80"),
                p50=Decimal("100.125"), p75=Decimal("130")) | changes


def test_prediction_fresh_reload_and_application_horizon_limit(engine):
    from app.models import ForecastPrediction
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    with Session(engine) as session:
        row = ForecastPrediction(**prediction_values(ids, run_id))
        session.add(row)
        session.flush()
        identifier = row.id
        # Explicitly prove cross-table horizon is NOT a DB constraint in S1.4.
        outside = ForecastPrediction(**prediction_values(ids, run_id, forecast_date=date(2026, 10, 8)))
        session.add(outside)
        session.commit()
    with Session(engine) as fresh:
        row = fresh.get(ForecastPrediction, identifier)
        for key, value in prediction_values(ids, run_id).items():
            assert getattr(row, key) == value
        assert len(fresh.scalars(select(ForecastPrediction)).all()) == 2


@pytest.mark.parametrize("issue", ["negative", "p25_order", "p50_order", "nan", "infinity", "duplicate", "product_store", "run_store", "missing_run", "missing_product"])
def test_prediction_integrity(engine, issue):
    from app.models import ForecastPrediction
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    changes = {"negative": {"p25": -1}, "p25_order": {"p25": 101}, "p50_order": {"p50": 131},
               "nan": {"p75": Decimal("NaN")}, "infinity": {"p75": Decimal("Infinity")},
               "product_store": {"product_id": ids["other_product"]},
               "run_store": {"store_id": ids["other_store"], "product_id": ids["other_product"]},
               "missing_run": {"forecast_run_id": uuid4()}, "missing_product": {"product_id": uuid4()}, "duplicate": {}}[issue]
    if issue == "duplicate":
        with Session(engine) as session:
            session.add(ForecastPrediction(**prediction_values(ids, run_id)))
            session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(ForecastPrediction(**prediction_values(ids, run_id, **changes)))
        session.commit()


@pytest.mark.parametrize("strategy", ["LEAN", "BALANCED", "PROTECTED"])
def test_decision_json_fresh_reload_rerun_and_independent_values(engine, strategy):
    from app.models import DecisionRun, InventoryLot
    from test_supplier_operational_constraints import lot_values
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    values = decision_values(ids, run_id, recommended_strategy=strategy)
    values["decision_package_json"]["recommendation"] = strategy
    expected = deepcopy(values)
    with Session(engine) as session:
        source_lot = InventoryLot(**lot_values(ids, on_hand_quantity=Decimal("20")))
        first, rerun = DecisionRun(**values), DecisionRun(**deepcopy(values))
        session.add_all([source_lot, first, rerun])
        session.flush()
        identifiers = first.id, rerun.id, source_lot.id
        session.commit()
    values["input_snapshot_json"]["inventory"]["on_hand"] = "5"
    with engine.begin() as connection:
        # Test-only privileged SQL demonstrates snapshot independence, not mutation service.
        connection.execute(text("UPDATE inventory_lots SET on_hand_quantity=5 WHERE id=:id"), {"id": identifiers[2]})
    with Session(engine) as fresh:
        for identifier in identifiers[:2]:
            row = fresh.get(DecisionRun, identifier)
            for key, value in expected.items():
                assert getattr(row, key) == value
            assert row.input_snapshot_json["inventory"]["on_hand"] == "20"
        assert identifiers[0] != identifiers[1]
        assert fresh.get(InventoryLot, identifiers[2]).on_hand_quantity == 5


@pytest.mark.parametrize("field", ["package_schema_version", "input_fingerprint", "input_snapshot_json", "decision_package_json", "recommended_strategy", "completed_at", "forecast_run_id"])
def test_completed_decision_required_fields(engine, field):
    from app.models import DecisionRun
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(DecisionRun(**decision_values(ids, run_id, **{field: None})))
        session.commit()


@pytest.mark.parametrize("changes", [
    {"status": "RANDOM"}, {"recommended_strategy": "RANDOM"},
    {"package_schema_version": 0}, {"package_schema_version": -1},
    {"planning_end_date": date(2026, 9, 30)}, {"input_fingerprint": " "},
    {"input_snapshot_json": []}, {"decision_package_json": "invalid"},
    {"error_summary": "Unexpected error on completed"},
    {"completed_at": datetime(2026, 9, 30, tzinfo=timezone.utc)},
])
def test_decision_constraints(engine, changes):
    from app.models import DecisionRun
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(DecisionRun(**decision_values(ids, run_id, **changes)))
        session.commit()


def test_decision_cross_store(engine):
    from app.models import DecisionRun
    ids = parents(engine)
    run_id = saved_forecast(engine, ids, store_id=ids["other_store"])
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(DecisionRun(**decision_values(ids, run_id)))
        session.commit()


@pytest.mark.parametrize("status", ["RUNNING", "FAILED"])
@pytest.mark.parametrize("captured", [True, False])
def test_partial_decision_and_no_fake_results(engine, status, captured):
    from app.models import DecisionRun
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    changes = dict(status=status, decision_package_json=None, recommended_strategy=None,
                   completed_at=None if status == "RUNNING" else FINISHED)
    if status == "FAILED":
        changes.update(error_code="INPUT_NOT_READY", error_summary="Receipt age unavailable")
    if not captured:
        changes.update(input_snapshot_json=None, input_fingerprint=None, package_schema_version=None)
    with Session(engine) as session:
        row = DecisionRun(**decision_values(ids, run_id, **changes))
        session.add(row)
        session.flush()
        identifier = row.id
        session.commit()
    with Session(engine) as fresh:
        row = fresh.get(DecisionRun, identifier)
        assert row.status == status and row.decision_package_json is None
        assert row.recommended_strategy is None
        assert (row.input_snapshot_json is not None) == captured
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(DecisionRun(**decision_values(ids, run_id, **(changes | {"recommended_strategy": "BALANCED"}))))
        session.commit()


def test_zero_equal_quantiles_and_reference_deletion_restricted(engine):
    from app.models import ForecastPrediction
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    with Session(engine) as session:
        session.add(ForecastPrediction(**prediction_values(ids, run_id, p25=0, p50=0, p75=0)))
        session.commit()
    with Session(engine) as fresh:
        row = fresh.scalar(select(ForecastPrediction))
        assert row.p25 == row.p50 == row.p75 == Decimal("0")
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("DELETE FROM forecast_runs WHERE id=:id"), {"id": run_id})


@pytest.mark.parametrize("column", ["metrics_json", "input_snapshot_json", "decision_package_json"])
def test_json_null_cannot_bypass_object_presence_checks(engine, column):
    from app.models import DecisionRun
    ids = parents(engine)
    run_id = saved_forecast(engine, ids)
    identifier = run_id
    table = "forecast_runs"
    if column != "metrics_json":
        table = "decision_runs"
        with Session(engine) as session:
            row = DecisionRun(**decision_values(ids, run_id))
            session.add(row)
            session.flush()
            identifier = row.id
            session.commit()
    # Identifiers are a fixed parametrized allowlist, not user input.
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(f"UPDATE {table} SET {column}='null'::jsonb WHERE id=:id"), {"id": identifier})
