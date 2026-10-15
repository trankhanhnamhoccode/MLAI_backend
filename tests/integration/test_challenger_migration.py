"""Constraint-only roundtrip on the guarded disposable challenger database."""
from alembic import command
from sqlalchemy import create_engine,text
from scripts.dev import migration_config,validate_reset_target


def test_metadata_v2_roundtrip_preserves_empty_schema(database_settings):
    validate_reset_target(database_settings)
    assert database_settings.database_url.endswith('/shelfcash_challenger_test')
    engine=create_engine(database_settings.database_url)
    def constraint():
        with engine.connect() as connection:
            return connection.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_forecast_execution_metadata_version'"))
    try:
        assert "'2'" in constraint()
        command.downgrade(migration_config(),'0027_self_service_stores')
        assert "'2'" not in constraint()
        command.upgrade(migration_config(),'head')
        assert "'2'" in constraint()
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='f4_20261016_metadata_v2'
            assert connection.scalar(text('SELECT count(*) FROM forecast_runs'))==0
    finally:engine.dispose()
