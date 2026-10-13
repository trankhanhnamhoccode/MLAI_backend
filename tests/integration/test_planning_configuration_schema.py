"""S4.8 schema roundtrip and retained evidence; exact guarded local test DB."""
from sqlalchemy.engine import make_url
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect,text,select
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError,IntegrityError
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.database.base import Base
from app.models.planning_configuration import SavedRequirement,PlanningConfigurationEvent
from scripts.dev import migration_config
from tests.integration.test_planning_configuration_public import env,config,save

TABLES={'email_verification_tokens','email_verification_deliveries', 'password_reset_deliveries','import_history_records','notification_intents','notifications','notification_read_receipts','planning_exports','planning_defaults','planning_budgets','saved_requirements','planning_configuration_events','planning_configuration_revisions','planning_configuration_receipts','model_serving_configurations','forecast_serving_identities'}


def test_clean_roundtrip_exact_schema_metadata(database_settings):
    engine=create_database_engine(database_settings)
    try:
        with engine.connect() as c:assert c.scalar(text('SELECT current_database()')) == make_url(database_settings.database_url).database
        before=set(inspect(engine).get_table_names())
        command.downgrade(migration_config(),'0015_recipe_schedule')
        assert set(inspect(engine).get_table_names())==before-TABLES
        command.upgrade(migration_config(),'head')
        assert set(inspect(engine).get_table_names())==before
        with engine.connect() as c:
            assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0025_notifications_foundation'
            assert compare_metadata(MigrationContext.configure(c,opts={'compare_server_default':True}),Base.metadata)==[]
    finally:engine.dispose()


def test_creator_and_audit_immutable_and_evidence_refuses_downgrade(config):
    c=config;assert save(c).status_code==201
    with Session(c[0][1]) as s:
        row=s.scalar(select(SavedRequirement));row.created_at=c[0][4][0]
        # Ensure a distinct timestamp, even when clock equals the original.
        from datetime import timedelta
        row.created_at+=timedelta(seconds=1)
        with pytest.raises(IntegrityError):s.commit()
        s.rollback()
        audit=s.scalar(select(PlanningConfigurationEvent));audit.record_json={'tampered':True}
        with pytest.raises(IntegrityError):s.commit()
        s.rollback()
    with pytest.raises(DBAPIError):command.downgrade(migration_config(),'0015_recipe_schedule')
    with Session(c[0][1]) as s:
        assert s.scalar(text('SELECT version_num FROM alembic_version'))=='0025_notifications_foundation'
        assert 'tampered' not in s.scalar(select(PlanningConfigurationEvent)).record_json
