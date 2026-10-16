"""F4 content pin and effective database identity guards."""
import hashlib
from pathlib import Path
from sqlalchemy.engine import Engine
from app.config import Settings
from app.application.forecast_challenger_serialization import challenger_digest

FILES=('application/contracts/planning_challenger.py','application/contracts/planning_public_evidence.py',
    'application/contracts/forecast_model.py','application/contracts/planning_run.py',
    'application/use_cases/planning_challenger.py','application/use_cases/planning_public.py',
    'application/use_cases/planning_worker.py','application/use_cases/planning_run.py','application/use_cases/forecast_serving.py',
    'application/use_cases/forecast_trained_execution.py','application/use_cases/forecast_execution.py',
    'application/forecast_preparation.py','application/forecast_serialization.py',
    'infrastructure/database/planning_capture.py','infrastructure/planning_challenger_identity.py')


def integration_digest():
    root=Path(__file__).resolve().parents[1]
    return challenger_digest('f4-integration-code',tuple((name,hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in FILES))


def require_challenger_test_target(engine: Engine, settings: Settings) -> None:
    """Check configured target before connection, then actual DB and limited role."""
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from scripts.dev import validate_reset_target

    validate_reset_target(settings)
    url = make_url(settings.database_url)
    if (settings.environment != 'test' or url.database != 'shelfcash_challenger_test'
            or engine.url != url):
        raise ValueError('F4 restricted to the dedicated challenger test target')
    with engine.connect() as connection:
        if connection.execute(text('SELECT current_database(),current_user')).one() != (
                'shelfcash_challenger_test', 'shelfcash_challenger_tester'):
            raise ValueError('Connected challenger identity mismatch')
        if connection.scalar(text('SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user')):
            raise ValueError('Challenger runtime role must be limited')
