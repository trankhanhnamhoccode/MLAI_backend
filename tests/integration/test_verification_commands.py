"""Exercise developer commands across process and persisted-state boundaries."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_command(*arguments: str, **settings: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(ENVIRONMENT="development", DATABASE_URL="sqlite:///runtime/shelfcash.db")
    environment.update(settings)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/dev.py"), *arguments],
        cwd=ROOT.parent, env=environment, capture_output=True, text=True,
    )


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "sqlite:///runtime/other.db", "sqlite:///../outside.db"])
def test_reset_rejects_noncanonical_targets(url: str) -> None:
    result = run_command("reset", DATABASE_URL=url)
    assert result.returncode != 0
    assert "ERROR:" in result.stderr


def test_reset_rejects_nondevelopment_before_touching_file(tmp_path: Path) -> None:
    database = tmp_path / "sentinel.db"
    database.write_bytes(b"preserve this data")
    result = run_command("reset", ENVIRONMENT="production", DATABASE_URL="sqlite:///" + database.as_posix())
    assert result.returncode != 0
    assert "development" in result.stderr
    assert database.read_bytes() == b"preserve this data"


def test_status_does_not_create_missing_database(tmp_path: Path) -> None:
    database = tmp_path / "missing.db"
    result = run_command("status", DATABASE_URL="sqlite:///" + database.as_posix())
    assert result.returncode != 0
    assert not database.exists()


def test_seed_and_status_verify_fresh_persisted_baseline(tmp_path: Path) -> None:
    database = tmp_path / "baseline.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0001_scaffold')")
    settings = {"DATABASE_URL": "sqlite:///" + database.as_posix()}
    for _ in range(2):
        result = run_command("seed", **settings)
        assert result.returncode == 0, result.stderr
        assert "No business seed data" in result.stdout
    result = run_command("status", **settings)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["revisions"] == ["0001_scaffold"]
    assert state["tables"] == {"alembic_version": 1}
    assert state["integrity_check"] == "ok"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("UPDATE alembic_version SET version_num = 'wrong'")
    assert run_command("seed", **settings).returncode != 0
    assert run_command("status", **settings).returncode != 0


def test_unknown_test_category_fails() -> None:
    assert run_command("test", "unknown").returncode != 0


def test_reset_seed_repeat_and_sidecar_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import dev
    from app.config import Settings

    configuration = dev.migration_config()
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "migration_config", lambda: configuration)
    database = tmp_path / "runtime" / "shelfcash.db"
    database.parent.mkdir()
    url = "sqlite:///" + database.as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(_env_file=None, database_url=url, environment="development")
    for _ in range(2):
        dev.reset_database(settings, seed=True)
        # New connection after migration/seed verifies durable state, not ORM identity.
        with closing(sqlite3.connect(database)) as connection, connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [("0001_scaffold",)]
            connection.execute("CREATE TABLE disposable (value TEXT)")
    before = database.read_bytes()
    sidecar = Path(str(database) + "-wal")
    sidecar.write_bytes(b"in use")
    with pytest.raises(ValueError, match="sidecars"):
        dev.reset_database(settings, seed=False)
    assert database.read_bytes() == before
    assert sidecar.read_bytes() == b"in use"
