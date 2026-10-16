"""The relocated F4 guard still refuses wrong targets before connecting."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.planning_challenger_identity import require_challenger_test_target


URL = 'postgresql+psycopg://shelfcash_challenger_tester:synthetic@127.0.0.1:5438/shelfcash_challenger_test'


class GuardEngine:
    def __init__(self, url=URL, identity=('shelfcash_challenger_test', 'shelfcash_challenger_tester'), privileged=False):
        self.url, self.identity, self.privileged = make_url(url), identity, privileged
        self.connections = 0
        self.closed = False

    @contextmanager
    def connect(self):
        self.connections += 1
        try:
            yield self
        finally:
            self.closed = True

    def execute(self, statement):
        assert str(statement) == 'SELECT current_database(),current_user'
        return SimpleNamespace(one=lambda: self.identity)

    def scalar(self, statement):
        assert all(flag in str(statement) for flag in ('rolsuper', 'rolcreatedb', 'rolcreaterole', 'rolreplication', 'rolbypassrls'))
        return self.privileged


@pytest.mark.parametrize('url,environment', [
    (URL, 'development'),
    (URL.replace('5438', '5442'), 'test'),
    (URL.replace('127.0.0.1', 'remote.example.test'), 'test'),
    (URL.replace('shelfcash_challenger_tester', 'postgres'), 'test'),
    (URL.replace('shelfcash_challenger_test', 'shelfcash_local'), 'test'),
    (URL + '?host=elsewhere', 'test'),
])
def test_configured_target_rejected_before_connection(url, environment):
    engine = GuardEngine(url)
    with pytest.raises(ValueError):
        require_challenger_test_target(engine, Settings(_env_file=None, environment=environment, database_url=url))
    assert engine.connections == 0


def test_engine_target_must_match_settings():
    engine = GuardEngine(URL.replace('5438', '5442'))
    with pytest.raises(ValueError, match='restricted'):
        require_challenger_test_target(engine, Settings(_env_file=None, environment='test', database_url=URL))
    assert engine.connections == 0


@pytest.mark.parametrize('identity,privileged', [
    (('foreign', 'shelfcash_challenger_tester'), False),
    (('shelfcash_challenger_test', 'postgres'), False),
    (('shelfcash_challenger_test', 'shelfcash_challenger_tester'), True),
])
def test_effective_identity_and_privilege_refused(identity, privileged):
    engine = GuardEngine(identity=identity, privileged=privileged)
    with pytest.raises(ValueError):
        require_challenger_test_target(engine, Settings(_env_file=None, environment='test', database_url=URL))
    assert engine.connections == 1 and engine.closed


def test_correct_limited_identity_closes_connection():
    engine = GuardEngine()
    require_challenger_test_target(engine, Settings(_env_file=None, environment='test', database_url=URL))
    assert engine.connections == 1 and engine.closed
