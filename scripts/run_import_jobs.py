"""Explicit disposable-test executor. Does not reset, migrate, seed or print tokens."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.import_staging import ImportStaging
from scripts.dev import TEST_DATABASE_NAMES, validate_reset_target
from sqlalchemy.engine import make_url
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-database", action="store_true", required=True)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_jobs <= 20:
        parser.error("max-jobs must be 1..20")
    base = Settings()
    url = make_url(base.test_database_url)
    if (
        url.database not in TEST_DATABASE_NAMES
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.query
    ):
        parser.error("only allowlisted local test databases supported")
    config = base.model_copy(
        update={
            "database_url": url.render_as_string(hide_password=False),
            "environment": "test",
        }
    )
    validate_reset_target(config)
    engine = create_database_engine(config)
    try:
        with engine.connect() as c:
            if c.scalar(text("SELECT current_database()")) != url.database:
                raise RuntimeError("database guard mismatch")
        service = ImportStaging(AuthUseCases(engine), config)
        recovered = service.recover() if args.recover else ()
        jobs = []
        for _ in range(args.max_jobs):
            ident = service.run_one()
            if ident is None:
                break
            jobs.append(str(ident))
        print(json.dumps({"jobs": jobs, "recovered": [str(x) for x in recovered]}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
