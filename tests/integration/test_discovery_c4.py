"""Read-only discovery uses current authority and scoped PostgreSQL snapshots."""
from uuid import uuid4
import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env, setup, login
from app.models import Supplier
from tests.integration.test_staff_public import staff_env,create,accept_http,target_session,owner_session


def test_supplier_picker_search_snapshot_and_private_fields(env):
    owner = setup(env); login(env)
    foreign=setup(env,'foreign@example.test')
    with Session(env[1]) as s:
        s.add_all([Supplier(id=uuid4(),store_id=owner.store_id,name=name,active=active)
                   for name,active in [('Nhà Cung Cấp Á',True),('Nhà Cung Cấp B',False)]])
        s.add(Supplier(id=uuid4(),store_id=foreign.store_id,name='Nhà Cung Cấp foreign',active=True))
        s.commit()
    path=f'/api/v1/stores/{owner.store_id}/suppliers'
    response=env[5].get(path,params={'q':'nha cung cap','limit':1})
    assert response.status_code==200,response.text
    data=response.json(); item=data['data']['items'][0]
    assert set(item)=={'supplier_id','name','active','version'}
    cursor=data['meta']['pagination']['next_cursor']; assert cursor
    second=env[5].get(path,params={'q':'nha cung cap','limit':1,'cursor':cursor})
    assert second.status_code==200 and second.json()['data']['items'][0]['active'] is False
    assert env[5].get(path,params={'q':'different','limit':1,'cursor':cursor}).status_code==422
    with Session(env[1]) as s:
        s.add(Supplier(id=uuid4(),store_id=owner.store_id,name='Nhà Cung Cấp C',active=True));s.commit()
    assert env[5].get(path,params={'q':'nha cung cap','limit':1,'cursor':cursor}).status_code==409
    assert env[5].get(path,params={'q':'not found'}).json()['data']['items']==[]


def test_supplier_picker_revoke_blocks_old_session_and_receipt(staff_env):
    from tests.integration.test_auth_public import ORIGIN
    from app.application.use_cases.stock_writes import StockWrites
    from app.application.use_cases.public_reads import PublicReads
    ctx=staff_env;env=ctx[0]
    env[5].app.state.stock_writes=StockWrites(env[2],PublicReads(env[2]))
    data,raw=create(ctx,grants=tuple(sorted(('supplier.read','inventory.read','ingredient.read','inventory.receive'))))
    accepted=accept_http(ctx,data,raw);assert accepted.status_code==201
    staff_token,csrf=target_session(ctx)
    root=f'/api/v1/stores/{ctx[2].store_id}'
    assert env[5].get(root+'/suppliers').status_code==200
    owner_session(ctx)
    member=next(row for row in env[5].get(root+'/memberships').json()['data']['items'] if row['user']['user_id']==str(ctx[3].user_id))
    revoked=env[5].put(root+f'/memberships/{member["membership_id"]}/permissions',
        headers={**ctx[5],'Idempotency-Key':str(uuid4()),'If-Match':member['version']},json={'grants':[],'reason':'Explicit C4 test revoke'})
    assert revoked.status_code==200,revoked.text
    env[5].cookies.set('__Host-shelfcash_session',staff_token,domain='backend.example.test',path='/')
    assert env[5].get(root+'/suppliers').status_code==403
    denied=env[5].post(root+'/inventory/receipts',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())},json=dict(
        origin='ACTUAL_RECEIPT',receipt_identity=dict(source_system_key='EXPLICIT',source_record_id='DENIED-1'),
        ingredient_id=str(uuid4()),supplier_id=None,lot_code=None,quantity='1',unit='l',received_date=None,
        expiry_date=None,unit_cost=None,currency='VND',observed_at=env[4][0].isoformat(),reason='Denied fixture',expected_inventory_version='stale-picker'))
    assert denied.status_code==403,denied.text


