"""Local tooling guards and private configuration work without sibling worktrees."""
import base64
from pathlib import Path
from types import SimpleNamespace
import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from app.config import Settings
from scripts import local_runtime as local


@pytest.fixture
def configured():
    app=Settings(_env_file=None,environment='development',database_url=f'postgresql+psycopg://{local.RUNTIME}:synthetic@127.0.0.1:5433/{local.DB}',
        test_database_url=f'postgresql+psycopg://{local.TESTER}:synthetic@127.0.0.1:5433/{local.TEST_DB}',
        runtime_directory=local.ROOT/'runtime/local/app',upload_directory=local.ROOT/'runtime/local/app/uploads',
        model_artifact_directory=local.ROOT/'runtime/local/app/models',auth_allowed_origins=['https://localhost:5173'])
    runtime=local.LocalSettings(_env_file=None,migration_database_url=f'postgresql+psycopg://{local.MIGRATOR}:synthetic@127.0.0.1:5433/{local.DB}')
    return app,runtime


@pytest.mark.parametrize('change',[{'database_url':'postgresql+psycopg://shelfcash:synthetic@127.0.0.1:5433/shelfcash'},
    {'test_database_url':f'postgresql+psycopg://{local.RUNTIME}:synthetic@127.0.0.1:5433/{local.DB}'},
    {'auth_dev_cookie':True},{'auth_allowed_origins':['http://localhost:5173']},
    {'runtime_directory':Path('C:/another-worktree/runtime')}, {'environment':'test'}])
def test_local_profile_refuses_old_targets_or_insecure_transport(configured,change):
    app,runtime=configured
    local.validate(app,runtime)
    with pytest.raises(ValueError):local.validate(app.model_copy(update=change),runtime)


def test_private_secret_generation_is_repeatable_and_does_not_print_values(tmp_path,monkeypatch,capsys):
    template=(local.ROOT/'.env.example').read_text(encoding='utf-8')
    monkeypatch.setattr(local,'ROOT',tmp_path)
    (tmp_path/'.env.example').write_text(template,encoding='utf-8')
    local.prepare_secrets();first=(tmp_path/'.env').read_bytes()
    local.prepare_secrets();assert (tmp_path/'.env').read_bytes()==first
    values=dotenv_values(tmp_path/'.env');key=values['AUTH_DELIVERY_ENCRYPTION_KEY']
    assert len(base64.b64decode(key))==32
    output=capsys.readouterr().out
    assert key not in output
    for field in ('DATABASE_URL','TEST_DATABASE_URL','MIGRATION_DATABASE_URL'):
        assert len(make_url(values[field]).password)>=32 and make_url(values[field]).password not in output


def test_example_fields_have_real_consumers():
    keys=set(dotenv_values(local.ROOT/'.env.example'))
    assert keys<=set(key.upper() for key in Settings.model_fields)|set(key.upper() for key in local.LocalSettings.model_fields)|{'POSTGRES_PASSWORD'}
    assert keys>={'DATABASE_URL','TEST_DATABASE_URL','MIGRATION_DATABASE_URL','AUTH_EMAIL_DELIVERY_ENABLED'}


def test_docker_refuses_second_compose_when_port_is_in_use(configured,monkeypatch):
    monkeypatch.setattr(local,'configuration',lambda:configured)
    calls=[]
    monkeypatch.setattr(local.subprocess,'run',lambda args,**kw:(calls.append(args) or SimpleNamespace(returncode=1)))
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def connect_ex(self,*args):return 0
    monkeypatch.setattr(local.socket,'socket',Socket)
    with pytest.raises(ValueError):local.docker_start()
    assert calls==[['docker','inspect',configured[1].local_postgres_container]]


def test_init_refuses_unowned_existing_database_before_ddl(configured,monkeypatch):
    monkeypatch.setattr(local,'configuration',lambda:configured)
    statements=[]
    def admin(config,statement,db='postgres'):
        statements.append(statement)
        return '1' if 'count(*)' in statement else 'not owned'
    monkeypatch.setattr(local,'admin',admin)
    with pytest.raises(ValueError):local.init_db()
    assert all(statement.startswith('SELECT') for statement in statements)


def test_tls_is_owned_by_requested_directory(tmp_path):
    from scripts.integrated_demo import certificate
    from cryptography import x509
    certificate(tmp_path)
    original=(tmp_path/'localhost.key').read_bytes()
    certificate(tmp_path)
    assert (tmp_path/'localhost.key').read_bytes()==original
    cert=x509.load_pem_x509_certificate((tmp_path/'localhost.pem').read_bytes())
    assert 'localhost' in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)


def test_smtp_smoke_requires_explicit_recipient_then_sends_once(configured,monkeypatch):
    app,runtime=configured
    app=app.model_copy(update={'auth_smtp_host':'smtp.fixture.test','auth_delivery_sender':'fixture@example.test'})
    monkeypatch.setattr(local,'configuration',lambda:(app,runtime))
    with pytest.raises(ValueError):local.smtp_smoke()
    runtime=runtime.model_copy(update={'local_smoke_recipient':'fixture@example.test'})
    messages=[]
    class SMTP:
        def __init__(self,*args,**kwargs):assert kwargs['context'].verify_mode!=0
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def send_message(self,message):messages.append(message)
    monkeypatch.setattr('smtplib.SMTP_SSL',SMTP)
    local.smtp_smoke()
    assert len(messages)==1 and messages[0]['To']=='fixture@example.test'
