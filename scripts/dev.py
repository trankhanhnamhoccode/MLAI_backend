"""Repository-local verification commands; never imported by the application."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.config import Settings


def migration_config() -> Config:
    configuration = Config(str(ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(ROOT / "alembic"))
    return configuration


def database_path(settings: Settings) -> Path:
    url = make_url(settings.database_url)
    if not url.database or url.database == ":memory:" or url.query:
        raise ValueError("Commands require a file-backed SQLite URL without query parameters")
    path = Path(url.database)
    return (path if path.is_absolute() else ROOT / path).resolve()


def inspect_database(settings: Settings) -> dict[str, object]:
    path = database_path(settings)
    if not path.is_file():
        raise ValueError(f"Database does not exist: {path}. Run reset_db first.")
    # mode=ro prevents inspection from creating a DB or modifying business state.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {}
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall():
            quoted_name = '"' + name.replace('"', '""') + '"'
            tables[name] = connection.execute(f"SELECT COUNT(*) FROM {quoted_name}").fetchone()[0]
        revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")] if "alembic_version" in tables else []
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    heads = ScriptDirectory.from_config(migration_config()).get_heads()
    if integrity != "ok" or violations or sorted(revisions) != sorted(heads):
        raise ValueError(f"Database verification failed: integrity={integrity}, foreign_key_violations={violations}, revisions={revisions}, expected={heads}")
    return {"database": str(path), "integrity_check": integrity,
            "foreign_key_violations": violations, "revisions": revisions, "tables": tables}


def seed_demo(settings: Settings) -> None:
    state = inspect_database(settings)
    if state["tables"] != {"alembic_version": 1}:
        raise ValueError("S0 seed expects only the empty scaffold revision table")
    print("No business seed data: S0 has no business tables. Migrated baseline verified; no rows written.")


def reset_database(settings: Settings, seed: bool) -> None:
    if settings.environment != "development":
        raise ValueError("Reset requires ENVIRONMENT=development")
    path = database_path(settings)
    canonical = ROOT / "runtime" / "shelfcash.db"
    if canonical.parent.is_symlink() or canonical.is_symlink():
        raise ValueError("Reset refuses linked runtime/database paths")
    if path != canonical or path.parent.resolve() != ROOT / "runtime":
        raise ValueError("Reset only permits backend/runtime/shelfcash.db")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Reset refuses SQLite sidecars; stop database users and close/checkpoint the database first")
    if path.exists():
        path.unlink()
    command.upgrade(migration_config(), "head")
    print(json.dumps(inspect_database(settings), indent=2))
    if seed:
        seed_demo(settings)


def run_tests(category: str) -> int:
    target = ROOT / "tests" if category == "all" else ROOT / "tests" / category
    if category != "all" and not list(target.rglob("test_*.py")):
        print(f"No {category} tests implemented in S0; no tests ran.")
        return 0
    return subprocess.run([sys.executable, "-m", "pytest", str(target)], cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    tests = commands.add_parser("test")
    tests.add_argument("category", nargs="?", default="all", choices=("unit", "integration", "api", "e2e", "all"))
    reset = commands.add_parser("reset")
    reset.add_argument("--seed", action="store_true")
    commands.add_parser("seed")
    commands.add_parser("status")
    arguments = parser.parse_args()
    os.chdir(ROOT)
    if arguments.command == "test":
        return run_tests(arguments.category)
    try:
        settings = Settings()
        if arguments.command == "reset":
            reset_database(settings, arguments.seed)
        elif arguments.command == "seed":
            seed_demo(settings)
        else:
            print(json.dumps(inspect_database(settings), indent=2))
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
