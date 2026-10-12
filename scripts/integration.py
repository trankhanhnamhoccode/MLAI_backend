"""Owned, isolated S4.11 local environment; no public administrative endpoint."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import inspect_database, migration_config, require_head

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runtime/s411/private"
DB = "shelfcash_integration_s411"
ROLE = "shelfcash_integration"
MARKER = "ShelfCash S4.11 disposable integration v1"


def write_json(path: Path, value: object) -> None:
    if not path.resolve().is_relative_to(PRIVATE.resolve()):
        raise ValueError("Private path outside integration runtime")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def validate_target(settings: Settings) -> None:
    url = make_url(settings.database_url)
    if (settings.environment != "test" or url.drivername != "postgresql+psycopg"
            or url.host != "127.0.0.1" or url.port != 5433 or url.database != DB
            or url.username != ROLE or url.query):
        raise ValueError("Exact isolated integration target required")
    for value, expected in ((settings.runtime_directory, PRIVATE / "app"),
                            (settings.upload_directory, PRIVATE / "app/uploads"),
                            (settings.model_artifact_directory, PRIVATE / "app/models")):
        if Path(value).resolve() != expected.resolve():
            raise ValueError("Exact owned integration storage required")
    if settings.openrouter_api_key is not None or settings.openrouter_model is not None:
        raise ValueError("Integration v1 forbids live provider configuration")


def settings() -> Settings:
    values = json.loads((PRIVATE / "settings.json").read_text(encoding="utf-8"))
    result = Settings(_env_file=None, **values)
    validate_target(result)
    return result


def init() -> None:
    if (PRIVATE / "settings.json").exists():
        validate_target(settings())
        print("Existing integration configuration preserved.")
        return
    password = secrets.token_urlsafe(32)
    values = dict(environment="test", database_url=f"postgresql+psycopg://{ROLE}:{password}@127.0.0.1:5433/{DB}",
                  runtime_directory=str(PRIVATE / "app"), upload_directory=str(PRIVATE / "app/uploads"),
                  model_artifact_directory=str(PRIVATE / "app/models"), auth_dev_cookie=True,
                  auth_allowed_origins=["http://localhost:5173"], auth_operator_id="s411-local-integration",
                  auth_operator_key=secrets.token_urlsafe(32),
                  auth_delivery_encryption_key=base64.b64encode(secrets.token_bytes(32)).decode(),
                  import_worker_enabled=True, planning_worker_enabled=True, pdf_export_worker_enabled=True,
                  openrouter_api_key=None, openrouter_model=None)
    validate_target(Settings(_env_file=None, **values))
    write_json(PRIVATE / "settings.json", values)
    env = PRIVATE / "compose.env"
    env.write_text(f"S411_POSTGRES_PASSWORD={password}\n", encoding="utf-8")
    env.chmod(0o600)
    write_json(PRIVATE / "state.json", {"version": 1, "store_allowlist": [], "dataset": None})
    print("Private integration configuration generated; no credentials printed.")


def connected_guard(engine, *, marker: bool = True, stores: bool = True) -> None:
    with engine.connect() as c:
        if c.scalar(text("SELECT current_database()")) != DB:
            raise ValueError("Connected database mismatch")
        if marker and c.scalar(text("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=current_database()")) != MARKER:
            raise ValueError("Disposable database ownership marker missing")
        if stores and c.scalar(text("SELECT to_regclass('public.stores')")):
            actual = {str(x) for x in c.scalars(text("SELECT id FROM stores"))}
            allowed = set(json.loads((PRIVATE / "state.json").read_text(encoding="utf-8"))["store_allowlist"])
            if actual != allowed:
                raise ValueError("Store allowlist differs from actual integration Stores")


def migrate() -> None:
    s = settings()
    engine = create_database_engine(s)
    try:
        connected_guard(engine, marker=False)
        with engine.begin() as c:
            old_marker = c.scalar(text("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=current_database()"))
            if old_marker != MARKER and (old_marker is not None or inspect(c).get_table_names(schema="public")):
                raise ValueError("Refusing to claim an existing unowned database")
            c.execute(text(f"COMMENT ON DATABASE {DB} IS '{MARKER}'"))
    finally:
        engine.dispose()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = s.database_url
    try:
        command.upgrade(migration_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    state = inspect_database(s)
    require_head(state)
    print(json.dumps({k: state[k] for k in ("database", "revisions", "expected_heads", "at_head")}))


def start() -> None:
    settings()
    state = inspect_database(settings())
    require_head(state)
    owned = PRIVATE / "server.json"
    if owned.exists():
        old = json.loads(owned.read_text(encoding="utf-8"))
        exit_file = PRIVATE / "server-exit.json"
        if not exit_file.exists() or json.loads(exit_file.read_text(encoding="utf-8")).get("run_id") != old["run_id"]:
            raise ValueError("Previous server has no matching completion evidence; inspect ownership before starting")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1",18001)) == 0:
            raise ValueError("Backend port occupied; no unknown process replaced or killed")
    token = str(uuid4())
    for path in (PRIVATE / "server-exit.json", PRIVATE / "stop.json"):
        if path.exists():
            path.unlink()
    with (PRIVATE / "server.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "scripts.integration_server", token], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    write_json(owned, {"pid": process.pid, "run_id": token})
    deadline=time.monotonic()+50
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise ValueError("Owned server exited before readiness; inspect private completion/log")
        try:
            with urlopen("http://localhost:18001/health",timeout=0.5) as response:
                if response.status==200:
                    print("Owned backend ready on http://localhost:18001; native lifespan started.")
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise ValueError("Owned server startup unverified; no second server launched")


def recover_stopped() -> None:
    """Record an unclean local shutdown only with positive OS/port/DB evidence."""
    from app.infrastructure.planning_process import _birth
    s = settings()
    owned = json.loads((PRIVATE / "server.json").read_text(encoding="utf-8"))
    if _birth(owned["pid"])[0] != "DEAD":
        raise ValueError("Recorded server is alive or unknown; recovery refused")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18001)) == 0:
            raise ValueError("Backend port occupied; recovery refused")
    engine = create_database_engine(s)
    try:
        connected_guard(engine)
        with engine.connect() as connection:
            clients = connection.scalar(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=:name AND pid<>pg_backend_pid()"
            ), {"name": DB})
            if clients:
                raise ValueError("Integration clients remain; recovery refused")
    finally:
        engine.dispose()
    write_json(PRIVATE / "server-exit.json", {
        "run_id": owned["run_id"], "exit_code": None,
        "recovery": "OS_DEAD_PORT_FREE_NO_DB_CLIENTS",
        "finished_at_unix": time.time(),
    })
    print("Unclean server shutdown established; data and artifacts preserved.")


def stop() -> None:
    owned = json.loads((PRIVATE / "server.json").read_text(encoding="utf-8"))
    write_json(PRIVATE / "stop.json", {"run_id": owned["run_id"]})
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        path = PRIVATE / "server-exit.json"
        if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("run_id") == owned["run_id"]:
            print("Owned server and workers stopped with completion evidence.")
            return
        time.sleep(0.2)
    raise ValueError("Graceful stop unverified; no process killed, reset forbidden")


def reset_disposable() -> None:
    s = settings()
    if (PRIVATE / "server.json").exists():
        owned = json.loads((PRIVATE / "server.json").read_text(encoding="utf-8"))
        exit_path = PRIVATE / "server-exit.json"
        if not exit_path.exists() or json.loads(exit_path.read_text(encoding="utf-8")).get("run_id") != owned["run_id"]:
            raise ValueError("Stop the identified server/three workers first")
    engine = create_database_engine(s)
    try:
        connected_guard(engine)
    finally:
        engine.dispose()
    admin = create_engine(make_url(s.database_url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            if c.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"), {"name": DB}):
                raise ValueError("Integration clients remain; no sessions terminated")
            # Exact constants only; DROP DATABASE itself refuses a racing connection.
            c.execute(text(f"DROP DATABASE {DB}"))
            c.execute(text(f"CREATE DATABASE {DB} OWNER {ROLE}"))
    finally:
        admin.dispose()
    write_json(PRIVATE / "state.json", {"version": 1, "store_allowlist": [], "dataset": None})
    # Keep old private artifact generations for diagnosis. Never reuse them after reset.
    current = PRIVATE / "app"
    if current.exists():
        destination = PRIVATE / ("retired-app-" + str(uuid4()))
        if not current.resolve().is_relative_to(PRIVATE.resolve()) or not destination.resolve().is_relative_to(PRIVATE.resolve()):
            raise ValueError("Artifact generation containment failure")
        current.rename(destination)
    for filename in ("accounts.json", "dataset.json", "e2e.json"):
        path = PRIVATE / filename
        if path.exists():
            path.unlink()
    migrate()
    print("Owned disposable DB recreated; old artifacts retained privately, seed required.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "migrate", "status", "start", "stop", "recover-stopped", "reset-disposable", "seed", "e2e", "cases", "restart-check"))
    args = parser.parse_args()
    try:
        if args.action == "status":
            s = settings()
            engine = create_database_engine(s)
            try:
                connected_guard(engine)
            finally:
                engine.dispose()
            print(json.dumps(inspect_database(s), indent=2))
        elif args.action in ("seed", "e2e", "cases", "restart-check"):
            from scripts.integration_workflow import seed, verify, verify_cases, verify_restart
            {"seed":seed,"e2e":verify,"cases":verify_cases,"restart-check":verify_restart}[args.action]()
        else:
            {"init": init, "migrate": migrate, "start": start, "stop": stop,
             "recover-stopped": recover_stopped,
             "reset-disposable": reset_disposable}[args.action]()
    except Exception as error:
        from scripts.integration_workflow import WireFailure
        if isinstance(error,WireFailure):
            print(str(error))
        print(f"Integration command failed ({type(error).__name__}); no credentials/raw errors printed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
