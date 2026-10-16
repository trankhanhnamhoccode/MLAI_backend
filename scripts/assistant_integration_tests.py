"""Offline sequential L5 verification on its privately provisioned disposable DB."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    from sqlalchemy.engine import make_url
    from app.config import Settings
    from scripts.dev import validate_reset_target
    root = Path(__file__).resolve().parents[1]
    url = (root/'runtime/assistant-integration/private/test-url.txt').read_text(encoding='utf8')
    target = make_url(url)
    if (target.drivername, target.host, target.port, target.database, target.username, bool(target.query)) != (
        'postgresql+psycopg', '127.0.0.1', 5441, 'shelfcash_integration_test', 'shelfcash_integration_tester', False
    ):
        raise RuntimeError('Refusing any target other than the dedicated L5 disposable DB')
    validate_reset_target(Settings(_env_file=None, environment='test', database_url=url))
    env = {**os.environ, 'ENVIRONMENT':'test', 'DATABASE_URL':url, 'TEST_DATABASE_URL':url,
           'PYTHONDONTWRITEBYTECODE':'1', 'CHAT_LLM_ENABLED':'false', 'SUMMARY_LLM_ENABLED':'false',
           'IMPORT_LLM_SUGGESTIONS_ENABLED':'false', 'AUTH_EMAIL_DELIVERY_ENABLED':'false',
           'IMPORT_WORKER_ENABLED':'false', 'PLANNING_WORKER_ENABLED':'false',
           'PDF_EXPORT_WORKER_ENABLED':'false', 'NOTIFICATION_WORKER_ENABLED':'false'}
    for name in ('OPENROUTER_API_KEY', 'SUMMARY_API_KEY', 'CHAT_API_KEY'):
        env.pop(name, None)
    raise SystemExit(subprocess.call([sys.executable, '-B', '-m', 'pytest', *sys.argv[1:]], cwd=root, env=env))


if __name__ == '__main__':
    main()
