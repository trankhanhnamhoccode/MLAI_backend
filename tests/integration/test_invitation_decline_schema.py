"""Additive 0022 on Auth0020; no audit/token evidence is erased by downgrade."""
from uuid import UUID
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
import pytest

from app.infrastructure.database.base import Base
from scripts.dev import migration_config
from tests.integration.test_auth_public import env
from tests.integration.test_staff_public import staff_env, create
from tests.integration.test_invitation_decline import decline_http


def test_additive_pending_preservation_metadata_and_decline_retention(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    engine = ctx[0][1]
    with engine.connect() as c:
        before = tuple(c.execute(text('SELECT id,token_digest,version,status,offered_grants FROM staff_invitations')).one())
    command.downgrade(migration_config(),'0020_password_reset_delivery')
    assert 'declined_at' not in {col['name'] for col in inspect(engine).get_columns('staff_invitations')}
    command.upgrade(migration_config(),'head')
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0023_auth_permissions_v3'
        assert tuple(c.execute(text('SELECT id,token_digest,version,status,offered_grants FROM staff_invitations')).one()) == before
        assert compare_metadata(MigrationContext.configure(c, opts={'compare_server_default': True}),Base.metadata) == []
    response = decline_http(ctx,data,raw)
    assert response.status_code == 200
    with pytest.raises(Exception, match='B3 decline evidence requires retention'):
        command.downgrade(migration_config(),'0020_password_reset_delivery')
    with engine.connect() as c:
        assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0023_auth_permissions_v3'
        assert c.scalar(text('SELECT count(*) FROM staff_invitations WHERE status=\'declined\'')) == 1
