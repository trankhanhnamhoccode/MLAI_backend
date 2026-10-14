"""Minimal additive migration, historical rows preserved, downgrade guarded."""
from sqlalchemy.engine import make_url
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect,text
from sqlalchemy.orm import Session
import pytest
from tests.integration.test_planning_exports import exports,flow,config,env,export
from tests.integration.test_planning_public import submit
from app.models import PlanningRun,PlanningExport
from app.infrastructure.database.base import Base
from scripts.dev import migration_config,validate_reset_target


def test_additive_roundtrip_preserves_actual_historical_run_and_protects_export(exports, test_database_url):
    flow,svc=exports;c,_,_,worker=flow;validate_reset_target(c[0][0])
    response=submit(c);record=worker.run_one();assert record.status=='completed'
    with Session(c[0][1]) as s:
        assert s.scalar(text('SELECT current_database()')) == make_url(test_database_url).database
        before=s.get(PlanningRun,record.run_id).record_json
    command.downgrade(migration_config(),'0016_planning_configuration')
    assert 'planning_exports' not in inspect(c[0][1]).get_table_names()
    command.upgrade(migration_config(),'head')
    with Session(c[0][1]) as s:
        assert s.get(PlanningRun,record.run_id).record_json==before and s.query(PlanningExport).count()==0
    with c[0][1].connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn,opts={'compare_server_default':True}),Base.metadata)==[]
    accepted=export(c,response.headers['Location']);assert accepted.status_code==202,accepted.text
    with pytest.raises(RuntimeError,match='Refusing downgrade'):command.downgrade(migration_config(),'0016_planning_configuration')
    with Session(c[0][1]) as s:
        assert s.scalar(text('SELECT version_num FROM alembic_version'))=='0026_collaboration_requests'
        assert s.query(PlanningExport).count()==1 and s.get(PlanningRun,record.run_id).record_json==before
