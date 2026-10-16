"""Offline observer invariants; no native inference, Planning run, DB or batch claim."""
import json
import types
import sys
import pytest
from scripts.planning_profile_observer import Observer
from scripts.profile_planning_f4_1 import claim,verify_owner


def test_nested_elapsed_is_not_double_counted():
    ticks=iter([0.,1.,3.,5.])
    observer=Observer(clock=lambda:next(ticks))
    with observer.span('outer'):
        with observer.span('inner'):pass
    assert observer.rows['startup / outer']==dict(calls=1,inclusive_seconds=5.,exclusive_seconds=3.)
    assert observer.rows['startup / inner']==dict(calls=1,inclusive_seconds=2.,exclusive_seconds=2.)


def test_disabled_preserves_function_and_has_no_observation():
    observer=Observer(enabled=False)
    def f(value):return value
    assert observer.wrap(f,'off') is f
    with observer.span('off'):assert f(3)==3
    assert observer.rows=={}


def test_observation_preserves_exact_return_and_exception_identity():
    observer=Observer();result=object();failure=ValueError('fixture')
    def f():return result
    def bad():raise failure
    assert observer.wrap(f,'success')() is result
    with pytest.raises(ValueError) as caught:observer.wrap(bad,'failure')()
    assert caught.value is failure and observer.stack==[]
    assert observer.rows['startup / failure']['calls']==1


def test_aliases_are_scoped_and_restored(monkeypatch):
    module=types.ModuleType('app._observer_fixture')
    def f():return ('same',1)
    module.call=f;monkeypatch.setitem(sys.modules,module.__name__,module)
    observer=Observer();observer.aliases(f,'call')
    try:
        assert module.call is not f and module.call()==('same',1)
    finally:observer.restore()
    assert module.call is f


@pytest.mark.parametrize('kind,limit',[('planning',3),('native',2)])
def test_limits_reject_before_extra_execution(kind,limit):
    observer=Observer()
    for _ in range(limit):observer.resource(kind)
    with pytest.raises(RuntimeError):observer.resource(kind)
    assert (observer.planning_executions if kind=='planning' else observer.native_inferences)==limit


def test_claim_is_exclusive_and_cannot_reset_budget(tmp_path):
    marker=tmp_path/'claim.json'
    claim(marker,'a'*64,123.)
    before=marker.read_bytes()
    with pytest.raises(FileExistsError):claim(marker,'b'*64,124.)
    assert marker.read_bytes()==before
    value=json.loads(before)
    assert value['hard_wall_seconds']==120 and value['maximum_native_inferences']==2


def test_consumed_batch_rejects_before_loading_or_overwriting_receipts(tmp_path,monkeypatch):
    from scripts import profile_planning_f4_1 as tool
    marker=tmp_path/'compute-claim.json';marker.write_text('original consumed claim')
    monkeypatch.setattr(tool,'BASE',tmp_path)
    def forbidden(*args):raise AssertionError('must not reach preflight or execution')
    monkeypatch.setattr(tool,'loaded',forbidden)
    with pytest.raises(RuntimeError,match='F4_1_BATCH_ALREADY_CONSUMED'):tool.run('a'*64)
    assert marker.read_text()=='original consumed claim'


def test_actual_install_restores_host_aliases_without_execution():
    from scripts.planning_profile_observer import install
    from app.application.use_cases import bom,serving
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    original=bom.expand_bom;load=ChallengerStorage.load_artifact
    observer=Observer()
    install(observer,lambda:None)
    try:
        assert bom.expand_bom is serving.expand_bom and bom.expand_bom.__wrapped__ is original
        assert ChallengerStorage.load_artifact.__wrapped__ is load
        assert observer.planning_executions==observer.native_inferences==0
    finally:observer.restore()
    assert bom.expand_bom is serving.expand_bom is original
    assert ChallengerStorage.load_artifact is load


def test_claim_owner_in_venv_subprocess_without_compute(tmp_path):
    import subprocess
    marker=tmp_path/'probe.json'
    claim(marker,'a'*64,123.)
    command="import json,sys; from scripts.profile_planning_f4_1 import verify_owner; verify_owner(json.load(open(sys.argv[1])), 'a'*64)"
    result=subprocess.run([sys.executable,'-B','-c',command,str(marker)],capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode()


@pytest.mark.parametrize('change',['missing','identity','pid','birth','host'])
def test_claim_owner_rejects_invalid_or_unverifiable_incarnation(tmp_path,change):
    marker=tmp_path/'probe.json';claim(marker,'a'*64,123.)
    value=json.loads(marker.read_bytes())
    if change=='missing':del value['parent_process']
    elif change=='identity':value['identity']='b'*64
    elif change=='pid':value['parent_pid']+=1
    else:value['parent_process'][change]+='-wrong'
    with pytest.raises(RuntimeError):verify_owner(value,'a'*64)


def test_original_runtime_mismatch_still_fails_closed():
    from pathlib import Path
    from app.application.contracts.forecast_challenger import ChallengerInput,ChallengerError
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    path=Path('runtime/challenger/runs/31394ccc8b91b35e8528bf4cec555e0eb068557709796e340602cce05d51b82b/evidence.json')
    value=ChallengerInput.model_validate(json.loads(path.read_bytes())['input'])
    with pytest.raises(ChallengerError,match='ARTIFACT_RUNTIME_MISMATCH'):
        ForecastChallenger(ChallengerStorage(Path('runtime/challenger')),enabled=True)._admit(value)
