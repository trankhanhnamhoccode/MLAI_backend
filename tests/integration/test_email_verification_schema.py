"""Additive migration/metadata/proof state and evidence retention."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
import pytest
from app.infrastructure.database.base import Base
from app.models.auth import AuthAccount
from scripts.dev import migration_config
from uuid import uuid4
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.contracts.provisioning import VerifiedAccountCommand
from tests.integration.test_email_verification import env, signup, delivered_token, complete


def test_roundtrip_existing_proof_preserved_metadata_exact_and_evidence_retained(env):
    engine = env[0]
    settings = env[7]
    assisted = AssistedProvisioning(engine, settings, clock=lambda: env[1][0]).provision(
        VerifiedAccountCommand(request_reference=str(uuid4()), evidence_reference="retained-operator-proof",
            email="assisted@example.test", display_name="Assisted"), "synthetic", settings.auth_operator_key)
    command.downgrade(migration_config(), "0017_planning_exports")
    assert "email_verification_tokens" not in inspect(engine).get_table_names()
    command.upgrade(migration_config(), "head")
    with Session(engine) as fresh:
        proof = fresh.get(AuthAccount, assisted.user_id)
        assert proof.verified_at == env[1][0] and proof.verification_reference == "retained-operator-proof"
        assert proof.verified_email == "assisted@example.test" and not proof.credential_ready and proof.proof_revision == 1
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection, opts={"compare_server_default": True}), Base.metadata) == []
    signup(env)
    assert complete(env, delivered_token(env)).status_code == 200
    with Session(engine) as fresh:
        before = fresh.scalar(select(AuthAccount)).credential_revision
    with pytest.raises(Exception, match="B1 evidence requires retention"):
        command.downgrade(migration_config(), "0017_planning_exports")
    with Session(engine) as fresh:
        assert fresh.scalar(select(AuthAccount)).credential_revision == before
