"""Repository-local PostgreSQL verification commands, outside application runtime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine


def migration_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


TEST_DATABASE_NAMES = frozenset({"shelfcash_test", "shelfcash_import_test", "shelfcash_auth_test", "shelfcash_integration_test", "shelfcash_notifications_test", "shelfcash_local_test", "shelfcash_readiness_test"})
DEDICATED_TEST_ROLES = {"shelfcash_integration_test": "shelfcash_integration_tester",
                        "shelfcash_notifications_test": "shelfcash_notifications_tester", "shelfcash_local_test": "shelfcash_local_tester",
                        "shelfcash_readiness_test": "shelfcash_readiness_tester"}


def validate_reset_target(settings: Settings) -> None:
    """Explicit allowlist: never reset arbitrary databases or remote hosts."""
    if settings.environment not in {"development", "test"}:
        raise ValueError("Reset requires ENVIRONMENT=development or test")
    url = make_url(settings.database_url)
    if url.database in DEDICATED_TEST_ROLES and url.username != DEDICATED_TEST_ROLES[url.database]:
        raise ValueError("Integration test database requires its dedicated tester role")
    if url.host not in {"localhost", "127.0.0.1", "::1", "postgres"} or url.query:
        raise ValueError("Reset only permits local PostgreSQL hosts without URL query overrides")
    if url.database not in ({"shelfcash"} | TEST_DATABASE_NAMES):
        raise ValueError("Reset requires an explicitly allowlisted local database")
    if settings.environment == "test" and url.database not in TEST_DATABASE_NAMES:
        raise ValueError("Test resets require an explicitly allowlisted test database")


def inspect_database(settings: Settings) -> dict[str, object]:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            database = connection.scalar(text("SELECT current_database()"))
            connection_user = connection.scalar(text("SELECT current_user"))
            version = connection.scalar(text("SHOW server_version"))
            tables: dict[str, int] = {}
            for name in inspect(connection).get_table_names(schema="public"):
                quoted = connection.dialect.identifier_preparer.quote_identifier(name)
                tables[name] = connection.scalar(text(f'SELECT COUNT(*) FROM public.{quoted}'))
            revisions = (
                list(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
                if "alembic_version" in tables else []
            )
        heads = ScriptDirectory.from_config(migration_config()).get_heads()
        return {
            "reachable": True, "database": database, "current_user": connection_user, "server_version": version,
            "schema": "public", "revisions": revisions, "expected_heads": heads,
            "at_head": sorted(revisions) == sorted(heads), "tables": tables,
        }
    finally:
        engine.dispose()


def require_head(state: dict[str, object]) -> None:
    if not state["at_head"]:
        raise ValueError(f"Database is not at Alembic head: {state['revisions']}; expected {state['expected_heads']}")


def seed_demo(settings: Settings) -> None:
    state = inspect_database(settings)
    require_head(state)
    if set(state["tables"]) != {"alembic_version", "users", "stores", "store_memberships", "products", "ingredients", "recipes", "recipe_lines", "suppliers", "supplier_terms", "sales_daily", "inventory_lots", "inventory_movements", "business_constraints", "forecast_runs", "forecast_predictions", "decision_runs", "forecast_run_inputs", "forecast_execution_metadata", "planning_runs", "auth_accounts", "auth_sessions", "credential_tokens", "membership_grants", "auth_audit", "staff_invitations", "permission_events", "invitation_events", "staff_request_receipts", "invitation_delivery_intents", "auth_rate_limits", "public_read_revisions", "import_batches", "import_blobs", "import_files", "import_profiles", "import_profile_versions", "import_source_contexts", "import_jobs", "import_previews", "import_receipts", "import_audit", "supplier_source_records", "term_source_records", "payable_fee_records", "scope_declaration_records", "inventory_receipt_records", "inventory_thresholds", "stock_request_receipts", "inventory_audit", "recipe_schedule_changes", "recipe_schedule_request_receipts", "forecast_serving_identities", "model_serving_configurations", "planning_budgets", "planning_configuration_events", "planning_configuration_receipts", "planning_configuration_revisions", "planning_defaults", "saved_requirements", "planning_exports", "email_verification_tokens", "email_verification_deliveries", "password_reset_deliveries", "import_history_records", "notification_intents", "notifications", "notification_read_receipts", "permission_requests", "permission_request_audit", "mapping_submissions", "store_creation_receipts"}:
        raise ValueError("Seed expects the current S1 schema and S2.3 retention table")
    print("No business seed data: seeding is not implemented. Migrated schema verified; no rows written.")


def reset_database(settings: Settings, seed: bool) -> None:
    validate_reset_target(settings)
    engine = create_database_engine(settings)
    try:
        # PostgreSQL DDL is transactional: lock/permission errors roll back this reset.
        with engine.begin() as connection:
            url = make_url(settings.database_url)
            if connection.scalar(text("SELECT current_database()")) != url.database:
                raise ValueError("Connected database does not match the guarded target")
            if url.database in DEDICATED_TEST_ROLES and connection.scalar(text("SELECT current_user")) != url.username:
                raise ValueError("Connected user does not match the guarded integration tester")
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public AUTHORIZATION CURRENT_USER"))
    finally:
        engine.dispose()
    # Alembic must use the exact validated URL, including when invoked by a test.
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(migration_config(), "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
    state = inspect_database(settings)
    require_head(state)
    print(json.dumps(state, indent=2))
    if seed:
        seed_demo(settings)


def run_tests(category: str) -> int:
    target = ROOT / "tests" if category == "all" else ROOT / "tests" / category
    if category != "all" and not list(target.rglob("test_*.py")):
        print(f"No {category} tests implemented; no tests ran.")
        return 0
    return subprocess.run([sys.executable, "-m", "pytest", str(target)], cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    tests = commands.add_parser("test")
    tests.add_argument("category", nargs="?", default="all", choices=("unit", "integration", "api", "e2e", "all"))
    reset = commands.add_parser("reset")
    reset.add_argument("--seed", action="store_true")
    reset.add_argument("--test-database", action="store_true")
    commands.add_parser("seed")
    status = commands.add_parser("status")
    status.add_argument("--allow-unmigrated", action="store_true")
    status.add_argument("--test-database", action="store_true")
    arguments = parser.parse_args()
    os.chdir(ROOT)
    if arguments.command == "test":
        return run_tests(arguments.category)
    try:
        settings = Settings()
        if getattr(arguments, "test_database", False):
            settings = settings.model_copy(update={"environment": "test", "database_url": settings.test_database_url})
            validate_reset_target(settings)
        if arguments.command == "reset":
            reset_database(settings, arguments.seed)
        elif arguments.command == "seed":
            seed_demo(settings)
        else:
            state = inspect_database(settings)
            print(json.dumps(state, indent=2))
            if not arguments.allow_unmigrated:
                require_head(state)
        return 0
    except Exception as error:
        print(f"ERROR: {type(error).__name__} (details omitted to protect credentials)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
