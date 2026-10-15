"""Provision only the isolated F4 Compose instance; never another database host."""
import json
from pathlib import Path
import secrets
import subprocess
from sqlalchemy.engine import URL
from app.config import Settings
from scripts.dev import validate_reset_target

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'runtime/challenger/f4/private'


def main():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    env=PRIVATE/'compose.env'
    credentials=PRIVATE/'database.json'
    if env.exists() or credentials.exists():
        raise RuntimeError('Existing private setup is retained; inspect it instead of reprovisioning')
    password=secrets.token_hex(24)
    url=URL.create('postgresql+psycopg',username='shelfcash_challenger_tester',password=password,
                   host='127.0.0.1',port=5438,database='shelfcash_challenger_test').render_as_string(hide_password=False)
    validate_reset_target(Settings(_env_file=None,environment='test',database_url=url))
    # No credentials in command-line arguments or stdout.
    env.write_text('F4_POSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
    credentials.write_text(json.dumps({'url':url}))
    compose=['docker','compose','--env-file',str(env),'-f',str(ROOT/'compose.challenger.yaml')]
    subprocess.run([*compose,'up','-d','--wait'],check=True,capture_output=True,timeout=90)
    container=subprocess.check_output([*compose,'ps','-q','postgres'],text=True).strip()
    # This SQL runs exclusively inside the freshly created dedicated instance.
    sql=f"""CREATE ROLE shelfcash_challenger_tester LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE shelfcash_challenger_test OWNER shelfcash_challenger_tester;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
REVOKE CONNECT ON DATABASE shelfcash_challenger_test FROM PUBLIC;
GRANT CONNECT ON DATABASE shelfcash_challenger_test TO shelfcash_challenger_tester;
"""
    subprocess.run(['docker','exec','-i',container,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres'],
                   input=sql,text=True,capture_output=True,check=True,timeout=30)
    print('Provisioned isolated loopback5438 shelfcash_challenger_test / limited shelfcash_challenger_tester. Private URL retained locally.')


if __name__=='__main__':main()
