"""Exercise command results AND persisted state across fresh connections."""
from sqlalchemy.engine import make_url
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
    assert state["database"] == make_url(database_settings.database_url).database
    assert state["revisions"] == ["0026_collaboration_requests"]
    assert state["tables"] == {"alembic_version": 1, "users": 0, "stores": 0, "store_memberships": 0, "products": 0, "ingredients": 0, "recipes": 0, "recipe_lines": 0, "suppliers": 0, "supplier_terms": 0, "sales_daily": 0, "inventory_lots": 0, "inventory_movements": 0, "business_constraints": 0, "forecast_runs": 0, "forecast_predictions": 0, "decision_runs": 0, "forecast_run_inputs": 0, "forecast_execution_metadata": 0, "planning_runs": 0, "auth_accounts": 0, "auth_sessions": 0, "credential_tokens": 0, "membership_grants": 0, "auth_audit": 0, "staff_invitations": 0, "permission_events": 0, "invitation_events": 0, "staff_request_receipts": 0, "invitation_delivery_intents": 0, "auth_rate_limits": 0, "public_read_revisions": 0, "import_batches": 0, "import_blobs": 0, "import_files": 0, "import_profiles": 0, "import_profile_versions": 0, "import_source_contexts": 0, "import_jobs": 0, "import_previews": 0, "import_receipts": 0, "import_audit": 0, "supplier_source_records": 0, "term_source_records": 0, "payable_fee_records": 0, "scope_declaration_records": 0, "inventory_receipt_records": 0, "inventory_thresholds": 0, "stock_request_receipts": 0, "inventory_audit": 0, "recipe_schedule_changes": 0, "recipe_schedule_request_receipts": 0, 'forecast_serving_identities': 0, 'model_serving_configurations': 0, 'planning_budgets': 0, 'planning_configuration_events': 0, 'planning_configuration_receipts': 0, 'planning_configuration_revisions': 0, 'planning_defaults': 0, 'saved_requirements': 0, 'planning_exports': 0, 'email_verification_tokens': 0, 'email_verification_deliveries': 0, 'password_reset_deliveries': 0, 'import_history_records': 0, 'notification_intents': 0, 'notifications': 0, 'notification_read_receipts': 0, 'permission_requests': 0, 'permission_request_audit': 0, 'mapping_submissions': 0}
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
                assert fresh.scalar(text("SELECT version_num FROM public.alembic_version")) == "0026_collaboration_requests"
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
        assert state["tables"] == {"users": 0, "stores": 0, "store_memberships": 0, "products": 0, "ingredients": 0, "recipes": 0, "recipe_lines": 0, "suppliers": 0, "supplier_terms": 0, "sales_daily": 0, "inventory_lots": 0, "inventory_movements": 0, "business_constraints": 0, "forecast_runs": 0, "forecast_predictions": 0, "decision_runs": 0, "forecast_run_inputs": 0, "forecast_execution_metadata": 0, "planning_runs": 0, "auth_accounts": 0, "auth_sessions": 0, "credential_tokens": 0, "membership_grants": 0, "auth_audit": 0, "staff_invitations": 0, "permission_events": 0, "invitation_events": 0, "staff_request_receipts": 0, "invitation_delivery_intents": 0, "auth_rate_limits": 0, "public_read_revisions": 0, "import_batches": 0, "import_blobs": 0, "import_files": 0, "import_profiles": 0, "import_profile_versions": 0, "import_source_contexts": 0, "import_jobs": 0, "import_previews": 0, "import_receipts": 0, "import_audit": 0, "supplier_source_records": 0, "term_source_records": 0, "payable_fee_records": 0, "scope_declaration_records": 0, "inventory_receipt_records": 0, "inventory_thresholds": 0, "stock_request_receipts": 0, "inventory_audit": 0, "recipe_schedule_changes": 0, "recipe_schedule_request_receipts": 0, 'forecast_serving_identities': 0, 'model_serving_configurations': 0, 'planning_budgets': 0, 'planning_configuration_events': 0, 'planning_configuration_receipts': 0, 'planning_configuration_revisions': 0, 'planning_defaults': 0, 'saved_requirements': 0, 'planning_exports': 0, 'email_verification_tokens': 0, 'email_verification_deliveries': 0, 'password_reset_deliveries': 0, 'import_history_records': 0, 'notification_intents': 0, 'notifications': 0, 'notification_read_receipts': 0, 'permission_requests': 0, 'permission_request_audit': 0, 'mapping_submissions': 0}
        assert run_command(database_settings, "status").returncode != 0
        with engine.connect() as fresh:
            assert fresh.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
    finally:
        engine.dispose()
