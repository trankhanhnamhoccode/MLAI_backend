"""Catalogue-only migration preserves Auth state and refuses destructive rollback."""
import json
import os
import subprocess
import sys
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.models.auth import MembershipGrant
from app.models.staff import StaffInvitation, InvitationDeliveryIntent
from scripts.dev import migration_config
from tests.integration.test_auth_public import env, KEY
from tests.integration.test_staff_public import staff_env, create, accept_http, owner_session, target_session


def snapshot(engine):
    with engine.connect() as connection:
        return {
            table: list(connection.execute(text(query)).all()) for table, query in {
                'memberships': 'SELECT id,authorization_revision,active FROM store_memberships ORDER BY id',
                'grants': 'SELECT membership_id,permission FROM membership_grants ORDER BY membership_id,permission',
                'invitations': 'SELECT id,token_digest,version,status,offered_grants FROM staff_invitations ORDER BY id',
            }.items()
        }


def test_additive_catalogue_preserves_grants_revisions_and_pending_tokens(staff_env):
    ctx = staff_env
    command.downgrade(migration_config(), '0017_planning_exports')
    command.upgrade(migration_config(), '0023_auth_permissions_v3')
    accepted, raw = create(ctx)
    assert accept_http(ctx, accepted, raw).status_code == 201
    owner_session(ctx)
    pending, _ = create(ctx, email='pending@example.test')
    engine = ctx[0][1]
    before = snapshot(engine)
    command.downgrade(migration_config(), '0022_invitation_decline')
    assert snapshot(engine) == before
    command.upgrade(migration_config(), '0023_auth_permissions_v3')
    assert snapshot(engine) == before
    with engine.connect() as connection:
        actual_tables = set(connection.dialect.get_table_names(connection))
        assert actual_tables == (set(Base.metadata.tables) - {'import_history_records', 'notification_intents', 'notifications', 'notification_read_receipts', 'permission_requests', 'permission_request_audit', 'mapping_submissions'}) | {'alembic_version'}
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0023_auth_permissions_v3'
    # Explicitly granted new keys make downgrade unsafe; retain them and the head.
    with Session(engine) as session:
        mid = session.scalar(select(MembershipGrant.membership_id))
        session.add(MembershipGrant(membership_id=mid, permission='calendar.read'))
        session.commit()
    with pytest.raises(RuntimeError, match='Retained v3 grants prevent downgrade'):
        command.downgrade(migration_config(), '0022_invitation_decline')
    with Session(engine) as fresh:
        assert fresh.get(MembershipGrant, (mid, 'calendar.read')) is not None
        assert fresh.get(StaffInvitation, UUID(pending['invitation']['invitation_id'])).status == 'pending'
        assert fresh.scalar(text('SELECT version_num FROM alembic_version')) == '0023_auth_permissions_v3'
    # Keep the original exact metadata assertion against the combined model,
    # after installing the companion branch without changing retained Auth state.
    command.upgrade(migration_config(), 'head')
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0026_collaboration_requests'


def test_persisted_v2_offer_needs_owner_reissue_not_automatic_grants(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    identifier = UUID(data['invitation']['invitation_id'])
    with Session(ctx[0][1]) as session:
        session.get(StaffInvitation, identifier).permission_catalog_version = 'permissions-v2'
        session.commit()
    response = accept_http(ctx, data, raw)
    assert response.status_code == 409 and response.json()['error']['code'] == 'PERMISSION_CATALOG_CHANGED'
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(StaffInvitation, identifier).status == 'pending'
        assert fresh.scalar(select(MembershipGrant)) is None
    owner_session(ctx)
    response = ctx[0][5].post(f'/api/v1/stores/{ctx[2].store_id}/staff-invitations/{identifier}/actions',
        headers=ctx[5] | {'Idempotency-Key': str(uuid4()), 'If-Match': data['invitation']['version']},
        json={'action': 'reissue', 'permission_catalog_version': 'permissions-v3',
            'grants': ['calendar.read'], 'reason': 'Owner reviews new catalogue'})
    assert response.status_code == 200, response.text
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation, identifier)
        assert row.permission_catalog_version == 'permissions-v3' and row.version != data['invitation']['version']
        assert fresh.scalar(select(MembershipGrant)) is None
    assert accept_http(ctx, data, raw).status_code == 404


def test_pending_invitation_delivery_recovers_after_process_restart(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    identifier = UUID(data['delivery']['attempt_id'])
    code = '''
import json,os
from datetime import datetime
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from app.config import Settings
from scripts.dev import validate_reset_target
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.invitation_delivery import InvitationDispatcher
s=Settings(_env_file=None,environment='test',database_url=os.environ['B4_TEST_URL'],
 auth_delivery_encryption_key=SecretStr(os.environ['B4_TEST_KEY']),
 auth_operator_id='support-test',auth_operator_key=SecretStr('SYNTHETIC-OPERATOR-CREDENTIAL'))
u=make_url(s.database_url)
assert u.database==os.environ['B4_TEST_DATABASE'] and u.username==os.environ['B4_TEST_USER']
validate_reset_target(s)
engine=create_database_engine(s)
def sink(address,identifier,secret):
 assert address=='staff@example.test' and engine.pool.checkedout()==0
 assert len(secret.get_secret_value())>=32
try:
 print(json.dumps(InvitationDispatcher(engine,s,lambda:datetime.fromisoformat(os.environ['B4_TEST_NOW'])).dispatch(s.auth_operator_id,s.auth_operator_key,sink)))
finally:
 engine.dispose()
'''
    from sqlalchemy.engine import make_url
    fixture_url = make_url(ctx[0][0].database_url)
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30,
        env=dict(os.environ, B4_TEST_DATABASE=fixture_url.database, B4_TEST_USER=fixture_url.username, B4_TEST_URL=ctx[0][0].database_url,
            B4_TEST_KEY=ctx[1].settings.auth_delivery_encryption_key.get_secret_value(),
            B4_TEST_NOW=ctx[0][4][0].isoformat()))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['delivered'] == 1
    assert raw not in result.stdout + result.stderr
    with Session(ctx[0][1]) as fresh:
        intent = fresh.get(InvitationDeliveryIntent, identifier)
        assert intent.status == 'delivered' and intent.ciphertext is None
        assert fresh.get(StaffInvitation, UUID(data['invitation']['invitation_id'])).status == 'pending'
        assert fresh.scalar(select(MembershipGrant)) is None
