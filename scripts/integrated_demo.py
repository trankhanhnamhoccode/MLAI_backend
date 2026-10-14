"""BE-only integrated HTTPS demo; never resets data or sends real email.

Private credentials/configuration live in ignored runtime; .env selects runtime DB.
Provisioning uses the existing Docker PostgreSQL instance, not another Compose.
"""
from __future__ import annotations

import argparse
import hashlib
import base64
from datetime import datetime, timedelta, timezone
import ipaddress
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
from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'runtime/integrated-demo/private'
DB = 'shelfcash_integration_demo'
ROLE = 'shelfcash_integration_demo_runtime'
MIGRATOR = 'shelfcash_integration_demo_migrator'
CONTAINER = 'shelfcash-integration-s411-postgres-1'
ADMIN = 'shelfcash_integration'
MARKER = 'ShelfCash integrated HTTPS demo v1'
ORIGIN = 'https://localhost:5173'
URL = 'https://localhost:8103'


def source_identity() -> dict:
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise ValueError('Demo requires a committed clean source snapshot')
    return dict(source_root=str(ROOT), source_sha=result.stdout.strip())


def migration_head() -> str:
    from alembic.script import ScriptDirectory
    from scripts.dev import migration_config
    heads = ScriptDirectory.from_config(migration_config()).get_heads()
    if len(heads) != 1:
        raise ValueError('A single reviewed migration head is required')
    return heads[0]


def schema_counts(engine) -> dict:
    with engine.connect() as connection:
        return {name: connection.scalar(text('SELECT count(*) FROM public.' + '"' + name.replace('"', '""') + '"'))
                for name in inspect(connection).get_table_names(schema='public')}


def quiescent(engine) -> None:
    from app.infrastructure.planning_process import _birth
    state_path = PRIVATE / 'server.json'
    if state_path.exists() and _birth(json.loads(state_path.read_text())['pid'])[0] != 'DEAD':
        raise ValueError('Stop the owned demo before migration')
    with engine.connect() as connection:
        tables=set(inspect(connection).get_table_names(schema='public'))
        for table in ('import_jobs', 'planning_runs', 'planning_exports'):
            if table in tables and connection.scalar(text(f"SELECT count(*) FROM {table} WHERE status IN ('queued','running')")):
                raise ValueError('Pending demo work requires controlled completion before upgrade')


