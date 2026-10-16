"""Run sequential pytest against the guarded dedicated F4 DB; no URL output."""
import json
import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine,text
from app.config import Settings
from scripts.dev import validate_reset_target

ROOT=Path(__file__).resolve().parents[1]


def main():
    url=json.loads((ROOT/'runtime/challenger/f4/private/database.json').read_text())['url']
    settings=Settings(_env_file=None,environment='test',database_url=url)
    validate_reset_target(settings)
    engine=create_engine(url)
    try:
        with engine.connect() as conn:
            database,user=conn.execute(text('SELECT current_database(),current_user')).one()
            assert database=='shelfcash_challenger_test' and user=='shelfcash_challenger_tester'
            assert not conn.scalar(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user'))
            assert not conn.scalar(text("SELECT bool_or(has_database_privilege(current_user,oid,'CONNECT')) FROM pg_database WHERE datname!=current_database() AND datallowconn"))
    finally:engine.dispose()
    env=os.environ.copy()
    env.update(TEST_DATABASE_URL=url,DATABASE_URL=url,ENVIRONMENT='test',PYTHONDONTWRITEBYTECODE='1')
    for name in ('IMPORT_WORKER_ENABLED','PLANNING_WORKER_ENABLED','PDF_EXPORT_WORKER_ENABLED','NOTIFICATION_WORKER_ENABLED',
                 'IMPORT_LLM_SUGGESTIONS_ENABLED','AUTH_EMAIL_DELIVERY_ENABLED'):env[name]='false'
    result=subprocess.run([sys.executable,'-B','-m','pytest',*sys.argv[1:]],cwd=ROOT,env=env)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
