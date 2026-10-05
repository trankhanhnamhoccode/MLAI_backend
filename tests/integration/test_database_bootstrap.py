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
            "alembic_version", "users", "stores", "store_memberships",
        }
        with Session(engine) as fresh:
            assert fresh.scalar(text("SELECT version_num FROM public.alembic_version")) == "0002_identity_store"
    finally:
        engine.dispose()