def backup_upgrade() -> None:
    """Back up this owned DB and private configuration without resetting any target."""
    s=settings(); engine=create_engine(s.database_url)
    try:
        guard(engine,ROLE)
        counts=schema_counts(engine)
        with engine.connect() as connection:
            revisions=list(connection.scalars(text('SELECT version_num FROM alembic_version'))) if 'alembic_version' in counts else []
        destination=ROOT.parent/'.shelfcash-private-backups'/('demo-before-upgrade-'+str(uuid4()))
        destination.mkdir(parents=True)
        dump=destination/'shelfcash_integration_demo.dump'
        with dump.open('wb') as output:
            result=subprocess.run(['docker','exec',CONTAINER,'pg_dump','-U',ADMIN,'-d',DB,'--format=custom'],
                                  stdout=output,stderr=subprocess.PIPE)
        if result.returncode or dump.stat().st_size < 100:
            raise RuntimeError('Demo database backup failed; migration forbidden')
        verified=subprocess.run(['docker','exec','-i',CONTAINER,'pg_restore','--list'],input=dump.read_bytes(),capture_output=True)
        if verified.returncode or (counts and b'TABLE DATA' not in verified.stdout) or not verified.stdout.strip():
            raise RuntimeError('Demo backup archive verification failed')
        payload=subprocess.run(['docker','exec','-i',CONTAINER,'pg_restore','--file=/dev/null'],
                               input=dump.read_bytes(),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        if payload.returncode:
            raise RuntimeError('Demo backup payload verification failed')
        shutil.copy2(ROOT/'.env',destination/'.env')
        config=destination/'private';config.mkdir()
        for path in PRIVATE.iterdir():
            if path.is_file() and path.suffix in {'.json','.pem','.key','.cer'}:
                shutil.copy2(path,config/path.name)
        manifest=dict(database=DB,revisions=revisions,counts=counts,dump=str(dump),
                      sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),**source_identity())
        (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        private_json('upgrade-backup.json',manifest)
        print('Owned demo backup verified: custom archive/TOC/SHA-256, schema row counts and private configuration retained outside Git.')
    finally: engine.dispose()


def check_upgrade_backup(engine) -> dict:
    saved=json.loads((PRIVATE/'upgrade-backup.json').read_text())
    dump=Path(saved['dump'])
    if (saved['database']!=DB or not dump.is_file() or
            hashlib.sha256(dump.read_bytes()).hexdigest()!=saved['sha256'] or schema_counts(engine)!=saved['counts']):
        raise ValueError('Verified unchanged demo backup required before upgrade')
    return saved


def private_json(name: str, value: object) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def backup(path: Path) -> None:
    if path.exists():
        destination = ROOT.parent / '.shelfcash-private-backups' / ('integrated-demo-' + str(uuid4()))
        destination.mkdir(parents=True)
        shutil.copy2(path, destination / path.name)


def validate(s: Settings, *, migration: bool = False) -> None:
    u = make_url(s.database_url)
    expected = MIGRATOR if migration else ROLE
    if (u.drivername, u.host, u.port, u.database, u.username) != (
        'postgresql+psycopg', '127.0.0.1', 5433, DB, expected
    ) or u.query:
        raise ValueError('Exact demo database identity required')
    test = make_url(s.test_database_url)
    if (test.database, test.username) != ('shelfcash_integration_test', 'shelfcash_integration_tester'):
        raise ValueError('Dedicated integration TEST_DATABASE_URL must be preserved')
    if s.environment != 'development' or s.auth_dev_cookie or s.auth_allowed_origins != [ORIGIN]:
        raise ValueError('HTTPS cookie/exact Origin configuration required')
    if s.auth_email_delivery_enabled or s.import_llm_suggestions_enabled or s.openrouter_api_key or s.openrouter_model:
        raise ValueError('Real email and provider must remain disabled in this profile')
    for actual, suffix in ((s.runtime_directory, 'app'), (s.upload_directory, 'app/uploads'),
                           (s.model_artifact_directory, 'app/models')):
        if actual.resolve() != (PRIVATE / suffix).resolve():
            raise ValueError('Owned runtime storage required')


def settings() -> Settings:
    s = Settings()
    validate(s)
    return s


def guard(engine, role: str) -> None:
    with engine.connect() as c:
        if tuple(c.execute(text('SELECT current_database(),current_user')).one()) != (DB, role):
            raise ValueError('Connected demo identity mismatch')
        marker = c.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
        if marker != MARKER:
            raise ValueError('Owned database marker required')
        owner = c.scalar(text('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()'))
        flags = c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
        if owner != MIGRATOR or any(flags):
            raise ValueError('Separate limited migration/runtime roles required')


def admin_sql(statement: str, database: str = 'postgres') -> str:
    result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                             '-U', ADMIN, '-d', database, '-At'], input=statement,
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Docker SQL failed; raw output withheld')
    return result.stdout.strip()


