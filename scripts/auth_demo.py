"""Owned local Auth demo. Never resets a database or prints configuration secrets."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import ipaddress
import json
import os
from pathlib import Path
import secrets
import smtplib
import socket
import ssl
import subprocess
import sys
import threading
import time

from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import inspect_database, migration_config, require_head

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "runtime/auth-demo/private"
DB = ROLE = "shelfcash_auth_demo"
MARKER = "ShelfCash owned Auth SMTP demo v1"
ORIGIN = "https://localhost:5173"


def private_json(name: str, value: object) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / name
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    path.chmod(0o600)


def settings() -> Settings:
    values = json.loads((PRIVATE / "settings.json").read_text(encoding="utf-8"))
    result = Settings(**values)  # SMTP only comes from the user's .env/environment.
    url = make_url(result.database_url)
    if (url.drivername, url.host, url.port, url.database, url.username) != (
        "postgresql+psycopg", "127.0.0.1", 5434, DB, ROLE
    ) or url.query or result.environment != "development":
        raise ValueError("Exact owned Auth demo target required")
    if any((result.import_worker_enabled, result.planning_worker_enabled,
            result.pdf_export_worker_enabled, result.import_llm_suggestions_enabled)):
        raise ValueError("Only the Auth delivery worker is permitted")
    if result.auth_smtp_host != "smtp.gmail.com" or result.auth_smtp_port != 465:
        raise ValueError("Gmail SSL port 465 required")
    if not all((result.auth_smtp_username, result.auth_smtp_password,
                result.auth_smtp_password.get_secret_value(), result.auth_delivery_sender)):
        raise ValueError("SMTP credentials/sender missing")
    return result


def certificate() -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
            ]), critical=False).sign(key, hashes.SHA256()))
    (PRIVATE / "localhost.key").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (PRIVATE / "localhost.key").chmod(0o600)
    (PRIVATE / "localhost.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def compose(*args: str) -> None:
    result = subprocess.run(["docker", "compose", "-p", "shelfcash-auth-demo",
        "--env-file", str(PRIVATE / "compose.env"), "-f", str(ROOT / "scripts/auth_demo.compose.yaml"),
        *args], capture_output=True)
    if result.returncode:
        raise RuntimeError("Auth demo Docker command failed (output withheld)")


def connected_guard(engine, *, claim: bool = False) -> None:
    with engine.begin() as c:
        if tuple(c.execute(text("SELECT current_database(),current_user")).one()) != (DB, ROLE):
            raise ValueError("Connected demo identity mismatch")
        marker = c.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
        if marker != MARKER:
            if not claim or marker is not None or c.scalar(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")):
                raise ValueError("Refusing unowned/nonempty database")
            c.execute(text(f"COMMENT ON DATABASE {DB} IS '{MARKER}'"))


def init() -> None:
    if not (PRIVATE / "settings.json").exists():
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", 5434)) == 0:
                raise ValueError("Demo database port occupied; refusing replacement")
        password = secrets.token_urlsafe(32)
        private_json("settings.json", dict(environment="development",
            database_url=f"postgresql+psycopg://{ROLE}:{password}@127.0.0.1:5434/{DB}",
            runtime_directory=str(PRIVATE / "app"), upload_directory=str(PRIVATE / "app/uploads"),
            model_artifact_directory=str(PRIVATE / "app/models"),
            auth_allowed_origins=[ORIGIN], auth_dev_cookie=False,
            auth_frontend_url=ORIGIN + "/setup-password",
            auth_verification_frontend_url=ORIGIN + "/verify-email",
            auth_password_reset_frontend_url=ORIGIN + "/reset-password",
            auth_email_delivery_enabled=True,
            auth_delivery_encryption_key=base64.b64encode(secrets.token_bytes(32)).decode(),
            import_worker_enabled=False, planning_worker_enabled=False,
            pdf_export_worker_enabled=False, import_llm_suggestions_enabled=False,
            openrouter_api_key=None, openrouter_model=None))
        (PRIVATE / "compose.env").write_text(f"AUTH_DEMO_DB_PASSWORD={password}\n", encoding="utf-8")
        (PRIVATE / "compose.env").chmod(0o600)
        certificate()
    s = settings()
    compose("up", "-d", "--wait")
    engine = create_database_engine(s)
    try:
        connected_guard(engine, claim=True)
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
    status()


def status() -> None:
    s = settings()
    engine = create_database_engine(s)
    try:
        connected_guard(engine)
    finally:
        engine.dispose()
    state = inspect_database(s)
    require_head(state)
    print(json.dumps({k: state[k] for k in ("database", "revisions", "at_head")}))
    from app.infrastructure.email_verification_transport import VerificationEmailTransport
    if not all(VerificationEmailTransport(s, purpose=p).available for p in ("EMAIL_VERIFY", "RESET")):
        raise ValueError("Demo delivery capability unavailable")
    print("Gmail SSL/certificate verification configured; verify/reset ready; non-Auth workers disabled.")


def smoke() -> None:
    s = settings()
    record = PRIVATE / "smtp-smoke.json"
    # Reserve before any network action. Ambiguous failures are never retried.
    with record.open("x", encoding="utf-8") as handle:
        json.dump({"outcome": "ATTEMPT_RESERVED", "inbox_confirmed": False}, handle)
    record.chmod(0o600)
    try:
        message = EmailMessage()
        message["From"] = s.auth_delivery_sender
        message["To"] = s.auth_smtp_username
        message["Subject"] = "ShelfCash local Auth SMTP smoke"
        message.set_content("One authorized local SMTP smoke test. No authentication token or password is included. Please confirm receipt in your inbox.")
        with smtplib.SMTP_SSL(s.auth_smtp_host, s.auth_smtp_port,
                context=ssl.create_default_context(), timeout=15) as client:
            client.login(s.auth_smtp_username, s.auth_smtp_password.get_secret_value())
            refused = client.send_message(message, to_addrs=[s.auth_smtp_username])
            if refused:
                raise RuntimeError("Recipient rejected")
            # DATA has returned successfully. QUIT failure must not obscure acceptance.
            private_json("smtp-smoke.json", {"outcome": "SMTP_ACCEPTED", "inbox_confirmed": False})
        print("SMTP accepted one message to AUTH_SMTP_USERNAME; inbox arrival requires user confirmation.")
    except Exception as exc:
        current = json.loads(record.read_text(encoding="utf-8"))
        if current["outcome"] != "SMTP_ACCEPTED":
            private_json("smtp-smoke.json", {"outcome": "FAILED_OR_UNCERTAIN", "error_type": type(exc).__name__,
                "smtp_code": getattr(exc, "smtp_code", None), "inbox_confirmed": False})
        print(json.dumps(json.loads(record.read_text(encoding="utf-8"))))
        raise RuntimeError("SMTP smoke failed/uncertain; details redacted; no retry") from None


def serve() -> None:
    import uvicorn
    from app.main import create_app
    status()
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8102)) == 0:
            raise ValueError("Port 8102 occupied; no existing process replaced")
    s = settings()
    app = create_app(s)
    # Operational demo-only recipient boundary; production semantics are untouched.
    for dispatcher in (app.state.email_verification_dispatcher, app.state.password_reset_dispatcher):
        dispatcher.transport = SelfOnlyTransport(dispatcher.transport, s.auth_smtp_username)
    stop_path = PRIVATE / "stop"
    stop_path.unlink(missing_ok=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8102,
        ssl_keyfile=str(PRIVATE / "localhost.key"), ssl_certfile=str(PRIVATE / "localhost.pem"),
        access_log=False))
    done = threading.Event()
    def watch():
        while not done.wait(0.2):
            if stop_path.exists():
                server.should_exit = True
                return
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        server.run()
    finally:
        done.set()
        watcher.join(timeout=1)
        private_json("server-exit.json", {"stopped": True, "time": time.time()})


class SelfOnlyTransport:
    """Local operator boundary, shared by both durable delivery dispatchers."""
    def __init__(self, transport, address: str):
        self.transport = transport
        self.address = address.strip().casefold()

    @property
    def available(self) -> bool:
        return self.transport.available

    def __call__(self, address, token):
        if address.strip().casefold() != self.address:
            raise RuntimeError("Auth demo recipient not permitted")
        return self.transport(address, token)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "smoke", "serve", "stop", "db-stop"))
    action = parser.parse_args().command
    try:
        if action == "stop":
            settings()
            (PRIVATE / "stop").touch()
            print("Graceful stop requested; wait for server exit before db-stop.")
        elif action == "db-stop":
            settings()
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", 8102)) == 0:
                    raise ValueError("Stop server before stopping demo database")
            compose("stop")
            print("Demo DB stopped; named volume/data preserved.")
        else:
            globals()[action]()
        return 0
    except Exception as exc:
        print(f"Auth demo command failed: {type(exc).__name__}; details withheld to protect secrets.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
