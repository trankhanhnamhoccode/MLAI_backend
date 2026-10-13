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
    # Dedicated DBs are provisioned by an operator; their roles cannot CREATE DATABASE.
    # Preserve legacy bootstrap only when the legacy database is actually absent.
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == url.database
            if url.database == "shelfcash_integration_test":
                assert connection.scalar(text("SELECT current_user")) == "shelfcash_integration_tester"
    except Exception:
        if url.database != "shelfcash_test":
            raise RuntimeError("Dedicated test database unavailable; check provisioning/effective TEST_DATABASE_URL") from None
        admin = create_database_engine(settings.model_copy(update={"database_url": url.set(database="postgres").render_as_string(hide_password=False)}))
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database})
                if not exists:
                    connection.execute(text("CREATE DATABASE shelfcash_test"))
                else:
                    raise RuntimeError("Legacy test database exists but is unavailable") from None
        finally:
            admin.dispose()
    finally:
        engine.dispose()
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
