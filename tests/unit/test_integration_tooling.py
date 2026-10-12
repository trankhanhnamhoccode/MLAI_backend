"""Local operator tooling must not inherit development/test/reset authority."""
import pytest

from app.config import Settings
from scripts.integration import DB, PRIVATE, ROLE, validate_target
from scripts.dev import validate_reset_target


def integration_settings(**changes):
    values = dict(environment="test", database_url=f"postgresql+psycopg://{ROLE}:synthetic@127.0.0.1:5433/{DB}",
                  runtime_directory=PRIVATE/"app", upload_directory=PRIVATE/"app/uploads",
                  model_artifact_directory=PRIVATE/"app/models",openrouter_api_key=None,openrouter_model=None)
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_isolation_both_directions():
    s=integration_settings()
    validate_target(s)
    with pytest.raises(ValueError):validate_reset_target(s)
    for database in ("shelfcash","shelfcash_test","postgres"):
        with pytest.raises(ValueError):
            validate_target(integration_settings(database_url=f"postgresql+psycopg://{ROLE}:synthetic@127.0.0.1:5433/{database}"))


@pytest.mark.parametrize("change",[
    {"environment":"development"},{"environment":"production"},
    {"database_url":f"postgresql+psycopg://{ROLE}:synthetic@localhost:5433/{DB}"},
    {"database_url":f"postgresql+psycopg://{ROLE}:synthetic@127.0.0.1:5432/{DB}"},
    {"database_url":f"postgresql+psycopg://shelfcash:synthetic@127.0.0.1:5433/{DB}"},
    {"database_url":f"postgresql+psycopg://{ROLE}:synthetic@127.0.0.1:5433/{DB}?options=-csearch_path%3Dother"},
    {"runtime_directory":"runtime"},{"upload_directory":"runtime/uploads"},
    {"model_artifact_directory":"runtime/model_artifacts"},
    {"openrouter_api_key":"synthetic-never-called"},{"openrouter_model":"some-provider"},
])
def test_target_guard_refuses_ambient_or_foreign_resources(change):
    with pytest.raises(ValueError):validate_target(integration_settings(**change))


def test_settings_preserve_default_off_workers():
    settings=Settings(_env_file=None,import_worker_enabled=False,planning_worker_enabled=False,pdf_export_worker_enabled=False)
    assert not settings.import_worker_enabled and not settings.planning_worker_enabled and not settings.pdf_export_worker_enabled


@pytest.mark.parametrize("state", ["ALIVE", "UNKNOWN"])
def test_recovery_refuses_live_or_unknown_owner(tmp_path, monkeypatch, state):
    import json
    from scripts import integration
    from app.infrastructure import planning_process
    (tmp_path / "server.json").write_text(json.dumps({"pid": 123, "run_id": "synthetic"}))
    monkeypatch.setattr(integration, "PRIVATE", tmp_path)
    monkeypatch.setattr(integration, "settings", lambda: integration_settings())
    monkeypatch.setattr(planning_process, "_birth", lambda pid: (state, None))
    monkeypatch.setattr(integration, "create_database_engine", lambda s: pytest.fail("No DB access allowed"))
    with pytest.raises(ValueError, match="alive or unknown"):
        integration.recover_stopped()
    assert not (tmp_path / "server-exit.json").exists()


def test_recovery_refuses_occupied_port(tmp_path, monkeypatch):
    import json
    from scripts import integration
    from app.infrastructure import planning_process
    (tmp_path / "server.json").write_text(json.dumps({"pid": 123, "run_id": "synthetic"}))
    monkeypatch.setattr(integration, "PRIVATE", tmp_path)
    monkeypatch.setattr(integration, "settings", lambda: integration_settings())
    monkeypatch.setattr(planning_process, "_birth", lambda pid: ("DEAD", None))
    class Occupied:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect_ex(self, address): return 0
    monkeypatch.setattr(integration.socket, "socket", Occupied)
    monkeypatch.setattr(integration, "create_database_engine", lambda s: pytest.fail("No DB access allowed"))
    with pytest.raises(ValueError, match="port occupied"):
        integration.recover_stopped()
    assert not (tmp_path / "server-exit.json").exists()


@pytest.mark.parametrize("clients", [0, 1])
def test_recovery_requires_no_db_clients_and_retains_run_id(tmp_path, monkeypatch, clients):
    import json
    from scripts import integration
    from app.infrastructure import planning_process
    (tmp_path / "server.json").write_text(json.dumps({"pid": 123, "run_id": "synthetic"}))
    monkeypatch.setattr(integration, "PRIVATE", tmp_path)
    monkeypatch.setattr(integration, "settings", lambda: integration_settings())
    monkeypatch.setattr(planning_process, "_birth", lambda pid: ("DEAD", None))
    class FreePort:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect_ex(self, address): return 1
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def scalar(self, query, params):
            assert params == {"name": integration.DB}
            assert "pid<>pg_backend_pid()" in str(query)
            return clients
    class Engine:
        disposed = False
        def connect(self): return Connection()
        def dispose(self): self.disposed = True
    engine = Engine()
    checked = []
    monkeypatch.setattr(integration.socket, "socket", FreePort)
    monkeypatch.setattr(integration, "create_database_engine", lambda s: engine)
    monkeypatch.setattr(integration, "connected_guard", lambda e: checked.append(e))
    if clients:
        with pytest.raises(ValueError, match="clients remain"):
            integration.recover_stopped()
        assert not (tmp_path / "server-exit.json").exists()
    else:
        integration.recover_stopped()
        receipt = json.loads((tmp_path / "server-exit.json").read_text())
        assert receipt["run_id"] == "synthetic" and receipt["exit_code"] is None
        assert receipt["recovery"] == "OS_DEAD_PORT_FREE_NO_DB_CLIENTS"
    assert checked == [engine] and engine.disposed
