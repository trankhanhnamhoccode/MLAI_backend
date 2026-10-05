import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import validate_reset_target


def test_postgresql_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    url = make_url(settings.database_url)
    assert url.drivername == "postgresql+psycopg"
    assert url.database == "shelfcash"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://tester:password@localhost:5432/shelfcash_test")
    assert make_url(Settings(_env_file=None).database_url).username == "tester"


@pytest.mark.parametrize("url", ["mysql://localhost/test", "postgresql+asyncpg://localhost/test", "postgresql+psycopg:///test"])
def test_config_rejects_unsupported_driver_or_missing_host(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=url)


def test_engine_uses_synchronous_postgresql_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: pytest.fail("Eager connection"))
    engine = create_database_engine(Settings(_env_file=None))
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert not engine.dialect.is_async
    finally:
        engine.dispose()


@pytest.mark.parametrize("environment,host,database", [
    ("production", "localhost", "shelfcash"),
    ("development", "remote.example", "shelfcash"),
    ("development", "localhost", "other"),
    ("test", "localhost", "shelfcash"),
])
def test_reset_rejects_unsafe_targets(environment: str, host: str, database: str) -> None:
    settings = Settings(_env_file=None, environment=environment,
                        database_url=f"postgresql+psycopg://local:local@{host}:5432/{database}")
    with pytest.raises(ValueError):
        validate_reset_target(settings)


def test_reset_rejects_query_overrides() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://local:local@localhost/shelfcash?host=remote.example")
    with pytest.raises(ValueError):
        validate_reset_target(settings)


def test_application_import_and_health_do_not_connect(tmp_path: Path) -> None:
    script = """
import psycopg
def reject(*args, **kwargs):
    raise AssertionError('Import/health attempted database connection')
psycopg.connect = reject
import app
import app.main
from fastapi.testclient import TestClient
with TestClient(app.main.app) as client:
    assert client.get('/health').json() == {'status':'ok','service':'shelfcash-backend'}
"""
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(Path(__file__).resolve().parents[2]),
                       APP_NAME="shelfcash-backend", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path,
                            env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_unknown_test_category_fails() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / "scripts/dev.py"), "test", "unknown"], capture_output=True)
    assert result.returncode != 0
