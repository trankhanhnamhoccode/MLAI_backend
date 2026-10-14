"""C1 surface and explicit worker lifecycle; startup/health require no database."""
from threading import Event
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.application.use_cases.notification_delivery import NotificationDispatcher


def test_nf_surface_typed_and_exact_delta():
    app = create_app(Settings(_env_file=None, environment="test"))
    schema = app.openapi()
    operations = [(path, method, spec["operationId"]) for path, entry in schema["paths"].items()
                  for method, spec in entry.items() if method in {"get", "post", "put", "patch", "delete"}]
    assert len(operations) == 72 and len(schema["paths"]) == 66
    assert {item for item in operations if item[2].startswith("NF")} == {
        ("/api/v1/notifications", "get", "NF01"),
        ("/api/v1/notifications/unread-count", "get", "NF02"),
        ("/api/v1/notifications/{notification_id}", "patch", "NF03")}
    assert schema["components"]["schemas"]["ReadRequest"]["additionalProperties"] is False
    assert schema["components"]["schemas"]["ReadRequest"]["properties"]["read"]["type"] == "boolean"
    assert not any("notification" in path and any(word in path for word in ("send", "delivery", "jobs", "dismiss")) for path in schema["paths"])


def test_worker_explicit_opt_in_health_has_no_dispatch(monkeypatch):
    started = Event()
    calls = []
    def dispatch(self, limit):
        calls.append(limit)
        started.set()
        return 0
    monkeypatch.setattr(NotificationDispatcher, "dispatch", dispatch)
    settings = Settings(_env_file=None, environment="test",
        database_url="postgresql+psycopg://synthetic:synthetic@127.0.0.1:1/shelfcash_notifications_test")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
    assert not calls
    with TestClient(create_app(settings.model_copy(update={"notification_worker_enabled": True}))) as client:
        assert started.wait(3)
        assert client.get("/health").status_code == 200
    import threading
    assert calls == [20]
    assert not any(t.name == "shelfcash-notifications" for t in threading.enumerate())
