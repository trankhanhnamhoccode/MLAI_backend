from pathlib import Path

from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine


def test_empty_alembic_baseline_and_synchronous_session(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    database_url = "sqlite:///" + (tmp_path / "bootstrap.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", database_url)
    configuration = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(configuration, "head")
    engine = create_database_engine(Settings(_env_file=None, database_url=database_url))
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
        with Session(engine) as session:
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0001_scaffold"
            )
            assert session.scalar(text("PRAGMA foreign_keys")) == 1
        command.downgrade(configuration, "base")
        with Session(engine) as session:
            assert session.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 0
    finally:
        engine.dispose()
