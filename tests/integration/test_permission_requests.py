"""Public PR decisions, committed grants and durable producer evidence."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from concurrent.futures import ThreadPoolExecutor
from tests.integration.test_staff_public import staff_env, create, accept_http, target_session, owner_session
from tests.integration.test_auth_public import ORIGIN, env
from app.models.auth import MembershipGrant
from app.models.collaboration import PermissionRequestRecord, PermissionRequestAudit
from app.models.staff import PermissionEventRecord
from app.models.notifications import NotificationIntent


def prepare(ctx):
    data, raw=create(ctx)
    assert accept_http(ctx,data,raw).status_code == 201
    owner_session(ctx)
    return ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]


def submit(ctx, member, *, permissions=('sales.read','budget.read'), key=None):
    _, csrf=target_session(ctx)
    return ctx[0][5].post(f'/api/v1/stores/{ctx[2].store_id}/permission-requests',
        headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':key or str(uuid4())},
        json=dict(requested_permissions=permissions,permission_catalog_version='permissions-v3',
                  expected_grants_version=member.version,reason='Explicit synthetic request'))


def approve(ctx, row, *, permissions=('sales.read',), key=None):
    owner_session(ctx)
    return ctx[0][5].post(f'/api/v1/stores/{ctx[2].store_id}/permission-requests/{row["request_id"]}/actions',
        headers={**ctx[5],'Idempotency-Key':key or str(uuid4()),'If-Match':'"'+row['version']+'"'},
        json=dict(action='approve',approved_permissions=permissions,permission_catalog_version='permissions-v3',
                  expected_grants_version=row['current_grants_version'],reason='Approve exact subset'))


def test_union_replay_after_revoke_and_atomic_notifications(staff_env):
    ctx=staff_env; member=prepare(ctx); key=str(uuid4())
    response=submit(ctx,member,key=key)
    assert response.status_code==201,response.text
    row=response.json()['data']
    assert submit(ctx,member,key=key).json()['data']==row
    duplicate=submit(ctx,member)
    assert duplicate.status_code==409
    assert duplicate.json()['error']['details']['existing_request_id']==row['request_id']
    wire=ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/permission-requests').json()
    assert len(wire['data']['permission_catalog'])==43
    decision_key=str(uuid4()); approved=approve(ctx,row,key=decision_key)
    assert approved.status_code==200,approved.text
    result=approved.json()['data']; assert result['request']['actually_added_permissions']==['sales.read']
    with Session(ctx[0][1]) as fresh:
        assert set(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==member.membership_id)))=={'menu.read','sales.read'}
        assert fresh.get(PermissionRequestRecord,UUID(row['request_id'])).state=='approved'
        event=fresh.get(PermissionEventRecord,UUID(result['request']['decision']['permission_event_id'])).record_json
        assert event['source']=='PERMISSION_REQUEST_APPROVAL' and event['permission_request_id']==row['request_id']
        assert fresh.scalar(select(func.count()).select_from(NotificationIntent))==2
    target_session(ctx)
    assert 'sales.read' in ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}').json()['data']['membership']['effective_permissions']
    owner_session(ctx)
    current=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    from app.application.contracts.staff import GrantsRequest
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,GrantsRequest(grants=('menu.read',),reason='Explicit revoke'),str(uuid4()),current.version,ctx[5]['X-CSRF-Token'],'test')
    assert approve(ctx,row,key=decision_key).json()['data']==result
    with Session(ctx[0][1]) as fresh:
        assert set(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==member.membership_id)))=={'menu.read'}


def test_intent_failure_rolls_back_decision_grant_audit_receipt(staff_env,monkeypatch):
    ctx=staff_env; member=prepare(ctx)
    row=submit(ctx,member).json()['data']; key=str(uuid4())
    from app.repositories import notifications
    original=notifications.enqueue
    def fail(s,event):
        original(s,event)
        raise IntegrityError('synthetic',{},Exception('synthetic'))
    monkeypatch.setattr(notifications,'enqueue',fail)
    assert approve(ctx,row,key=key).status_code==503
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(PermissionRequestRecord,UUID(row['request_id'])).state=='pending'
        assert set(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==member.membership_id)))=={'menu.read'}
        assert fresh.scalar(select(func.count()).select_from(PermissionRequestAudit))==1
    monkeypatch.setattr(notifications,'enqueue',original)
    assert approve(ctx,row,key=key).status_code==200


@pytest.mark.parametrize('action',('cancel','reject'))
def test_cancel_reject_no_grants_and_requester_scope(staff_env,action):
    ctx=staff_env; member=prepare(ctx); row=submit(ctx,member).json()['data']
    if action=='reject': owner_session(ctx); headers=ctx[5]
    else:
        _,csrf=target_session(ctx); headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}
    path=f'/api/v1/stores/{ctx[2].store_id}/permission-requests/{row["request_id"]}/actions'
    result=ctx[0][5].post(path,headers={**headers,'Idempotency-Key':str(uuid4()),'If-Match':'"'+row['version']+'"'},json={'action':action,'reason':'Explicit outcome'})
    assert result.status_code==200,result.text
    assert result.json()['data']['request']['state']=={'cancel':'cancelled','reject':'rejected'}[action]
    with Session(ctx[0][1]) as fresh:
        assert set(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==member.membership_id)))=={'menu.read'}
    target_session(ctx)
    assert ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/memberships').status_code==403


def test_catalogue_grants_cas_satisfied_and_noop(staff_env):
    ctx=staff_env; member=prepare(ctx)
    row=submit(ctx,member,permissions=('menu.read','sales.read')).json()['data']
    approved=approve(ctx,row,permissions=('menu.read',))
    assert approved.status_code==200,approved.text
    request=approved.json()['data']['request']
    assert request['actually_added_permissions']==[] and request['decision']['permission_event_id'] is None
    assert request['current_grants_version']==member.version
    row=submit(ctx,member,permissions=('sales.read',)).json()['data']
    assert approve(ctx,{**row,'version':'stale'}).status_code==412
    assert approve(ctx,{**row,'current_grants_version':'stale'}).json()['error']['code']=='GRANTS_VERSION_CONFLICT'
    from app.application.contracts.staff import GrantsRequest
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,GrantsRequest(grants=('menu.read','sales.read'),reason='Fulfill independently'),str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'test')
    current=ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/permission-requests/{row["request_id"]}').json()['data']
    assert current['state']=='satisfied'
    assert approve(ctx,current).json()['error']['code']=='PERMISSION_REQUEST_SATISFIED'
    with Session(ctx[0][1]) as fresh: assert fresh.get(PermissionRequestRecord,UUID(row['request_id'])).state=='satisfied'


def test_concurrent_winner_lost_ack_replay_and_membership_revoke(staff_env,monkeypatch):
    ctx=staff_env; member=prepare(ctx); row=submit(ctx,member).json()['data']; owner_session(ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=sorted(pool.map(lambda _:approve(ctx,row).status_code,range(2)))
    assert codes==[200,412]
    member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    row=submit(ctx,member,permissions=('budget.read',)).json()['data']; key=str(uuid4())
    original=Session.commit
    def uncertain(s):
        original(s)
        raise OperationalError('synthetic lost ACK',{},Exception('synthetic'))
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',uncertain)
        assert approve(ctx,row,permissions=('budget.read',),key=key).status_code==503
    retained=approve(ctx,row,permissions=('budget.read',),key=key)
    assert retained.status_code==200,retained.text
    from app.models import StoreMembership
    with Session(ctx[0][1]) as fresh:
        fresh.get(StoreMembership,member.membership_id).active=False; fresh.commit()
    assert approve(ctx,row,permissions=('budget.read',),key=key).status_code==409


def test_transport_catalogue_and_unknown_permission(staff_env):
    ctx=staff_env; member=prepare(ctx)
    assert submit(ctx,member,permissions=('unknown.permission',)).json()['error']['code']=='UNKNOWN_PERMISSION'
    _,csrf=target_session(ctx); base=f'/api/v1/stores/{ctx[2].store_id}/permission-requests'
    body=dict(requested_permissions=['sales.read'],permission_catalog_version='old',expected_grants_version=member.version,reason='Explicit request')
    headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())}
    assert ctx[0][5].post(base,json=body,headers=headers).json()['error']['code']=='PERMISSION_CATALOG_CHANGED'
    assert ctx[0][5].post(base,json=body,headers={**headers,'Origin':'https://wrong.example.test'}).status_code==403
    assert ctx[0][5].post(base,json=body,headers={k:v for k,v in headers.items() if k!='X-CSRF-Token'}).status_code==403
    assert ctx[0][5].post(base,content='{',headers=headers).status_code==400
    assert ctx[0][5].post(base,content='{"reason":"'+'x'*65536+'"}',headers=headers).status_code==413
