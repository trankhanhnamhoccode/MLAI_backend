"""Demo tooling cannot target old/test DBs or weaken browser/provider guards."""
import base64

import pytest

from app.config import Settings
from scripts import integrated_demo as demo
from scripts.dev import validate_reset_target


@pytest.fixture
def config():
    return Settings(_env_file=None, environment='development',
        database_url=f'postgresql+psycopg://{demo.ROLE}:synthetic@127.0.0.1:5433/{demo.DB}',
        test_database_url='postgresql+psycopg://shelfcash_integration_tester:synthetic@127.0.0.1:5432/shelfcash_integration_test',
        runtime_directory=demo.PRIVATE/'app',upload_directory=demo.PRIVATE/'app/uploads',
        model_artifact_directory=demo.PRIVATE/'app/models',auth_allowed_origins=[demo.ORIGIN],
        auth_dev_cookie=False,auth_email_delivery_enabled=False,import_llm_suggestions_enabled=False,
        openrouter_api_key=None,openrouter_model=None,
        auth_delivery_encryption_key=base64.b64encode(bytes(32)).decode())


@pytest.mark.parametrize('change', [
    {'database_url':'postgresql+psycopg://shelfcash_integration:synthetic@127.0.0.1:5433/shelfcash_integration_s411'},
    {'database_url':'postgresql+psycopg://shelfcash_integration_tester:synthetic@127.0.0.1:5432/shelfcash_integration_test'},
    {'database_url':f'postgresql+psycopg://{demo.MIGRATOR}:synthetic@127.0.0.1:5433/{demo.DB}'},
    {'test_database_url':f'postgresql+psycopg://{demo.ROLE}:synthetic@127.0.0.1:5433/{demo.DB}'},
    {'auth_dev_cookie':True}, {'auth_allowed_origins':['http://localhost:5173']},
    {'auth_email_delivery_enabled':True}, {'import_llm_suggestions_enabled':True},
    {'runtime_directory':demo.ROOT/'runtime/s411/private/app'},
])
def test_runtime_refuses_unsafe_target_or_transport(config,change):
    with pytest.raises(ValueError): demo.validate(config.model_copy(update=change))


def test_demo_is_never_a_reset_target(config):
    demo.validate(config)
    with pytest.raises(ValueError): validate_reset_target(config)


def test_stop_refuses_unknown_process_without_writing_stop(monkeypatch,tmp_path):
    import json
    import app.infrastructure.planning_process as process
    monkeypatch.setattr(demo,'PRIVATE',tmp_path)
    (tmp_path/'server.json').write_text(json.dumps(dict(pid=1,birth='expected',run_id='synthetic')))
    monkeypatch.setattr(process,'_birth',lambda pid:('UNKNOWN',None))
    with pytest.raises(ValueError): demo.stop()
    assert not (tmp_path/'stop.json').exists()


def test_stop_refuses_reused_pid(monkeypatch,tmp_path):
    import json
    import app.infrastructure.planning_process as process
    monkeypatch.setattr(demo,'PRIVATE',tmp_path)
    (tmp_path/'server.json').write_text(json.dumps(dict(pid=1,birth='old',run_id='synthetic')))
    monkeypatch.setattr(process,'_birth',lambda pid:('ALIVE','new'))
    with pytest.raises(ValueError): demo.stop()
    assert not (tmp_path/'stop.json').exists()


def test_init_invalid_test_identity_never_calls_docker(monkeypatch,config,tmp_path):
    (tmp_path/'.env').write_text('TEST_DATABASE_URL=synthetic')
    monkeypatch.setattr(demo,'ROOT',tmp_path)
    invalid=config.model_copy(update={'test_database_url':f'postgresql+psycopg://{demo.ROLE}:synthetic@127.0.0.1:5433/{demo.DB}'})
    monkeypatch.setattr(demo,'Settings',lambda:invalid)
    def unexpected(*args,**kwargs):
        pytest.fail('Invalid test identity must fail before Docker/DB mutation')
    monkeypatch.setattr(demo,'admin_sql',unexpected)
    with pytest.raises(ValueError): demo.init()


@pytest.mark.parametrize('value', [r'D:\Folder with spaces\demo', 'synthetic # secret "quote"', 'Tiếng Việt'])
def test_env_serialization_preserves_strings(value):
    from dotenv import dotenv_values
    from io import StringIO
    assert dotenv_values(stream=StringIO('DEMO_VALUE='+demo.env_value(value)),interpolate=False)['DEMO_VALUE']==value


def test_upgrade_requires_intact_backup_and_unchanged_rows(monkeypatch,tmp_path):
    import hashlib,json
    monkeypatch.setattr(demo,'PRIVATE',tmp_path)
    archive=tmp_path/'synthetic.dump';archive.write_bytes(b'synthetic test archive')
    saved=dict(database=demo.DB,dump=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),counts={'users':3})
    (tmp_path/'upgrade-backup.json').write_text(json.dumps(saved))
    monkeypatch.setattr(demo,'schema_counts',lambda _: {'users':3})
    assert demo.check_upgrade_backup(object())==saved
    monkeypatch.setattr(demo,'schema_counts',lambda _: {'users':4})
    with pytest.raises(ValueError):demo.check_upgrade_backup(object())
    monkeypatch.setattr(demo,'schema_counts',lambda _: {'users':3})
    archive.write_bytes(b'corrupt')
    with pytest.raises(ValueError):demo.check_upgrade_backup(object())


def test_migration_refuses_live_or_unknown_owned_process(monkeypatch,tmp_path):
    import json
    import app.infrastructure.planning_process as process
    monkeypatch.setattr(demo,'PRIVATE',tmp_path)
    (tmp_path/'server.json').write_text(json.dumps(dict(pid=1)))
    for state in ('ALIVE','UNKNOWN'):
        monkeypatch.setattr(process,'_birth',lambda _,state=state:(state,None))
        with pytest.raises(ValueError):demo.quiescent(object())


def test_runtime_refuses_uncommitted_source(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(demo.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout='synthetic-sha'))
    monkeypatch.setattr(demo.subprocess,'check_output',lambda *a,**k:b' M app/main.py')
    with pytest.raises(ValueError):demo.source_identity()
