"""Read-only disposable-DB verification, with explicit test target guards."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from sqlalchemy.engine import make_url
    from app.config import Settings
    from scripts.dev import inspect_database, validate_reset_target

    url = make_url(Settings().test_database_url)
    if url.database != 'shelfcash_test' or url.host not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Refusing nonlocal or non-disposable database target')
    settings = Settings(_env_file=None, environment='test',
                        database_url=url.render_as_string(hide_password=False))
    validate_reset_target(settings)
    # inspect_database uses a fresh READ ONLY transaction and releases its engine.
    state = inspect_database(settings)
    if state['database'] != 'shelfcash_test' or not state['at_head']:
        raise ValueError('Test database identity/schema verification failed')
    if any(count for name, count in state['tables'].items() if name != 'alembic_version'):
        raise ValueError('Test fixture cleanup left business rows')
    state.update(checked_at=datetime.now(timezone.utc).isoformat(),
                 development_connected=False, host=url.host, port=url.port or 5432,
                 target_guard='PASS', inspection='fresh read-only test connection')
    destination = ROOT / 'runtime/verification/database/post_test_database.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(state))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not expose URLs, passwords or raw DBAPI error messages.
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__}))
        raise SystemExit(1)
