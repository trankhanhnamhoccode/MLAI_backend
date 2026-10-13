"""0020 is additive on Auth0018; private RESET evidence is retained."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
import pytest
from app.infrastructure.database.base import Base
from app.models.auth import AuthAccount
from scripts.dev import migration_config
from tests.integration.test_password_reset import env, reset_env, verified, request_reset


def test_additive_roundtrip_preserves_b1_proof_metadata_and_refuses_evidence_loss(reset_env):
    env = reset_env[0]
    uid = verified(env)
    with Session(env[0]) as fresh:
        account = fresh.get(AuthAccount, uid)
        before = (account.verified_at, account.verification_reference, account.credential_revision, account.proof_revision)
    command.downgrade(migration_config(), "0018_email_verification")
    assert "password_reset_deliveries" not in inspect(env[0]).get_table_names()
    command.upgrade(migration_config(), "head")
    with env[0].connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0025_notifications_foundation"
        assert compare_metadata(MigrationContext.configure(connection, opts={"compare_server_default": True}), Base.metadata) == []
    with Session(env[0]) as fresh:
        account = fresh.get(AuthAccount, uid)
        assert (account.verified_at, account.verification_reference, account.credential_revision, account.proof_revision) == before
    request_reset(reset_env)
    with pytest.raises(Exception, match="B2 evidence requires retention"):
        command.downgrade(migration_config(), "0018_email_verification")
