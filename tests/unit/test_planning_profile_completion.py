"""Completion authorization/process-tree tests; never run Planning or inference."""
import json
import os
import pytest
from scripts import profile_planning_f4_1_completion as completion


def test_consumed_group_stops_before_loading_and_keeps_old_marker(tmp_path,monkeypatch):
    marker=tmp_path/'compute-claim.json';marker.write_text('consumed')
    monkeypatch.setattr(completion,'GROUP',tmp_path)
    with pytest.raises(RuntimeError,match='COMPLETION_AUTHORIZATION_CONSUMED'):
        completion.run('a'*64)
    assert marker.read_text()=='consumed'


def test_source_freeze_includes_controller_and_tree_guard():
    pins=completion.sources()
    assert all(p in pins for p in completion.EXTRA)
    assert 'scripts/profile_planning_f4_1.py' in pins


def test_child_command_uses_same_interpreter_and_module_for_probe_and_compute():
    actual=completion.command('a'*64)
    probe=completion.command('a'*64,'probe')
    assert actual[:4]==probe[:4] and actual[4]=='child' and probe[4]=='probe'


@pytest.mark.skipif(os.name!='nt',reason='Windows job/venv contract')
def test_suspended_job_probe_terminates_launcher_child_and_descendant(tmp_path,monkeypatch):
    monkeypatch.setattr(completion,'GROUP',tmp_path)
    directory=completion.probe()
    result=json.loads((directory/'result.json').read_bytes())
    assert result['status']=='PASS' and result['job_active_after']==0
    assert result['job_active_before']>=2
    assert result['planning_executions']==result['native_inferences']==0