def test_today_empty_sections_partial_failure_and_snapshot(env,monkeypatch):
    owner=setup(env);login(env);path=f'/api/v1/stores/{owner.store_id}/today'
    response=env[5].get(path);assert response.status_code==200,response.text
    sections=response.json()['data']['sections']
    assert set(sections)=={'inventory','imports','mapping','permissions','readiness','planning'}
    assert all(sections[k]['availability']=='empty' for k in ('inventory','imports','mapping','permissions','planning')), {k:s['availability'] for k,s in sections.items()}
    assert sections['planning']['value'] is None
    assert sections['inventory']['value']['expired_lot_count']==0
    assert sections['inventory']['completeness']=='unknown'
    assert sections['readiness']['availability']=='available',sections['readiness']
    assert any(not action['can_execute'] for action in sections['readiness']['value']['actions'])
    only=env[5].get(path,params={'section':'permissions'}).json()
    assert set(only['data']['sections'])=={'permissions'}
    assert env[5].get(path,params={'section':'permissions','snapshot_id':only['meta']['snapshot_id']}).status_code==200
    assert env[5].get(path,params={'section':'permissions','snapshot_id':'stale'}).status_code==409
    from app.application.use_cases.today import TodayReads
    monkeypatch.setattr(TodayReads,'inventory',lambda *_:(_ for _ in ()).throw(RuntimeError('Synthetic dependency failure')))
    partial=env[5].get(path).json()['data']['sections']
    assert partial['inventory']['availability']=='unavailable' and partial['inventory']['value'] is None
    assert partial['permissions']['availability']=='empty'


@pytest.mark.parametrize('grants',[(),('menu.read','planning.context.read','sales.read')])
def test_today_staff_sections_do_not_leak_forbidden_counts_or_sources(staff_env,grants):
    ctx=staff_env;env=ctx[0];data,raw=create(ctx,grants=grants)
    accepted=accept_http(ctx,data,raw)
    assert accepted.status_code==201
    target_session(ctx)
    path=f'/api/v1/stores/{ctx[2].store_id}/today'
    response=env[5].get(path);assert response.status_code==200,response.text
    sections=response.json()['data']['sections']
    for name in ('inventory','imports','mapping','planning')+(() if grants else ('readiness',)):
        assert sections[name]==dict(availability='forbidden',value=None,updated_at=None,
            completeness='unknown',reason_codes=['PERMISSION_DENIED'],source=None)
    assert sections['permissions']['value']['total_count']==0
    if grants:
        readiness=sections['readiness']['value']
        assert readiness is not None
        assert {a['action'] for a in readiness['actions']}=={'menu','forecast'}
        assert readiness['scope_estimate'] is readiness['history_watermark'] is None
        assert all(readiness['source_versions'][k] is None for k in ('suppliers','fees','planning_config','declarations'))
    assert env[5].get(f'/api/v1/stores/{uuid4()}/today').status_code==404
    assert env[5].get(path,params={'section':'unsupported'}).status_code==422


def count_read_queries(engine,request):
    statements=[]
    def before(_connection,_cursor,statement,_params,_context,_many):
        statements.append(statement.lstrip().split(None,1)[0].upper())
    event.listen(engine,'before_cursor_execute',before)
    try:response=request()
    finally:event.remove(engine,'before_cursor_execute',before)
    assert response.status_code==200,response.text
    assert not {'INSERT','UPDATE','DELETE'}&set(statements)
    return len(statements),response


def test_supplier_and_today_queries_do_not_grow_with_items(env):
    from tests.integration.test_auth_public import ORIGIN
    from app.application.use_cases.import_staging import ImportStaging
    owner=setup(env);signed=login(env).json()['data'];env[5].app.state.import_staging=ImportStaging(env[2],env[0])
    headers={'Origin':ORIGIN,'X-CSRF-Token':signed['session']['csrf_token']}
    root=f'/api/v1/stores/{owner.store_id}'
    for _ in range(15):
        response=env[5].post(root+'/imports',headers={**headers,'Idempotency-Key':str(uuid4())},json={'data_date':'2026-10-10'})
        assert response.status_code==201
    one,r1=count_read_queries(env[1],lambda:env[5].get(root+'/today',params={'section':'imports','limit':1}))
    many,r2=count_read_queries(env[1],lambda:env[5].get(root+'/today',params={'section':'imports','limit':20}))
    assert one==many
    today_query_count=one
    assert r1.json()['data']['sections']['imports']['value']['total_count']==15
    assert len(r2.json()['data']['sections']['imports']['value']['items'])==15
    with Session(env[1]) as s:
        s.add_all(Supplier(id=uuid4(),store_id=owner.store_id,name=f'Explicit supplier {i}',active=True) for i in range(15));s.commit()
    one,_=count_read_queries(env[1],lambda:env[5].get(root+'/suppliers',params={'limit':1}))
    many,_=count_read_queries(env[1],lambda:env[5].get(root+'/suppliers',params={'limit':100}))
    assert one==many
    print(f'Query evidence: Today imports={today_query_count}; supplier picker={many}; query counts constant across page sizes.')
