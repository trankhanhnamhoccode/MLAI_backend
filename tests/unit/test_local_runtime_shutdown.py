"""Reproduce Windows observation replacement failures without starting workers."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import local_runtime as local


def test_atomic_save_retries_temporary_windows_denial(tmp_path, monkeypatch):
    monkeypatch.setattr(local, 'PRIVATE', tmp_path)
    monkeypatch.setattr(local.time, 'sleep', lambda seconds: None)
    replace = Path.replace
    attempts = []
    def transient(path, target):
        attempts.append(target)
        if len(attempts) < 3:
            raise PermissionError('synthetic sharing violation')
        return replace(path, target)
    monkeypatch.setattr(Path, 'replace', transient)
    local.save('workers.json', {'run_id': 'test'})
    assert json.loads((tmp_path / 'workers.json').read_text()) == {'run_id': 'test'}
    assert len(attempts) == 3


def test_atomic_save_persistent_denial_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(local, 'PRIVATE', tmp_path)
    monkeypatch.setattr(local.time, 'sleep', lambda seconds: None)
    attempts = []
    def denied(path, target):
        attempts.append(target)
        raise PermissionError('synthetic sharing violation')
    monkeypatch.setattr(Path, 'replace', denied)
    with pytest.raises(PermissionError):
        local.save('workers.json', {'run_id': 'test'})
    assert len(attempts) == 6


def test_watcher_survives_observation_error_then_stops_only_matching_run(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(local, 'PRIVATE', tmp_path)
    monkeypatch.setattr(local, 'profile_digest', lambda *args: 'test')
    (tmp_path / 'stop.json').write_text(json.dumps({'run_id': 'previous'}))
    observations = []
    def denied(name, value):
        observations.append(name)
        raise PermissionError('synthetic sharing violation')
    monkeypatch.setattr(local, 'save', denied)
    server = SimpleNamespace(started=True, should_exit=False)
    class Finished:
        calls = 0
        def wait(self, seconds):
            self.calls += 1
            if self.calls == 2:
                assert not server.should_exit
                (tmp_path / 'stop.json').write_text(json.dumps({'run_id': 'current'}))
            assert self.calls <= 2, 'Watcher did not stop'
            return False
    local.watch_server(server, Finished(), 'current', None, None)
    assert server.should_exit
    assert observations == ['workers.json']
    assert 'shutdown watcher remains active' in caplog.text
