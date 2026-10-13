"""Read-only guarded readiness probe; never development or schema mutations."""
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    result=dict(status='BLOCKED',development_connected=False,fixtures_migrations_reset=False,
                checked_at=datetime.now(timezone.utc).isoformat())
    engine=None
    try:
        from sqlalchemy.engine import make_url
        from sqlalchemy import text
        from app.config import Settings
        from scripts.dev import TEST_DATABASE_NAMES, validate_reset_target
        from app.infrastructure.database.engine import create_database_engine
        url=make_url(Settings().test_database_url)
        if url.database not in TEST_DATABASE_NAMES or url.host not in {'localhost','127.0.0.1','::1'}:
            raise ValueError('Refusing non-disposable or nonlocal test target')
        settings=Settings(_env_file=None,environment='test',database_url=url.render_as_string(hide_password=False))
        validate_reset_target(settings)
        result.update(database=url.database,host=url.host,port=url.port or 5432,target_guard='PASS')
        engine=create_database_engine(settings)
        with engine.connect() as connection:
            if connection.scalar(text('SELECT current_database()'))!=url.database:
                raise ValueError('Connected database does not match disposable target')
            result.update(status='READY',postgres_version=connection.scalar(text('SHOW server_version')))
    except Exception as error:
        # Diagnostics intentionally exclude exception text/URL and credentials.
        result['error_type']=type(error).__name__
    finally:
        if engine is not None:engine.dispose()
    destination=ROOT/'runtime/verification/database/postgres_readiness.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
