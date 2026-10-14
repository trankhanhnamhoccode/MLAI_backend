"""Customer local runtime: explicit empty DB setup, own TLS and owned BE lifecycle."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from uuid import uuid4

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.engine import make_url
from psycopg import sql

from app.config import Settings
from app.infrastructure.planning_process import _birth
from scripts.dev import migration_config

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'runtime/local/private'
DB='shelfcash_local'
RUNTIME='shelfcash_local_runtime'
MIGRATOR='shelfcash_local_migrator'
TEST_DB='shelfcash_local_test'
TESTER='shelfcash_local_tester'
MARKER='ShelfCash customer self-service local v1'


class LocalRuntimeError(ValueError):
    """Deliberately secret-free operator-facing setup error."""
    pass


class LocalSettings(BaseSettings):
    model_config=SettingsConfigDict(env_file=ROOT/'.env',env_file_encoding='utf-8',extra='ignore')
    migration_database_url: SecretStr
    local_postgres_container: str='shelfcash-local-postgres-1'
    postgres_user: str='shelfcash_local_admin'
    postgres_port: int=5433
    local_port: int=8103
    local_smoke_recipient: str|None=None


def configuration():
    app,local=Settings(),LocalSettings()
    validate(app,local)
    return app,local


def validate(app,local):
    for value,db,role in ((app.database_url,DB,RUNTIME),(app.test_database_url,TEST_DB,TESTER),
                         (local.migration_database_url.get_secret_value(),DB,MIGRATOR)):
        url=make_url(value)
        if (url.drivername,url.host,url.port,url.database,url.username)!=('postgresql+psycopg','127.0.0.1',local.postgres_port,db,role) or url.query or not url.password or 'CHANGE_ME' in url.password:
            raise LocalRuntimeError('Use exact local database/role URLs with private passwords; run secrets after copying .env.example')
    if app.environment!='development' or app.auth_dev_cookie or not app.auth_allowed_origins or any(not origin.startswith('https://') for origin in app.auth_allowed_origins):
        raise LocalRuntimeError('Local browser runtime requires development, HTTPS cookies and exact HTTPS Origins')
    if not 1024<=local.local_port<=65535:raise LocalRuntimeError('Invalid local port')
    for path in (app.runtime_directory,app.upload_directory,app.model_artifact_directory):
        if not path.resolve().is_relative_to((ROOT/'runtime/local').resolve()):
            raise LocalRuntimeError('Local runtime storage must belong to this checkout under runtime/local')


def engine(url):return create_engine(url,connect_args={'connect_timeout':5})


def guard(connection,db,role):
    if tuple(connection.execute(text('SELECT current_database(),current_user')).one())!=(db,role):raise LocalRuntimeError('Connected identity mismatch')
    marker=connection.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
    if marker!=MARKER:raise LocalRuntimeError('Owned local database marker required')
    flags=connection.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
    if any(flags):raise LocalRuntimeError('Limited database role required')


def save(name,value):
    PRIVATE.mkdir(parents=True,exist_ok=True)
    target=PRIVATE/name;temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(target)


def prepare_secrets():
    """Generate placeholders into the ignored file, never stdout or Git."""
    from dotenv import dotenv_values
    path=ROOT/'.env'
    if not path.exists():shutil.copy2(ROOT/'.env.example',path)
    values=dotenv_values(path);updates={}
    for key in ('DATABASE_URL','TEST_DATABASE_URL','MIGRATION_DATABASE_URL'):
        value=values.get(key)
        if value and 'CHANGE_ME' in (make_url(value).password or ''):
            updates[key]=make_url(value).set(password=secrets.token_urlsafe(32)).render_as_string(hide_password=False)
    if not values.get('AUTH_DELIVERY_ENCRYPTION_KEY'):updates['AUTH_DELIVERY_ENCRYPTION_KEY']=base64.b64encode(secrets.token_bytes(32)).decode()
    if values.get('POSTGRES_PASSWORD')=='CHANGE_ME':updates['POSTGRES_PASSWORD']=secrets.token_urlsafe(32)
    if updates:
        backup=ROOT.parent/'.shelfcash-private-backups'/('local-env-'+str(uuid4()));backup.mkdir(parents=True)
        shutil.copy2(path,backup/'.env')
        lines=[line for line in path.read_text(encoding='utf-8').splitlines() if line.split('=',1)[0].strip() not in updates]
        lines.extend(key+'='+json.dumps(value) for key,value in updates.items())
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Private local secrets prepared; existing real values retained. Configure SMTP/callbacks locally; no secrets printed.')


def admin(local,statement,db='postgres'):
    result=subprocess.run(['docker','exec','-i',local.local_postgres_container,'psql','-X','-v','ON_ERROR_STOP=1','-U',local.postgres_user,'-d',db,'-At'],input=statement,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:raise RuntimeError('Local PostgreSQL admin command failed; check container/admin identity privately')
    return result.stdout.strip()


def docker_start():
    _,local=configuration()
    found=subprocess.run(['docker','inspect',local.local_postgres_container],capture_output=True,text=True)
    if found.returncode==0:
        subprocess.run(['docker','start',local.local_postgres_container],check=True,stdout=subprocess.DEVNULL)
        print('Existing configured PostgreSQL container started; volume/credentials retained.');return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',local.postgres_port))==0:raise LocalRuntimeError('PostgreSQL port occupied; configure the existing instance, no second Compose')
    if local.local_postgres_container!='shelfcash-local-postgres-1':raise LocalRuntimeError('Configured existing container not found')
    subprocess.run(['docker','compose','--env-file','.env','-f','compose.local.yaml','up','-d','--wait'],cwd=ROOT,check=True)


def init_db():
    app,local=configuration()
    targets=((DB,MIGRATOR,RUNTIME,make_url(app.database_url).password),
             (TEST_DB,TESTER,TESTER,make_url(app.test_database_url).password))
    for db,owner,role,password in targets:
        exists=admin(local,f"SELECT count(*) FROM pg_database WHERE datname={sql.Literal(db).as_string()}")=='1'
        if exists:
            marker=admin(local,f"SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname={sql.Literal(db).as_string()}")
            if marker!=MARKER:raise LocalRuntimeError('Existing database is not owned by this local setup; no changes')
            continue
        roles={owner:make_url(local.migration_database_url.get_secret_value()).password,role:password} if db==DB else {role:password}
        for name,secret in roles.items():
            if admin(local,f"SELECT count(*) FROM pg_roles WHERE rolname={sql.Literal(name).as_string()}")!='0':
                raise LocalRuntimeError('Existing role without owned DB; no credential overwrite')
            admin(local,f"SET log_statement='none'; SET log_min_duration_statement=-1; CREATE ROLE {sql.Identifier(name).as_string()} LOGIN PASSWORD {sql.Literal(secret).as_string()} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        admin(local,f'CREATE DATABASE {db} OWNER {owner}')
        admin(local,f"COMMENT ON DATABASE {db} IS {sql.Literal(MARKER).as_string()}; REVOKE ALL ON DATABASE {db} FROM PUBLIC; GRANT CONNECT ON DATABASE {db} TO {role}")
        admin(local,f'REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO {role}',db)
    # Add only role-specific HBA rules, retaining pre-existing rule content and order.
    result=subprocess.run(['docker','exec',local.local_postgres_container,'cat','/var/lib/postgresql/data/pg_hba.conf'],capture_output=True,text=True,check=True)
    old=result.stdout;tag='# ShelfCash customer self-service local roles v1'
    if tag not in old:
        backup=ROOT.parent/'.shelfcash-private-backups'/('local-hba-'+str(uuid4()));backup.mkdir(parents=True)
        (backup/'pg_hba.conf').write_text(old,encoding='utf-8')
        rules=[tag]
        for db,roles in ((DB,(RUNTIME,MIGRATOR)),(TEST_DB,(TESTER,))):
            for role in roles:rules.extend([f'local {db} {role} scram-sha-256',f'local all {role} reject',f'host {db} {role} all scram-sha-256',f'host all {role} all reject'])
        changed=subprocess.run(['docker','exec','-i',local.local_postgres_container,'sh','-c','cat > /var/lib/postgresql/data/pg_hba.conf'],input='\n'.join(rules)+'\n'+old,text=True,capture_output=True)
        if changed.returncode:raise RuntimeError('Local HBA update failed; backup retained')
        admin(local,'SELECT pg_reload_conf()')
    for url,db,role in ((app.database_url,DB,RUNTIME),(app.test_database_url,TEST_DB,TESTER),(local.migration_database_url.get_secret_value(),DB,MIGRATOR)):
        db_engine=engine(url)
        try:
            with db_engine.connect() as connection:guard(connection,db,role)
        finally:db_engine.dispose()
    print('Owned local and test databases/limited roles prepared; existing DBs unchanged. No account/Store/business seed or reset.')


def migrate(*,upgrade=False):
    from alembic import command
    from alembic.script import ScriptDirectory
    app,local=configuration();db_engine=engine(local.migration_database_url.get_secret_value())
    try:
        with db_engine.connect() as connection:
            guard(connection,DB,MIGRATOR)
            if inspect(connection).has_table('alembic_version') and not upgrade:
                raise LocalRuntimeError('Existing schema: use the backup-aware upgrade command, not first-time migrate')
            if upgrade:
                verify_backup(connection)
    finally:db_engine.dispose()
    graph=ScriptDirectory.from_config(migration_config())
    if len(graph.get_heads())!=1:raise LocalRuntimeError('Single reviewed migration head required')
    previous=os.environ.get('DATABASE_URL')
    try:
        os.environ['DATABASE_URL']=local.migration_database_url.get_secret_value()
        command.upgrade(migration_config(),'head')
    finally:
        if previous is None:os.environ.pop('DATABASE_URL',None)
        else:os.environ['DATABASE_URL']=previous
    admin(local,f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME}; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME}; ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR} IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {RUNTIME}',DB)
    print('Local database migrated with separate migrator; runtime remains limited. No seed.')


def counts(connection):
    return {name:connection.scalar(text('SELECT count(*) FROM '+connection.dialect.identifier_preparer.quote_identifier(name))) for name in inspect(connection).get_table_names(schema='public')}


def quiescent(connection):
    if (PRIVATE/'server.json').exists() and _birth(json.loads((PRIVATE/'server.json').read_text())['pid'])[0]!='DEAD':
        raise LocalRuntimeError('Stop the owned local BE before upgrade')
    tables=set(inspect(connection).get_table_names(schema='public'))
    for table in ('import_jobs','planning_runs','planning_exports'):
        if table in tables and connection.scalar(text(f"SELECT count(*) FROM {table} WHERE status IN ('queued','running')")):
            raise LocalRuntimeError('Complete pending/running work before upgrade')


def backup():
    app,local=configuration();db_engine=engine(app.database_url)
    try:
        with db_engine.connect() as connection:
            guard(connection,DB,RUNTIME);quiescent(connection);before=counts(connection)
    finally:db_engine.dispose()
    destination=ROOT.parent/'.shelfcash-private-backups'/('customer-local-'+str(uuid4()));destination.mkdir(parents=True)
    dump=destination/'shelfcash_local.dump'
    with dump.open('wb') as out:
        result=subprocess.run(['docker','exec',local.local_postgres_container,'pg_dump','-U',local.postgres_user,'-d',DB,'-Fc'],stdout=out,stderr=subprocess.PIPE)
    if result.returncode or dump.stat().st_size<100:raise RuntimeError('Local backup failed')
    checked=subprocess.run(['docker','exec','-i',local.local_postgres_container,'pg_restore','--file=/dev/null'],input=dump.read_bytes(),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    if checked.returncode:raise RuntimeError('Backup payload verification failed')
    shutil.copy2(ROOT/'.env',destination/'.env')
    shutil.copytree(PRIVATE,destination/'private',ignore=shutil.ignore_patterns('server.log'))
    save('upgrade-backup.json',dict(database=DB,counts=before,dump=str(dump),sha256=hashlib.sha256(dump.read_bytes()).hexdigest()))
    print('Local custom backup, full payload and SHA256 verified; private config retained outside Git.')


def verify_backup(connection):
    guard(connection,DB,MIGRATOR);quiescent(connection)
    saved=json.loads((PRIVATE/'upgrade-backup.json').read_text());dump=Path(saved['dump'])
    if saved['database']!=DB or not dump.is_file() or hashlib.sha256(dump.read_bytes()).hexdigest()!=saved['sha256'] or counts(connection)!=saved['counts']:
        raise LocalRuntimeError('An intact backup matching current database state is required')


def upgrade():
    migrate(upgrade=True)
    app,_=configuration();db_engine=engine(app.database_url)
    try:
        with db_engine.connect() as connection:
            after=counts(connection)
            before=json.loads((PRIVATE/'upgrade-backup.json').read_text())['counts']
            if any(after.get(name)!=value for name,value in before.items() if name!='alembic_version'):
                raise LocalRuntimeError('Pre-existing row counts changed; retain backup/evidence, no automatic downgrade')
    finally:db_engine.dispose()
    status()


def tls():
    from scripts.integrated_demo import certificate
    PRIVATE.mkdir(parents=True,exist_ok=True);certificate(PRIVATE)
    print('Own localhost TLS certificate prepared; trust runtime/local/private/localhost.cer once. No other worktree certificate used.')


def source():
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():raise LocalRuntimeError('Start requires clean committed source')
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def profile_digest(app,local):
    def encode(value):
        return value.get_secret_value() if isinstance(value,SecretStr) else str(value)
    return hashlib.sha256(json.dumps([app.model_dump(),local.model_dump()],sort_keys=True,default=encode).encode()).hexdigest()


def status():
    from alembic.script import ScriptDirectory
    from app.infrastructure.database.base import Base
    import app.models
    app,local=configuration();db_engine=engine(app.database_url)
    try:
        with db_engine.connect() as connection:
            guard(connection,DB,RUNTIME)
            revisions=list(connection.scalars(text('SELECT version_num FROM alembic_version')))
            expected=ScriptDirectory.from_config(migration_config()).get_heads()
            if revisions!=expected or len(inspect(connection).get_table_names())!=len(Base.metadata.tables)+1:raise LocalRuntimeError('DB head/schema differs from source')
    finally:db_engine.dispose()
    from app.infrastructure.email_verification_transport import VerificationEmailTransport
    from app.infrastructure.invitation_email import InvitationEmailTransport
    result=dict(database=DB,role=RUNTIME,revisions=revisions,tables=len(Base.metadata.tables)+1,server='stopped',
        api=f'https://localhost:{local.local_port}',origins=app.auth_allowed_origins,email_enabled=app.auth_email_delivery_enabled,
        email_capabilities=dict(verification=VerificationEmailTransport(app).available,reset=VerificationEmailTransport(app,purpose='RESET').available,invitation=InvitationEmailTransport(app).available))
    if (PRIVATE/'server.json').exists():
        owned=json.loads((PRIVATE/'server.json').read_text());state,birth=_birth(owned['pid'])
        if state=='ALIVE' and birth==owned['birth']:
            workers=json.loads((PRIVATE/'workers.json').read_text())
            if workers['run_id']!=owned['run_id'] or time.time()-workers['observed_at']>10:raise LocalRuntimeError('Worker observation stale')
            result.update(server='running',source_sha=owned['source_sha'],source_root=owned['source_root'],
                configuration_matches=workers.get('profile_digest')==profile_digest(app,local),
                workers={key:value for key,value in workers.items() if key!='profile_digest'})
        elif state!='DEAD':raise LocalRuntimeError('Unknown process incarnation')
    print(json.dumps(result));return result


def serve(run_id):
    import uvicorn
    from app.main import create_app
    app,local=configuration();application=create_app(app)
    server=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=local.local_port,
        ssl_keyfile=str(PRIVATE/'localhost.key'),ssl_certfile=str(PRIVATE/'localhost.pem'),access_log=False))
    finished=threading.Event()
    def watch():
        while not finished.wait(.5):
            if server.started:
                names={t.name for t in threading.enumerate() if t.is_alive()}
                save('workers.json',dict(run_id=run_id,observed_at=time.time(),database=DB,profile_digest=profile_digest(app,local),
                    threads={name:name in names for name in ('shelfcash-import','shelfcash-planning','shelfcash-pdf-export','shelfcash-notifications','email-verification')}))
            if (PRIVATE/'stop.json').exists() and json.loads((PRIVATE/'stop.json').read_text())['run_id']==run_id:
                server.should_exit=True;return
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    try:server.run()
    finally:
        finished.set();thread.join(timeout=2);save('exit.json',dict(run_id=run_id,stopped=True))


def start():
    app,local=configuration();sha=source();status()
    if (PRIVATE/'server.json').exists():
        owned=json.loads((PRIVATE/'server.json').read_text());state,birth=_birth(owned['pid'])
        if state=='ALIVE' and birth==owned['birth']:
            if owned['source_sha']!=sha or owned.get('profile_digest')!=profile_digest(app,local):raise LocalRuntimeError('Stop the owned old source/configuration snapshot before start')
            return
        if state!='DEAD':raise LocalRuntimeError('Unknown previous process; no replacement')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',local.local_port))==0:raise LocalRuntimeError('BE port occupied by another process; no replacement')
    context=ssl.create_default_context(cafile=str(PRIVATE/'localhost.pem'))
    run_id=str(uuid4())
    with (PRIVATE/'server.log').open('ab') as log:
        child=subprocess.Popen([sys.executable,'-m','scripts.local_runtime','serve','--run-id',run_id],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    state,birth=_birth(child.pid)
    if state!='ALIVE':raise LocalRuntimeError('Child identity unavailable')
    save('server.json',dict(pid=child.pid,birth=birth,run_id=run_id,source_sha=sha,source_root=str(ROOT),profile_digest=profile_digest(app,local)))
    required={'shelfcash-import':app.import_worker_enabled,'shelfcash-planning':app.planning_worker_enabled,'shelfcash-pdf-export':app.pdf_export_worker_enabled,'shelfcash-notifications':app.notification_worker_enabled,'email-verification':app.auth_email_delivery_enabled}
    for _ in range(100):
        if child.poll() is not None:raise RuntimeError('Owned server exited; inspect private server.log')
        try:
            with httpx.Client(verify=context,trust_env=False,timeout=2) as client:
                response=client.get(f'https://localhost:{local.local_port}/health')
            workers=json.loads((PRIVATE/'workers.json').read_text())
            if response.status_code==200 and workers['run_id']==run_id and workers['threads']==required and workers.get('profile_digest')==profile_digest(app,local):
                status();return
        except (httpx.HTTPError,FileNotFoundError):pass
        time.sleep(.2)
    raise RuntimeError('Readiness unverified; no second process launched')


def stop():
    if not (PRIVATE/'server.json').exists():print('No owned local server');return
    owned=json.loads((PRIVATE/'server.json').read_text());state,birth=_birth(owned['pid'])
    if state=='DEAD':print('Owned local server already stopped');return
    if state!='ALIVE' or birth!=owned['birth']:raise LocalRuntimeError('Stop refused: process incarnation mismatch')
    save('stop.json',dict(run_id=owned['run_id']))
    for _ in range(100):
        if _birth(owned['pid'])[0]=='DEAD':
            if json.loads((PRIVATE/'exit.json').read_text())['run_id']!=owned['run_id']:raise LocalRuntimeError('Exit ownership mismatch')
            print('Owned local BE/workers stopped; databases and data retained');return
        time.sleep(.2)
    raise RuntimeError('Graceful exit pending; no forced kill')


def smtp_smoke():
    """Explicit user-run single test message; setup/start never calls this."""
    import smtplib
    from email.message import EmailMessage
    from app.application.contracts.auth import canonical_email
    app,local=configuration()
    if not local.local_smoke_recipient or not app.auth_smtp_host or not app.auth_delivery_sender:
        raise LocalRuntimeError('Configure LOCAL_SMOKE_RECIPIENT, SMTP host and authorized sender privately')
    recipient=canonical_email(local.local_smoke_recipient)
    message=EmailMessage()
    message['From'],message['To'],message['Subject']=app.auth_delivery_sender,recipient,'ShelfCash local SMTP smoke'
    message.set_content('One explicit local SMTP smoke. No account, Store, token or business facts were created.')
    with smtplib.SMTP_SSL(app.auth_smtp_host,app.auth_smtp_port,context=ssl.create_default_context(),timeout=15) as smtp:
        if app.auth_smtp_username:smtp.login(app.auth_smtp_username,app.auth_smtp_password.get_secret_value() if app.auth_smtp_password else '')
        smtp.send_message(message)
    print('One configured SMTP test message accepted; inbox delivery and customer email workflow remain separate checks.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('secrets','docker','init-db','migrate','backup','upgrade','tls','start','status','stop','serve','smtp-smoke'))
    parser.add_argument('--run-id');args=parser.parse_args()
    try:
        if args.action=='serve':
            if not args.run_id:raise LocalRuntimeError('Run id required')
            serve(args.run_id)
        else:{'secrets':prepare_secrets,'docker':docker_start,'init-db':init_db,'migrate':migrate,'backup':backup,'upgrade':upgrade,'tls':tls,'start':start,'status':status,'stop':stop,'smtp-smoke':smtp_smoke}[args.action]()
        return 0
    except LocalRuntimeError as error:
        print(f'Local setup/runtime: {error}');return 1
    except Exception as error:
        print(f'Local setup/runtime failed ({type(error).__name__}); inspect target, .env and private logs. Raw secrets/errors withheld.');return 1


if __name__=='__main__':raise SystemExit(main())
