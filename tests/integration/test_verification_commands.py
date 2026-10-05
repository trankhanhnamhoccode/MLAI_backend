"""Exercise command results AND persisted state across fresh connections."""
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import text

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine

ROOT = Path(__file__).resolve().parents[2]


def run_command(settings: Settings, *arguments: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(ENVIRONMENT="test", DATABASE_URL=settings.database_url)
    environment.update(overrides)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/dev.py"), *arguments],
        cwd=ROOT.parent, env=environment, capture_output=True, text=True,
    )


def test_seed_and_status_verify_fresh_persisted_baseline(database_settings: Settings) -> None:
    for _ in range(2):
        result = run_command(database_settings, "seed")
        assert result.returncode == 0, result.stderr
        assert "No business seed data" in result.stdout
    result = run_command(database_settings, "status")
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["reachable"] is True
    assert state["database"] == "shelfcash_test"
    assert state["revisions"] == ["0006_forecast_decision_persist"]
    assert state["tables"] == {"alembic_version": 1, "users": 0, "stores": 0, "store_memberships": 0, "products": 0, "ingredients": 0, "recipes": 0, "recipe_lines": 0, "suppliers": 0, "supplier_terms": 0, "sales_daily": 0, "inventory_lots": 0, "inventory_movements": 0, "business_constraints": 0, "forecast_runs": 0, "forecast_predictions": 0, "decision_runs": 0}
    assert state["at_head"] is True
    engine = create_database_engine(database_settings)
    try:
        with engine.begin() as connection:
            connection.execute(text("UPDATE public.alembic_version SET version_num = 'wrong'"))
        assert run_command(database_settings, "seed").returncode != 0
        assert run_command(database_settings, "status").returncode != 0
    finally:
        engine.dispose()


def test_reset_seed_repeat_and_unsafe_target_guard(database_settings: Settings) -> None:
    engine = create_database_engine(database_settings)
    try:
        for _ in range(2):
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE public.disposable (value TEXT)"))
                connection.execute(text("INSERT INTO public.disposable VALUES ('preserve until reset')"))
            refused = run_command(database_settings, "reset", ENVIRONMENT="production")
            assert refused.returncode != 0
            with engine.connect() as fresh:
                assert fresh.scalar(text("SELECT value FROM public.disposable")) == "preserve until reset"
            result = run_command(database_settings, "reset", "--seed")
            assert result.returncode == 0, result.stderr
            assert "No business seed data" in result.stdout
            with engine.connect() as fresh:
                assert fresh.scalar(text("SELECT version_num FROM public.alembic_version")) == "0006_forecast_decision_persist"
                assert fresh.scalar(text("SELECT to_regclass('public.disposable')")) is None
    finally:
        engine.dispose()


def test_status_unmigrated_database_is_reachable(database_settings: Settings) -> None:
    engine = create_database_engine(database_settings)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE public.alembic_version"))
        result = run_command(database_settings, "status", "--allow-unmigrated")
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        assert state["reachable"] and not state["at_head"]
        assert state["tables"] == {"users": 0, "stores": 0, "store_memberships": 0, "products": 0, "ingredients": 0, "recipes": 0, "recipe_lines": 0, "suppliers": 0, "supplier_terms": 0, "sales_daily": 0, "inventory_lots": 0, "inventory_movements": 0, "business_constraints": 0, "forecast_runs": 0, "forecast_predictions": 0, "decision_runs": 0}
        assert run_command(database_settings, "status").returncode != 0
        with engine.connect() as fresh:
            assert fresh.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
    finally:
        engine.dispose()