def certificate() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    if (PRIVATE / 'localhost.pem').exists() or (PRIVATE / 'localhost.key').exists():
        if not all((PRIVATE / f).exists() for f in ('localhost.pem', 'localhost.key')):
            raise ValueError('Incomplete TLS key/certificate; no overwrite')
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ShelfCash integrated localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
            .not_valid_after(now+timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    (PRIVATE/'localhost.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (PRIVATE/'localhost.key').chmod(0o600)
    (PRIVATE/'localhost.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (PRIVATE/'localhost.cer').write_bytes(cert.public_bytes(serialization.Encoding.DER))


def init() -> None:
    # Reject an unrelated worktree/test profile before any Docker/DB mutation.
    env_path = ROOT / '.env'
    existing = Settings()
    test = make_url(existing.test_database_url)
    if not env_path.exists() or (test.database, test.username) != (
        'shelfcash_integration_test', 'shelfcash_integration_tester'
    ):
        raise ValueError('Ignored .env with dedicated integration test configuration required')
    # Reserve credentials before DDL so failed/partial setup is recoverable.
    credentials = PRIVATE / 'database.json'
    if not credentials.exists():
        if admin_sql(f"SELECT count(*) FROM pg_database WHERE datname='{DB}'") != '0':
            raise ValueError('Existing demo DB without private ownership credentials; no overwrite')
        if admin_sql(f"SELECT count(*) FROM pg_roles WHERE rolname IN ('{ROLE}','{MIGRATOR}')") != '0':
            raise ValueError('Existing roles without ownership credentials; no overwrite')
        private_json('database.json', {ROLE: secrets.token_urlsafe(32), MIGRATOR: secrets.token_urlsafe(32)})
    passwords = json.loads(credentials.read_text())
    for role in (ROLE, MIGRATOR):
        if admin_sql(f"SELECT count(*) FROM pg_roles WHERE rolname='{role}'") == '0':
            literal = sql.Literal(passwords[role]).as_string()
            admin_sql(f"SET log_statement='none'; SET log_min_duration_statement=-1; CREATE ROLE {role} LOGIN PASSWORD {literal} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;")
    if admin_sql(f"SELECT count(*) FROM pg_database WHERE datname='{DB}'") == '0':
        admin_sql(f'CREATE DATABASE {DB} OWNER {MIGRATOR};')
        admin_sql(f"COMMENT ON DATABASE {DB} IS '{MARKER}'; REVOKE ALL ON DATABASE {DB} FROM PUBLIC; GRANT CONNECT ON DATABASE {DB} TO {ROLE};")
        admin_sql(f'REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO {ROLE};', DB)
    elif admin_sql(f"SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='{DB}'") != MARKER:
        raise ValueError('Existing unowned database; no migration or overwrite')
    # Scope new roles before all existing trust/SCRAM rules, preserving those rules.
    result = subprocess.run(['docker','exec',CONTAINER,'cat','/var/lib/postgresql/data/pg_hba.conf'], capture_output=True,text=True,check=True)
    old = result.stdout
    tag = '# ShelfCash integrated demo role boundary v1'
    if tag not in old:
        backup_dir = ROOT.parent / '.shelfcash-private-backups' / ('integrated-demo-hba-' + str(uuid4()))
        backup_dir.mkdir(parents=True)
        (backup_dir/'pg_hba.conf').write_text(old, encoding='utf-8')
        rules = [tag]
        for role in (ROLE,MIGRATOR):
            rules += [f'local {DB} {role} scram-sha-256', f'local all {role} reject',
                      f'host {DB} {role} all scram-sha-256', f'host all {role} all reject']
        result = subprocess.run(['docker','exec','-i',CONTAINER,'sh','-c','cat > /var/lib/postgresql/data/pg_hba.conf'],
                                input='\n'.join(rules)+'\n'+old,text=True,capture_output=True)
        if result.returncode: raise RuntimeError('HBA update failed')
        admin_sql('SELECT pg_reload_conf();')
    values = dict(environment='development', database_url=f'postgresql+psycopg://{ROLE}:{passwords[ROLE]}@127.0.0.1:5433/{DB}',
        runtime_directory=str(PRIVATE/'app'),upload_directory=str(PRIVATE/'app/uploads'),model_artifact_directory=str(PRIVATE/'app/models'),
        auth_allowed_origins=[ORIGIN],auth_dev_cookie=False,import_worker_enabled=True,planning_worker_enabled=True,
        pdf_export_worker_enabled=True,notification_worker_enabled=True,auth_email_delivery_enabled=False,import_llm_suggestions_enabled=False,
        openrouter_api_key=None,openrouter_model=None,auth_frontend_url=ORIGIN+'/credentials/complete',
        auth_password_reset_frontend_url=ORIGIN+'/credentials/complete',auth_invitation_frontend_url=None,
        auth_verification_frontend_url=None)
    saved_path = PRIVATE/'profile.json'
    if saved_path.exists():
        saved=json.loads(saved_path.read_text())
        values.update({k:saved[k] for k in ('auth_operator_id','auth_operator_key','auth_delivery_encryption_key')})
    else:
        values.update(auth_operator_id='integrated-demo-local',auth_operator_key=secrets.token_urlsafe(32),
            auth_delivery_encryption_key=base64.b64encode(secrets.token_bytes(32)).decode())
    private_json('profile.json', values)
    # Reuse only SMTP settings from the already approved local Auth profile.
    # Dispatch remains OFF; invitation/verification callbacks are unresolved.
    from dotenv import dotenv_values
    smtp_source=ROOT.parent/'backend-auth-self-service/.env'
    if smtp_source.exists():
        source=dotenv_values(smtp_source)
        for key in ('AUTH_SMTP_HOST','AUTH_SMTP_PORT','AUTH_SMTP_USERNAME','AUTH_SMTP_PASSWORD','AUTH_DELIVERY_SENDER'):
            if not getattr(existing,key.lower()) and source.get(key):
                values[key.lower()]=source[key]
    lines=env_path.read_text(encoding='utf-8').splitlines()
    keys={k.upper() for k in values}
    kept=[line for line in lines if line.split('=',1)[0].strip().upper() not in keys]
    for k,v in values.items():
        value=env_value(v)
        kept.append(k.upper()+'='+value)
    backup(env_path)
    env_path.write_text('\n'.join(kept)+'\n',encoding='utf-8')
    env_path.chmod(0o600)
    certificate()
    settings()
    print('Private demo configuration prepared; original DB/roles preserved. Run migrate explicitly.')


def env_value(value: object) -> str:
    """Quote strings (including Windows paths/SMTP values) for dotenv parsing."""
    if value is None:
        return ''
    return json.dumps(value, ensure_ascii=False)


def migrate() -> None:
    from scripts.dev import migration_config
    from alembic import command
    identity=source_identity()
    s=settings()
    passwords=json.loads((PRIVATE/'database.json').read_text())
    migration_url=make_url(s.database_url).set(username=MIGRATOR,password=passwords[MIGRATOR]).render_as_string(hide_password=False)
    migration_s=s.model_copy(update={'database_url':migration_url})
    validate(migration_s,migration=True)
    engine=create_engine(migration_url)
    try:
        guard(engine,MIGRATOR)
        quiescent(engine)
        saved=check_upgrade_backup(engine)
        if saved.get('source_sha')!=identity['source_sha'] or saved.get('source_root')!=identity['source_root']:
            raise ValueError('Backup must belong to the current committed demo source')
        from alembic.script import ScriptDirectory
        graph=ScriptDirectory.from_config(migration_config())
        ancestors={r.revision for r in graph.walk_revisions()}
        if not set(saved['revisions'])<=ancestors:
            raise ValueError('Unrecognized demo revision; upgrade forbidden')
        target=migration_head()
    finally: engine.dispose()
    previous={k:os.environ.get(k) for k in ('DATABASE_URL','ENVIRONMENT')}
    try:
        os.environ.update(DATABASE_URL=migration_url,ENVIRONMENT='development')
        command.upgrade(migration_config(),target)
    finally:
        for k,v in previous.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v
    admin_sql(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE}; ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR} IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {ROLE}; ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR} IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO {ROLE};',DB)
    engine=create_engine(s.database_url)
    try:
        after=schema_counts(engine)
        if any(after.get(name)!=count for name,count in saved['counts'].items() if name!='alembic_version'):
            raise ValueError('Pre-existing demo row counts changed; retain backup/evidence, no automatic downgrade')
    finally: engine.dispose()
    status()


def db_status() -> dict:
    s=settings(); engine=create_engine(s.database_url)
    try:
        guard(engine,ROLE)
        with engine.connect() as c:
            revisions=list(c.scalars(text('SELECT version_num FROM alembic_version')))
            tables=len(inspect(c).get_table_names(schema='public'))
            flags=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
            from app.infrastructure.database.base import Base
            import app.models  # Register the source schema without connecting elsewhere.
            if revisions!=[migration_head()] or tables!=len(Base.metadata.tables)+1 or any(flags): raise ValueError('Demo head/schema/role guard failed')
            return dict(database=DB,role=ROLE,revisions=revisions,tables=tables)
    finally: engine.dispose()


def context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(PRIVATE/'localhost.pem'))


