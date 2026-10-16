"""Real traversal from either accepted head, catalogue overlap and retained grants."""
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import create_database_engine
from scripts.dev import migration_config

IMPORT = '0021_import_support_history'
AUTH = '0023_auth_permissions_v3'
HEAD = 'l5_20261016_assistant_f4'
KEYS = ('calendar.read', 'calendar.write', 'usage.history.read',
        'usage.history.write', 'purchase.history.read', 'purchase.history.write')


def test_demo_upgrade_0024_to_current_preserves_accounts_and_grants(database_settings):
    """Synthetic upgrade rehearsal, on the guarded test DB rather than the demo."""
    engine=create_database_engine(database_settings)
    try:
        command.downgrade(migration_config(),'0024_integrate_import_auth')
        mid=member(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO membership_grants(membership_id,permission) VALUES(:mid,'menu.read')"),{'mid':mid})
            before={table:list(connection.execute(text('SELECT * FROM '+table)))
                    for table in ('users','stores','store_memberships','membership_grants')}
        command.upgrade(migration_config(),'head')
        assert versions(engine)=={HEAD}
        with engine.connect() as connection:
            assert all(list(connection.execute(text('SELECT * FROM '+table)))==rows for table,rows in before.items())
            assert compare_metadata(MigrationContext.configure(connection,opts={'compare_server_default':True}),Base.metadata)==[]
        assert len(inspect(engine).get_table_names())==76
    finally:engine.dispose()


def versions(engine):
    with engine.connect() as connection:
        return set(connection.scalars(text('SELECT version_num FROM alembic_version')))


def member(engine):
    # Schema-only synthetic state; no login or application provisioning claim.
    uid, store, mid = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users(id,email,password_hash,display_name) VALUES(:id,:email,'!UNSET','Schema fixture')"),
                           {'id': uid, 'email': f'{uid}@example.test'})
        connection.execute(text("INSERT INTO stores(id,name) VALUES(:id,'Schema fixture')"), {'id': store})
        connection.execute(text("INSERT INTO store_memberships(id,user_id,store_id,role) VALUES(:id,:uid,:sid,'STAFF')"),
                           {'id': mid, 'uid': uid, 'sid': store})
    return mid


@pytest.mark.parametrize('first,second', [(IMPORT, AUTH), (AUTH, IMPORT)])
def test_upgrade_from_each_branch_head_preserves_v3_grants_and_schema_parity(database_settings, first, second):
    engine = create_database_engine(database_settings)
    try:
        command.downgrade(migration_config(), '0017_planning_exports')
        command.upgrade(migration_config(), first)
        assert versions(engine) == {first}
        mid = member(engine)
        with engine.begin() as connection:
            assert connection.scalar(text('SELECT count(*) FROM membership_grants')) == 0
            for key in KEYS:
                connection.execute(text('INSERT INTO membership_grants(membership_id,permission) VALUES(:mid,:key)'),
                                   {'mid': mid, 'key': key})
        command.upgrade(migration_config(), second)
        assert versions(engine) == {first, second}
        command.upgrade(migration_config(), 'head')
        assert versions(engine) == {HEAD}
        with engine.connect() as connection:
            assert set(connection.scalars(text('SELECT permission FROM membership_grants WHERE membership_id=:mid'), {'mid': mid})) == set(KEYS)
            assert compare_metadata(MigrationContext.configure(connection, opts={'compare_server_default': True}), Base.metadata) == []
        assert len(inspect(engine).get_table_names()) == 76
    finally:
        engine.dispose()


@pytest.mark.parametrize('target,surviving', [('0019_sales_stockout', AUTH), ('0022_invitation_decline', IMPORT)])
@pytest.mark.parametrize('retained', [False, True])
def test_partial_downgrade_keeps_other_branches_v3_and_final_downgrade_guard(database_settings, target, surviving, retained):
    engine = create_database_engine(database_settings)
    try:
        mid = member(engine)
        if retained:
            with engine.begin() as connection:
                for key in KEYS:
                    connection.execute(text('INSERT INTO membership_grants(membership_id,permission) VALUES(:mid,:key)'),
                                       {'mid': mid, 'key': key})
        command.downgrade(migration_config(), target)
        assert versions(engine) == {target, surviving}
        # CHECK must still accept every surviving catalogue key, even with no grants.
        with engine.connect() as connection:
            check = connection.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_membership_grants_catalogue'"))
            assert all(key in check for key in KEYS)
            before = list(connection.execute(text('SELECT membership_id,permission FROM membership_grants ORDER BY permission')))
        if retained:
            with pytest.raises(RuntimeError, match='prevent[s]? downgrade'):
                command.downgrade(migration_config(), '0017_planning_exports')
            assert versions(engine) == {target, surviving}
            with engine.connect() as connection:
                assert list(connection.execute(text('SELECT membership_id,permission FROM membership_grants ORDER BY permission'))) == before
        else:
            command.downgrade(migration_config(), '0017_planning_exports')
            assert versions(engine) == {'0017_planning_exports'}
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text("INSERT INTO membership_grants(membership_id,permission) VALUES(:mid,'calendar.read')"), {'mid': mid})
        command.upgrade(migration_config(), 'head')
        assert versions(engine) == {HEAD}
    finally:
        engine.dispose()
