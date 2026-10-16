"""Fresh startup is independent of paid/native services; L5 DB guard is strict."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


def test_fresh_startup_health_without_native_provider_or_database():
    code='''
import importlib.abc,sys,socket,urllib.request
class BlockNative(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0]=='shelfcash_forecast':raise AssertionError('Native dependency at startup')
sys.meta_path.insert(0,BlockNative())
def forbidden(*a,**k):raise AssertionError('Startup network/DB/provider call')
socket.create_connection=urllib.request.urlopen=forbidden
from app.main import create_app
from app.config import Settings
from fastapi.testclient import TestClient
settings=Settings(_env_file=None)
assert not settings.summary_llm_enabled and not settings.chat_llm_enabled
assert not settings.import_llm_suggestions_enabled
app=create_app(settings)
assert app.state.assistant_chat.presentation_version==6
from app.application.use_cases.forecast_serving import ForecastServing
assert type(app.state.forecast_serving) is ForecastServing
with TestClient(app) as client:assert client.get('/health').status_code==200
print('OFF startup/health/defaultV6/host VERIFIED; native/network/DB forbidden')
'''
    env={**os.environ}
    for k in list(env):
        if k.endswith('_ENABLED'):env[k]='false'
    env.pop('OPENROUTER_API_KEY',None)
    child=subprocess.run([sys.executable,'-B','-c',code],env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stderr
    assert 'VERIFIED' in child.stdout


@pytest.mark.parametrize('url',[
    'postgresql+psycopg://shelfcash_integration_tester:x@127.0.0.1:5436/shelfcash_integration_test',
    'postgresql+psycopg://shelfcash_integration_tester:x@127.0.0.1:5441/shelfcash_local',
    'postgresql+psycopg://postgres:x@127.0.0.1:5441/shelfcash_integration_test',
    'postgresql+psycopg://shelfcash_integration_tester:x@127.0.0.1:5441/shelfcash_integration_test?host=elsewhere',
])
def test_l5_runner_refuses_foreign_effective_targets(monkeypatch,url):
    from scripts.assistant_integration_tests import main
    monkeypatch.setattr(Path,'read_text',lambda *a,**k:url)
    with pytest.raises(RuntimeError,match='Refusing any target'):main()