def status() -> None:
    result=db_status()
    path=PRIVATE/'server.json'
    result['server']='stopped'
    if path.exists():
        owned=json.loads(path.read_text())
        from app.infrastructure.planning_process import _birth
        state,birth=_birth(owned['pid'])
        if state=='ALIVE' and birth==owned['birth']:
            result['server']='running'
            result.update({key:owned.get(key) for key in ('source_root','source_sha')})
            result['workers']=json.loads((PRIVATE/'workers.json').read_text())
            if result['workers']['run_id'] != owned['run_id'] or time.time()-result['workers']['observed_at'] > 10:
                raise ValueError('Worker observation stale or belongs to another incarnation')
        elif state!='DEAD': raise ValueError('Server incarnation unknown; no replacement')
    print(json.dumps(result))


def serve(run_id: str) -> None:
    import uvicorn
    from app.main import create_app
    db_status(); s=settings(); application=create_app(s)
    server=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=8103,
        ssl_keyfile=str(PRIVATE/'localhost.key'),ssl_certfile=str(PRIVATE/'localhost.pem'),access_log=False))
    finished=threading.Event()
    def watch():
        while not finished.wait(.5):
            if server.started:
                threads={t.name for t in threading.enumerate() if t.is_alive()}
                private_json('workers.json', dict(run_id=run_id, observed_at=time.time(), import_alive='shelfcash-import' in threads,
                    planning_alive='shelfcash-planning' in threads,pdf_alive='shelfcash-pdf-export' in threads,
                    notification_alive='shelfcash-notifications' in threads,
                    email_enabled=False,database=DB,runtime=str(s.runtime_directory)))
            stop=PRIVATE/'stop.json'
            if stop.exists() and json.loads(stop.read_text())['run_id']==run_id:
                server.should_exit=True; return
    watcher=threading.Thread(target=watch,daemon=True); watcher.start()
    try: server.run()
    finally:
        finished.set(); watcher.join(timeout=2)
        private_json('server-exit.json',dict(run_id=run_id,stopped=True))


