import importlib
import os
from pathlib import Path
import subprocess
import sys

def test_application_imports() -> None:
    module = importlib.import_module("app.main")
    assert module.app.title


def test_domain_imports_without_infrastructure(tmp_path: Path) -> None:
    # A fresh interpreter prevents cached imports from hiding infrastructure coupling.
    script = """
import importlib
import sys

class RejectInfrastructure:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlalchemy', 'psycopg', 'fastapi', 'httpx'}:
            raise AssertionError('Domain imported external infrastructure: ' + fullname)
        if fullname.startswith(('app.infrastructure', 'app.models', 'app.api')):
            raise AssertionError('Domain imported application infrastructure: ' + fullname)

sys.meta_path.insert(0, RejectInfrastructure())
for name in ('', '.forecasting', '.demand', '.inventory', '.procurement', '.decision'):
    importlib.import_module('app.domain' + name)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=environment,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
