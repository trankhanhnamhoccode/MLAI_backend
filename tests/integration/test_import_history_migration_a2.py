"""A2 additive evolution keeps Staff grants; downgrade refuses evidence loss."""
from hashlib import sha256
from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup
from app.models import StoreMembership, ImportHistoryRecord
from app.models.auth import MembershipGrant
from scripts.dev import migration_config


@pytest.mark.parametrize('retained',['history','grant'])
def test_additive_history_and_catalogue_migration_no_auto_grants_and_retention_guard(env,retained):
    receipt=setup(env)
    with Session(env[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==receipt.store_id));member.role='STAFF'
        ident=member.id;s.add(MembershipGrant(membership_id=ident,permission='menu.read'));s.commit()
    command.downgrade(migration_config(),'0019_sales_stockout')
    command.upgrade(migration_config(),'0021_import_support_history')
    with Session(env[1]) as fresh:
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==ident)))==('menu.read',)
        assert fresh.scalar(select(text('count(*)')).select_from(ImportHistoryRecord))==0
    with Session(env[1]) as s:
        if retained=='grant':s.add(MembershipGrant(membership_id=ident,permission='usage.history.write'))
        else:
            s.add(ImportHistoryRecord(id=uuid4(),store_id=receipt.store_id,domain='calendar_events',source_system_key='test',
                report_type='events',source_record_key='event-1',source_record_hash=sha256(b'event-1').hexdigest(),
                version=1,payload={'event':'Synthetic immutable'},provenance={},recorded_at=env[4][0]))
        s.commit()
    with pytest.raises(RuntimeError,match='prevent[s]? downgrade'):
        command.downgrade(migration_config(),'0019_sales_stockout')
    with Session(env[1]) as fresh:
        assert fresh.scalar(text('SELECT version_num FROM alembic_version'))=='0021_import_support_history'
    if retained=='history':
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            with Session(env[1]) as s,s.begin():
                s.execute(text("UPDATE import_history_records SET payload='{}'::jsonb"))