def start() -> None:
    db_status()
    identity=source_identity()
    from app.infrastructure.planning_process import _birth
    path=PRIVATE/'server.json'
    if path.exists():
        owned=json.loads(path.read_text()); state,birth=_birth(owned['pid'])
        if state=='ALIVE' and birth==owned['birth']:
            if any(owned.get(key)!=value for key,value in identity.items()):
                raise ValueError('Owned demo runs another source snapshot; stop before starting the new commit')
            status(); return
        if state!='DEAD': raise ValueError('Previous incarnation unknown; no replacement')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',8103))==0: raise ValueError('Port8103 occupied; no replacement')
    run_id=str(uuid4())
    with (PRIVATE/'server.log').open('ab') as log:
        process=subprocess.Popen([sys.executable,'-m','scripts.integrated_demo','serve','--run-id',run_id],cwd=ROOT,
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    state,birth=_birth(process.pid)
    if state!='ALIVE': raise RuntimeError('Child identity unavailable')
    private_json('server.json',dict(pid=process.pid,birth=birth,run_id=run_id,**identity))
    for _ in range(100):
        if process.poll() is not None: raise RuntimeError('Owned child exited; inspect private log')
        try:
            with httpx.Client(verify=context(),trust_env=False) as client:
                if client.get(URL+'/health').status_code==200 and (PRIVATE/'workers.json').exists():
                    workers=json.loads((PRIVATE/'workers.json').read_text())
                    if workers['run_id']==run_id and all(workers[k] for k in ('import_alive','planning_alive','pdf_alive','notification_alive')):
                        status(); return
        except httpx.HTTPError: pass
        time.sleep(.2)
    raise RuntimeError('Runtime readiness unverified; no second process launched')


def stop() -> None:
    from app.infrastructure.planning_process import _birth
    path=PRIVATE/'server.json'
    if not path.exists(): print('No owned server'); return
    owned=json.loads(path.read_text()); state,birth=_birth(owned['pid'])
    if state=='DEAD': print('Owned process already stopped'); return
    if state!='ALIVE' or birth!=owned['birth']: raise ValueError('Incarnation mismatch; stop refused')
    private_json('stop.json',dict(run_id=owned['run_id']))
    for _ in range(100):
        if _birth(owned['pid'])[0]=='DEAD':
            result=json.loads((PRIVATE/'server-exit.json').read_text())
            if result['run_id']!=owned['run_id']: raise ValueError('Exit ownership mismatch')
            print('Owned BE and lifespan workers stopped; DB/data preserved'); return
        time.sleep(.2)
    raise RuntimeError('Graceful exit pending; no forced kill')


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('init','backup-upgrade','migrate','status','start','stop','serve'))
    parser.add_argument('--run-id')
    args=parser.parse_args()
    try:
        if args.action=='serve':
            if not args.run_id: raise ValueError('Run id required')
            serve(args.run_id)
        else: globals()[args.action.replace('-','_')]()
        return 0
    except Exception as error:
        print(f'Integrated demo failed ({type(error).__name__}); raw errors/secrets withheld.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
