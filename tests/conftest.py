"""Own only the separate local test database; never mutate development state."""
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import reset_database, validate_reset_target


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(Settings().test_database_url)
    settings = Settings(_env_file=None, environment="test", database_url=url.render_as_string(hide_password=False))
    validate_reset_target(settings)
    # The role created by the official local image can create this test database.
    admin = create_database_engine(settings.model_copy(update={"database_url": url.set(database="postgres").render_as_string(hide_password=False)}))
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database})
            if not exists:
                connection.execute(text("CREATE DATABASE shelfcash_test"))
    finally:
        admin.dispose()
    return settings.database_url


@pytest.fixture
def database_settings(test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None, database_url=test_database_url, environment="test")
    reset_database(settings, seed=False)
    try:
        yield settings
    finally:
        reset_database(settings, seed=False)
