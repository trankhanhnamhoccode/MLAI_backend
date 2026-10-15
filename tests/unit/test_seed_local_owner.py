"""CLI must reject a failed ownership guard before writing credentials or accounts."""
from types import SimpleNamespace

import pytest
from scripts import seed_local_owner, seed_local_staff


@pytest.mark.parametrize("seed", [seed_local_owner, seed_local_staff])
def test_failed_database_guard_does_not_seed(monkeypatch, capsys, seed):
    class Engine:
        disposed = False
        def connect(self):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def dispose(self):
            self.disposed = True
    engine = Engine()
    monkeypatch.setattr(seed.local_runtime, "configuration", lambda: (SimpleNamespace(database_url="unused"), None))
    monkeypatch.setattr(seed.local_runtime, "engine", lambda url: engine)
    def reject(*args):
        raise ValueError("secret database detail")
    monkeypatch.setattr(seed.local_runtime, "guard", reject)
    def forbidden(*args):
        raise AssertionError("seed must not run")
    monkeypatch.setattr(seed, "seed_owner", forbidden)
    if seed is seed_local_staff:
        monkeypatch.setattr(seed, "seed_staff", forbidden)
    assert seed.main() == 1
    assert engine.disposed
    assert "secret database detail" not in capsys.readouterr().out
