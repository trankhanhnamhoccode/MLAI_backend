from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import migration_config


def test_empty_alembic_baseline_and_synchronous_session(database_settings: Settings) -> None:
    engine = create_database_engine(database_settings)
    try:
        assert engine.dialect.name == "postgresql"
        command.downgrade(migration_config(), "0001_scaffold")
        assert inspect(engine).get_table_names(schema="public") == ["alembic_version"]
        with Session(engine) as session:
            assert session.scalar(text("SELECT 1")) == 1
            assert session.scalar(text("SELECT current_database()")) == "shelfcash_test"
            assert session.scalar(text("SELECT version_num FROM public.alembic_version")) == "0001_scaffold"
        command.downgrade(migration_config(), "base")
        with Session(engine) as fresh:
            assert fresh.scalar(text("SELECT COUNT(*) FROM public.alembic_version")) == 0
        command.upgrade(migration_config(), "head")
        assert set(inspect(engine).get_table_names(schema="public")) == {
            "supplier_source_records", "term_source_records", "payable_fee_records", "scope_declaration_records", "inventory_receipt_records", "inventory_thresholds", "stock_request_receipts", "inventory_audit", "recipe_schedule_changes", "recipe_schedule_request_receipts", "forecast_serving_identities", "model_serving_configurations", "planning_budgets", "planning_configuration_events", "planning_configuration_receipts", "planning_configuration_revisions", "planning_defaults", "saved_requirements", "planning_exports",
            "alembic_version", "users", "stores", "store_memberships", "products", "ingredients", "recipes", "recipe_lines", "suppliers", "supplier_terms", "sales_daily", "inventory_lots", "inventory_movements", "business_constraints", "forecast_runs", "forecast_predictions", "decision_runs", "forecast_run_inputs", "forecast_execution_metadata", "planning_runs", "auth_accounts", "auth_sessions", "credential_tokens", "membership_grants", "auth_audit", "staff_invitations", "permission_events", "invitation_events", "staff_request_receipts", "invitation_delivery_intents", "auth_rate_limits", "public_read_revisions", "import_batches", "import_blobs", "import_files", "import_profiles", "import_profile_versions", "import_source_contexts", "import_jobs", "import_previews", "import_receipts", "import_audit",
        }
        with Session(engine) as fresh:
            assert fresh.scalar(text("SELECT version_num FROM public.alembic_version")) == "0017_planning_exports"
    finally:
        engine.dispose()
