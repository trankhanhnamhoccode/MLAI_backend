"""Host startup must not require the optional challenger distribution."""
from pathlib import Path
import subprocess
import sys


def test_host_startup_health_without_challenger_distribution(tmp_path):
    code='''
import importlib.abc,importlib.metadata,sys
class MissingChallenger(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='shelfcash_forecast' or fullname.startswith('shelfcash_forecast.'):
            raise ModuleNotFoundError('Optional challenger deliberately unavailable')
sys.meta_path.insert(0,MissingChallenger())
version=importlib.metadata.version
def without_challenger(name):
    if name=='shelfcash-forecast-challenger-snapshot':
        raise importlib.metadata.PackageNotFoundError(name)
    return version(name)
importlib.metadata.version=without_challenger
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.application.use_cases.forecast_serving import ForecastServing
app=create_app(Settings(_env_file=None,environment='test',model_artifact_directory=sys.argv[1]))
with TestClient(app) as client:
    assert client.get('/health').status_code==200
    assert type(app.state.forecast_serving) is ForecastServing
assert not any(name.startswith('shelfcash_forecast') for name in sys.modules)
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path/'artifacts')],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
