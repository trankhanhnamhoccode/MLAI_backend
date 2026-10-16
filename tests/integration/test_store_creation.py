"""Customer onboarding uses public signup, fake delivery and real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_email_verification import env, signup, delivered_token, complete, post, EMAIL, PASSWORD, ORIGIN
from app.models import Store, StoreMembership, Product, Ingredient
from app.models.auth import AuthAudit, MembershipGrant


def holder(env):
    signup(env)
    assert complete(env,delivered_token(env)).status_code==200
    login=post(env,'login',dict(email=EMAIL,password=PASSWORD))
    assert login.status_code==200
    assert login.json()['data']['accessible_store_count']==0
    return login.json()['data']['session']['csrf_token']


def create(env,csrf,key=None,body=None,headers=None):
    return env[6].post('/api/v1/stores',json=body or dict(name='Explicit synthetic shop',timezone='Asia/Ho_Chi_Minh',currency='VND'),
        headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':key or str(uuid4()),**(headers or {})})


def test_self_service_owner_fresh_login_replay_and_no_business_seed(env):
    csrf=holder(env);key=str(uuid4());response=create(env,csrf,key)
    assert response.status_code==201,response.text
    row=response.json()['data'];sid=UUID(row['store_id'])
    assert row['role']=='OWNER' and response.headers['location']=='/api/v1/stores/'+str(sid)
    assert create(env,csrf,key).json()['data']==row
    changed=dict(name='Different request',timezone='Asia/Ho_Chi_Minh',currency='VND')
    assert create(env,csrf,key,changed).status_code==409
    assert env[6].get(response.headers['location']).json()['data']['membership']['role']=='OWNER'
    with Session(env[0]) as fresh:
        assert fresh.get(Store,sid).name==row['name']
        member=fresh.scalar(select(StoreMembership).where(StoreMembership.store_id==sid))
        assert member.role=='OWNER' and member.active
        assert fresh.scalar(select(func.count()).select_from(MembershipGrant))==0
        for model in (Product,Ingredient):assert fresh.scalar(select(func.count()).select_from(model))==0
        assert fresh.scalar(select(func.count()).select_from(AuthAudit).where(AuthAudit.kind=='STORE_CREATED'))==1
    assert env[6].post('/api/v1/auth/logout',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==204
    login=post(env,'login',dict(email=EMAIL,password=PASSWORD))
    assert login.json()['data']['default_store_id']==str(sid)
    csrf=login.json()['data']['session']['csrf_token']
    assert create(env,csrf,key).json()['data']==row
    assert create(env,csrf).status_code==201  # Explicit second Store, not name-based dedupe.
    assert env[6].get('/api/v1/auth/me').json()['data']['default_store_id'] is None


def test_store_creation_auth_origin_csrf_validation_and_isolation(env):
    assert create(env,'absent').status_code==401
    csrf=holder(env)
    assert create(env,csrf,headers={'Origin':'https://wrong.example'}).status_code==403
    assert create(env,'wrong').status_code==403
    assert create(env,csrf,headers={'Idempotency-Key':''}).status_code==428
    for change in ({'owner_user_id':str(uuid4())},{'role':'OWNER'},{'grants':[]},{'timezone':'Not/A_Zone'},{'name':'   '},{'name':'bad\x00name'},{'currency':'vnd'}):
        body=dict(name='Explicit shop',timezone='UTC',currency='VND');body.update(change)
        assert create(env,csrf,body=body).status_code==422
    first=create(env,csrf);assert first.status_code==201
    foreign=first.headers['location']
    env[1][0]+=__import__('datetime').timedelta(seconds=61)
    signup(env,'other@example.test')
    assert complete(env,delivered_token(env)).status_code==200
    assert post(env,'login',dict(email='other@example.test',password=PASSWORD)).status_code==200
    assert env[6].get(foreign).status_code==404
    assert env[6].get('/api/v1/stores').json()['data']['items']==[]


def test_concurrent_same_key_and_atomic_rollback(env,monkeypatch):
    csrf=holder(env);key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:create(env,csrf,key),range(2)))
    assert all(r.status_code==201 for r in replies),[r.status_code for r in replies]
    assert replies[0].json()['data']==replies[1].json()['data']
    from app.application.use_cases.store_creation import StoreCreation
    from sqlalchemy.exc import OperationalError
    from app.models.store_creation import StoreCreationReceipt
    original=StoreCreation._record
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise OperationalError('synthetic',{},Exception('synthetic'))
    with monkeypatch.context() as patch:
        patch.setattr(StoreCreation,'_record',fail)
        assert create(env,csrf).status_code==503
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store))==1
        assert fresh.scalar(select(func.count()).select_from(StoreMembership))==1
        assert fresh.scalar(select(func.count()).select_from(StoreCreationReceipt))==1


def test_lost_ack_reconciles_same_receipt_and_revoke_blocks_replay(env,monkeypatch):
    from sqlalchemy.exc import OperationalError
    csrf=holder(env);key=str(uuid4());real=Session.commit;raised=[False]
    def lost_ack(session):
        from app.models.store_creation import StoreCreationReceipt
        creating=any(isinstance(row,StoreCreationReceipt) for row in session.new)
        real(session)
        if creating and not raised[0]:
            raised[0]=True
            raise OperationalError('synthetic lost ACK',{},Exception('synthetic'))
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',lost_ack)
        assert create(env,csrf,key).status_code==503
    retry=create(env,csrf,key);assert retry.status_code==201,retry.text
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store))==1
        member=fresh.scalar(select(StoreMembership));member.active=False;fresh.commit()
    assert create(env,csrf,key).status_code==404


def test_reload_empty_discovery_does_not_fence_late_store_creation(env):
    """Reload readback is current state, never a terminal negative receipt."""
    from app.models.store_creation import StoreCreationReceipt
    from app.infrastructure.auth_crypto import digest

    csrf = holder(env)
    key = str(uuid4())
    # Simulate an old dispatch reaching BE only after reload discovery.
    assert env[6].get('/api/v1/stores').json()['data']['items'] == []
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(StoreCreationReceipt).where(
            StoreCreationReceipt.key_digest == digest(key)
        )) is None
    late = create(env, csrf, key)
    assert late.status_code == 201, late.text
    sid = late.json()['data']['store_id']
    # Client has discarded the original response/key/body: discovery can locate
    # the Store, but cannot identify the original logical intent from its name.
    discovered = env[6].get('/api/v1/stores').json()['data']['items']
    assert [item['store_id'] for item in discovered] == [sid]
    assert env[6].get(f'/api/v1/stores/{sid}').status_code == 200
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Store)) == 1
        assert fresh.scalar(select(func.count()).select_from(StoreCreationReceipt)) == 1


def test_receipt_retention_schema_parity_and_no_destructive_downgrade(env):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.models.store_creation import StoreCreationReceipt
    from app.infrastructure.database.base import Base
    from scripts.dev import migration_config
    csrf=holder(env);assert create(env,csrf).status_code==201
    with env[0].connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection,opts={'compare_server_default':True}),Base.metadata)==[]
    with Session(env[0]) as fresh:
        row=fresh.scalar(select(StoreCreationReceipt));row.result={'changed':True}
        with pytest.raises(DBAPIError):fresh.commit()
    with pytest.raises(DBAPIError,match='prevent downgrade'):
        command.downgrade(migration_config(),'0026_collaboration_requests')
    with Session(env[0]) as fresh:
        assert fresh.scalar(text('SELECT version_num FROM alembic_version'))=='0027_self_service_stores'
        assert fresh.scalar(select(func.count()).select_from(Store))==1


def test_self_created_store_imports_explicit_customer_files_without_provisioning(env):
    from pathlib import Path
    from types import SimpleNamespace
    from app.application.use_cases.import_staging import ImportStaging
    from app.application.use_cases.public_reads import PublicReads
    from tests.integration.test_import_commit import analyzed_files
    from tests.integration.test_import_setup_stock import review_batch,complete as commit_import
    csrf=holder(env);created=create(env,csrf).json()['data'];sid=UUID(created['store_id'])
    engine,clock,auth,_,_,_,client,settings=env
    service=ImportStaging(auth,settings);client.app.state.import_staging=service
    client.app.state.public_reads=PublicReads(auth)
    context=((settings,engine,auth,None,clock,client),SimpleNamespace(store_id=sid),service,
             {'Origin':ORIGIN,'X-CSRF-Token':csrf},None)
    folder=Path(__file__).parents[1]/'fixtures/local_self_service'
    ident=analyzed_files(context,[(name,(folder/name).read_bytes()) for name in ('products.csv','ingredients.csv')])
    creations={'DEMO_COFFEE':('product',dict(name='Explicit synthetic coffee',selling_unit='cup',sku='DEMO_COFFEE',price=None,active=True)),
               'DEMO_MILK':('ingredient',dict(name='Explicit synthetic milk',base_unit='l',sku='DEMO_MILK',expiry_tracking=False,active=True))}
    review_batch(context,ident,creations=creations,source_context=dict(source_system_key='LOCAL_EXPLICIT_FIXTURE',report_type='master-data'))
    _,done=commit_import(context,ident);assert done['outcome']=='committed'
    with Session(engine) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product).where(Product.store_id==sid))==1
        assert fresh.scalar(select(func.count()).select_from(Ingredient).where(Ingredient.store_id==sid))==1
    assert client.get(f'/api/v1/stores/{sid}/products').status_code==200


def test_self_created_owner_invites_self_registered_staff_with_fake_background_delivery(env):
    from app.application.use_cases.staff import StaffUseCases
    from app.application.use_cases.invitation_delivery import InvitationDispatcher
    csrf=holder(env);created=create(env,csrf).json()['data'];sid=created['store_id']
    env[6].app.state.staff=StaffUseCases(env[2],env[7])
    signup(env,'staff-local@example.test')
    assert complete(env,delivered_token(env)).status_code==200
    result=env[6].post(f'/api/v1/stores/{sid}/staff-invitations',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())},
        json=dict(email='staff-local@example.test',grants=['menu.read'],permission_catalog_version='permissions-v3',reason='Explicit customer invitation'))
    assert result.status_code==201,result.text
    invitation=result.json()['data']['invitation'];messages=[]
    class Delivery:
        available=True
        def __call__(self,address,identifier,token):
            assert env[0].pool.checkedout()==0
            messages.append((identifier,token.get_secret_value()))
    dispatcher=InvitationDispatcher(env[0],env[7].model_copy(update={'auth_email_delivery_enabled':True}),env[2].clock)
    assert dispatcher.dispatch_background(Delivery())['delivered']==1
    assert dispatcher.dispatch_background(Delivery())['delivered']==0
    assert str(messages[0][0])==invitation['invitation_id']
    login=post(env,'login',dict(email='staff-local@example.test',password=PASSWORD))
    assert login.json()['data']['accessible_store_count']==0
    csrf=login.json()['data']['session']['csrf_token']
    result=env[6].post(f'/api/v1/staff-invitations/{invitation["invitation_id"]}/accept',
        headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4()),'If-Match':invitation['version']},
        json=dict(token=messages[0][1],accept=True))
    assert result.status_code==201,result.text
    assert env[6].get(f'/api/v1/stores/{sid}').json()['data']['membership']['effective_permissions']==['menu.read']
    with Session(env[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership))==2
        assert list(fresh.scalars(select(MembershipGrant.permission)))==['menu.read']
    own=create(env,csrf);assert own.status_code==201 and own.json()['data']['role']=='OWNER'
    original=env[6].get(f'/api/v1/stores/{sid}').json()['data']['membership']
    assert original['role']=='STAFF' and original['effective_permissions']==['menu.read']
