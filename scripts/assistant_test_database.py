"""Provision only the labeled assistant test container/DB; no existing instance.

No reset is implicit. Private credentials stay under ignored runtime. Tests/reset
use the ordinary scripts.dev target/limited-role guards after this provisioning.
"""
import json
import secrets
import subprocess
import time
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'runtime/assistant-test/private'
CONTAINER = 'shelfcash-assistant-test-postgres'
LABEL = 'shelfcash.assistant-test=owned-v1'
DATABASE = 'shelfcash_assistant_test'
ROLE = 'shelfcash_assistant_tester'
PORT = 5436


def provision():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    config = PRIVATE / 'credentials.json'
    probe = subprocess.run(['docker','inspect',CONTAINER],capture_output=True)
    if probe.returncode == 0:
        data = json.loads(probe.stdout)[0]
        if data['Config']['Labels'].get('shelfcash.assistant-test') != 'owned-v1' or not config.exists():
            raise RuntimeError('Refusing unowned container or absent private recovery credentials')
        if not data['State']['Running']: raise RuntimeError('Owned test container stopped; start explicitly')
        credentials = json.loads(config.read_text(encoding='utf-8'))
    else:
        subprocess.run(['docker','info','--format','{{.ServerVersion}}'],check=True,capture_output=True)
        volume=subprocess.run(['docker','volume','inspect','shelfcash-assistant-test-pgdata'],capture_output=True)
        if volume.returncode==0: raise RuntimeError('Preserved volume exists without owned container; reconcile explicitly')
        if config.exists(): raise RuntimeError('Preserved credentials exist without container; reconcile explicitly')
        credentials = {'admin':secrets.token_hex(32),'tester':secrets.token_hex(32)}
        config.write_text(json.dumps(credentials),encoding='utf-8')
        env = PRIVATE / 'postgres.env'
        env.write_text('POSTGRES_USER=assistant_test_admin\nPOSTGRES_DB='+DATABASE+'\nPOSTGRES_PASSWORD='+credentials['admin']+'\n',encoding='utf-8')
        subprocess.run(['docker','run','-d','--name',CONTAINER,'--label',LABEL,
            '--env-file',str(env),'-p',f'127.0.0.1:{PORT}:5432',
            '-v','shelfcash-assistant-test-pgdata:/var/lib/postgresql/data','postgres:17-bookworm'],
            check=True,capture_output=True)
    connection = None
    for _ in range(40):
        try:
            connection = psycopg.connect(host='127.0.0.1',port=PORT,dbname=DATABASE,
                user='assistant_test_admin',password=credentials['admin'],autocommit=True,connect_timeout=1)
            break
        except psycopg.OperationalError: time.sleep(.5)
    if connection is None: raise RuntimeError('Owned test PostgreSQL unavailable')
    with connection as c:
        if c.execute('SELECT current_database()').fetchone()[0] != DATABASE: raise RuntimeError('Wrong target')
        if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(ROLE,)).fetchone():
            c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(ROLE),sql.Literal(credentials['tester'])))
        c.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION {}').format(sql.Identifier(ROLE)))
        c.execute(sql.SQL('ALTER SCHEMA public OWNER TO {}').format(sql.Identifier(ROLE)))
        c.execute(sql.SQL('GRANT CONNECT, CREATE ON DATABASE {} TO {}').format(sql.Identifier(DATABASE),sql.Identifier(ROLE)))
        c.execute("COMMENT ON DATABASE shelfcash_assistant_test IS 'ShelfCash assistant disposable test v1'")
    url = URL.create('postgresql+psycopg',username=ROLE,password=credentials['tester'],host='127.0.0.1',port=PORT,database=DATABASE).render_as_string(hide_password=False)
    from app.config import Settings
    from scripts.dev import validate_reset_target
    validate_reset_target(Settings(_env_file=None,environment='test',database_url=url))
    with psycopg.connect(host='127.0.0.1',port=PORT,dbname=DATABASE,user=ROLE,password=credentials['tester']) as c:
        flags = c.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if any(flags): raise RuntimeError('Tester privileges are not limited')
    (PRIVATE/'test-url.txt').write_text(url,encoding='utf-8')
    print(f'READY {DATABASE} / {ROLE} at 127.0.0.1:{PORT}; credentials private; no reset')


if __name__ == '__main__': provision()
