"""0015 roundtrip and durable evidence constraints, no development database."""
from sqlalchemy.engine import make_url
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError, IntegrityError
import pytest
from tests.integration.test_auth_public import env
from tests.integration.test_recipe_schedule import calendar, preview, commit_body, change
from scripts.dev import migration_config


def test_clean_0015_roundtrip_and_orm_columns_match(database_settings):
    from app.infrastructure.database.engine import create_database_engine
    from app.infrastructure.database.base import Base
    engine=create_database_engine(database_settings)
    try:
        with engine.connect() as c: assert c.scalar(text("SELECT current_database()")) == make_url(database_settings.database_url).database
        command.downgrade(migration_config(),"0014_operational_import")
        assert "recipe_schedule_changes" not in inspect(engine).get_table_names()
        assert "assigned" not in {c["name"] for c in inspect(engine).get_columns("recipes")}
        command.upgrade(migration_config(),"head")
        inspector=inspect(engine)
        for name in ("recipe_schedule_changes","recipe_schedule_request_receipts", "forecast_serving_identities", "model_serving_configurations", "planning_budgets", "planning_configuration_events", "planning_configuration_receipts", "planning_configuration_revisions", "planning_defaults", "saved_requirements","recipes"):
            columns={c["name"]:c for c in inspector.get_columns(name)}
            assert set(columns)==set(Base.metadata.tables[name].columns.keys())
            assert all(columns[c.name]["nullable"]==c.nullable for c in Base.metadata.tables[name].columns)
        with engine.connect() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version"))=="0024_integrate_import_auth"
    finally:engine.dispose()


def test_retained_proposal_receipt_audit_cannot_be_rewritten_or_downgraded(calendar):
    from uuid import UUID
    from app.models.recipe_schedule import RecipeScheduleChange
    c=calendar;p=preview(c);assert change(c,commit_body(p),p["schedule_version"]).status_code==200
    with Session(c[0][1]) as s:
        row=s.get(RecipeScheduleChange,UUID(p["change_id"]))
        row.audit_json={"tampered":True}
        with pytest.raises(IntegrityError):s.commit()
        s.rollback()
    with pytest.raises(DBAPIError):command.downgrade(migration_config(),"0014_operational_import")
    with Session(c[0][1]) as fresh:
        assert fresh.get(RecipeScheduleChange,UUID(p["change_id"])).audit_json["reason"]
        assert fresh.scalar(text("SELECT version_num FROM alembic_version"))=="0024_integrate_import_auth"
