"""Content pin for the F4 bridge, independent of the native E2 adapter identity."""
import hashlib
from pathlib import Path
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
