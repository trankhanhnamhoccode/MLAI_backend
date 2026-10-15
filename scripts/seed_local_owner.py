"""Create/reuse one synthetic Owner and empty Store in the owned local database.

Run: .venv/Scripts/python.exe -m scripts.seed_local_owner
Credentials: runtime/local/private/test-owner.json (never printed).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.application.contracts.auth import CredentialCompletion, LoginRequest
from app.application.contracts.provisioning import IssueCredentialCommand, ProvisionStoreCommand
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.provisioning import AssistedProvisioning
from app.config import Settings
from app.models.auth import AuthAccount
from scripts import local_runtime
from scripts.dev import inspect_database, require_head


EMAIL = "owner.local@example.test"
OPERATOR = "synthetic-local-owner-tool"
EVIDENCE = "User-authorized synthetic local test holder; not real-world identity proof"


def seed_owner(engine: Engine, settings: Settings, credentials_path: Path):
    """Application flow; CLI owns database guards. Never reset existing credentials."""
    if not credentials_path.exists():
        credentials_path.parent.mkdir(parents=True, exist_ok=True)
        # Persist recovery inputs before the first committed application mutation.
        with credentials_path.open("x", encoding="utf-8") as stream:
            json.dump({"email": EMAIL, "password": "Local!" + secrets.token_urlsafe(24)}, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    if credentials.get("email") != EMAIL:
        raise ValueError("Unexpected local test identity; preserve the private file")
    login = LoginRequest(**credentials)
    # Local synthetic operator only: never modify .env or expose a public endpoint.
    operator_key = SecretStr(secrets.token_urlsafe(32))
    local_settings = settings.model_copy(update={"auth_operator_id": OPERATOR, "auth_operator_key": operator_key})
    provisioning = AssistedProvisioning(engine, local_settings)
    receipt = provisioning.provision(ProvisionStoreCommand(
        request_reference="synthetic-local-owner-v1", evidence_reference=EVIDENCE,
        email=EMAIL, display_name="Local Test Owner", store_name="Local Test Store",
        timezone="Asia/Ho_Chi_Minh", currency="VND",
    ), OPERATOR, operator_key)
    with Session(engine) as fresh:
        account = fresh.get(AuthAccount, receipt.user_id)
        ready = account is not None and account.credential_ready
    auth = AuthUseCases(engine)
    if not ready:
        delivered = []
        delivery = provisioning.issue(IssueCredentialCommand(
            user_id=receipt.user_id, purpose="SETUP", verified_email=EMAIL,
            request_reference=str(uuid4()), evidence_reference=EVIDENCE,
        ), OPERATOR, operator_key, lambda address, token: delivered.append(token.get_secret_value()))
        if delivery.status != "delivered" or len(delivered) != 1:
            raise ValueError("Synthetic private delivery failed")
        auth.complete(CredentialCompletion(token=delivered[0], password=login.password), "local-owner-tool")
    context, token = auth.login(login, "local-owner-tool")
    try:
        store = auth.store_context(token, receipt.store_id)
        if store.membership.role != "OWNER":
            raise ValueError("Synthetic membership is no longer Owner; no authority restored")
    finally:
        auth.logout(token, context.session.csrf_token)
    return receipt


def main() -> int:
    engine = None
    try:
        settings, local = local_runtime.configuration()
        engine = local_runtime.engine(settings.database_url)
        with engine.connect() as connection:
            local_runtime.guard(connection, local_runtime.DB, local_runtime.RUNTIME)
        require_head(inspect_database(settings))
        receipt = seed_owner(engine, settings, local_runtime.PRIVATE / "test-owner.json")
        print(f"Local Owner ready: {EMAIL}; Store: {receipt.store_id}")
        print("Login credentials: runtime/local/private/test-owner.json")
        print("Re-run this command to reuse the same Owner/Store. No SMTP or business fixtures.")
        return 0
    except Exception:
        print("Local Owner setup failed. Check local DB/config and preserve test-owner.json; no credentials logged.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
