"""Dedicated Compose project selection cannot change DB guard or expose secrets."""
import json
import pytest
from scripts import setup_challenger_test as setup


def test_separate_project_keeps_fixed_guarded_target_and_private_credentials(tmp_path,monkeypatch):
    commands=[]
    monkeypatch.setattr(setup,'PRIVATE',tmp_path/'private')
    monkeypatch.setattr(setup.subprocess,'run',lambda command,**kwargs:commands.append(command))
    monkeypatch.setattr(setup.subprocess,'check_output',lambda command,**kwargs:commands.append(command) or 'owned-container')
    setup.main('shelfcash-forecast-integration-test')
    for command in commands:
        if command[:2]==['docker','compose']:
            assert command[2:4]==['--project-name','shelfcash-forecast-integration-test']
    url=json.loads((setup.PRIVATE/'database.json').read_text())['url']
    from sqlalchemy.engine import make_url
    target=make_url(url)
    assert (target.host,target.port,target.database,target.username)==('127.0.0.1',5438,'shelfcash_challenger_test','shelfcash_challenger_tester')
    assert all(target.password not in str(command) for command in commands)
    with pytest.raises(RuntimeError,match='Existing private setup'):setup.main('different-project')


def test_invalid_project_rejected_before_writing(tmp_path,monkeypatch):
    monkeypatch.setattr(setup,'PRIVATE',tmp_path/'private')
    with pytest.raises(ValueError):setup.main('--bad project')
    assert not setup.PRIVATE.exists()
