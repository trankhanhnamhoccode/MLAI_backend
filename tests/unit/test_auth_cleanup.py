import pytest
from app.infrastructure.database.auth_session import auth_session


def test_primary_error_preserved_and_cleanup_failures_are_recorded(monkeypatch, caplog):
    import app.infrastructure.database.auth_session as module
    events = []
    class FaultedSession:
        def __init__(self, *args, **kwargs):
            pass
        def rollback(self):
            events.append("rollback")
            raise OSError("synthetic-rollback")
        def close(self):
            events.append("close")
            raise OSError("synthetic-close")
        def invalidate(self):
            events.append("invalidate")
    monkeypatch.setattr(module, "Session", FaultedSession)
    primary = ValueError("synthetic-primary")
    with pytest.raises(ValueError) as caught:
        with auth_session(None):
            raise primary
    assert caught.value is primary
    assert events == ["rollback", "close", "invalidate"]
    assert len(primary.__notes__) == 2
    assert "rollback failed" in caplog.text and "close failed" in caplog.text


def test_close_failure_on_success_still_errors(monkeypatch):
    import app.infrastructure.database.auth_session as module
    class FaultedSession:
        def __init__(self, *args, **kwargs):
            pass
        def close(self):
            raise OSError("synthetic-close")
        def invalidate(self):
            pass
    monkeypatch.setattr(module, "Session", FaultedSession)
    with pytest.raises(OSError):
        with auth_session(None):
            pass
