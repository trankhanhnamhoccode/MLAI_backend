"""Run selected tests using only the provisioned assistant test URL, no .env edit."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    url = (root/'runtime/assistant-test/private/test-url.txt').read_text(encoding='utf-8')
    from app.config import Settings
    from scripts.dev import validate_reset_target
    from sqlalchemy.engine import make_url
    target = make_url(url)
    if (target.host,target.port,target.database,target.username) != ('127.0.0.1',5436,'shelfcash_assistant_test','shelfcash_assistant_tester'):
        raise RuntimeError('Refusing any other test target')
    validate_reset_target(Settings(_env_file=None,environment='test',database_url=url))
    env = {**os.environ,'ENVIRONMENT':'test','DATABASE_URL':url,'TEST_DATABASE_URL':url,
        'SUMMARY_LLM_ENABLED':'false','AUTH_EMAIL_DELIVERY_ENABLED':'false',
        'IMPORT_WORKER_ENABLED':'false','PLANNING_WORKER_ENABLED':'false',
        'PDF_EXPORT_WORKER_ENABLED':'false','NOTIFICATION_WORKER_ENABLED':'false',
        'IMPORT_LLM_SUGGESTIONS_ENABLED':'false','PYTHONDONTWRITEBYTECODE':'1'}
    env.pop('OPENROUTER_API_KEY',None)
    raise SystemExit(subprocess.call([sys.executable,'-B','-m','pytest',*sys.argv[1:]],cwd=root,env=env))


if __name__ == '__main__': main()
