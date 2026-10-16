"""N12--N19 real HTTP/PostgreSQL; synthetic identities and guarded test DB."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4
import pytest
from pydantic import SecretStr
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from tests.integration.test_auth_public import env, setup, login, ORIGIN, KEY, PASSWORD
from app.application.use_cases.staff import StaffUseCases
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.application.contracts.staff import AcceptInvitation, RevokeInvitation, ReissueInvitation, GrantsRequest
from app.application.contracts.auth import AuthError, LoginRequest
from app.infrastructure.invitation_secret import InvitationSecret
from app.application.use_cases.staff import delivery_identity
from app.models import StoreMembership, Store, User
from app.models.auth import MembershipGrant, AuthAccount
from app.models.staff import StaffInvitation, PermissionEventRecord, InvitationEventRecord, StaffRequestReceipt, InvitationDeliveryIntent


@pytest.fixture
def staff_env(env):
    settings = env[0].model_copy(update={"auth_delivery_encryption_key":SecretStr(base64.b64encode(bytes(range(32))).decode())})
    staff = StaffUseCases(env[2], settings)
    env[5].app.state.staff = staff
    owner, target = setup(env), setup(env,"staff@example.test",store=False)
    owner_login = login(env).json()["data"]
    owner_token = env[5].cookies.get("__Host-shelfcash_session")
    headers = {"Origin":ORIGIN,"X-CSRF-Token":owner_login["session"]["csrf_token"]}
    return env, staff, owner, target, owner_token, headers


def create(ctx, *, email="staff@example.test", grants=("menu.read",), key=None):
    env, _, owner, _, _, headers = ctx
    response = env[5].post(f"/api/v1/stores/{owner.store_id}/staff-invitations",
        headers={**headers,"Idempotency-Key":key or str(uuid4())},json=dict(email=email,grants=list(grants),permission_catalog_version="permissions-v3",reason="Synthetic invitation"))
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    with Session(env[1]) as fresh:
        row = fresh.get(StaffInvitation, UUID(data["invitation"]["invitation_id"]))
        intent = fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"]))
        raw = InvitationSecret(ctx[1].settings.auth_delivery_encryption_key).open(intent.ciphertext,delivery_identity(row,intent.id)).get_secret_value()
    return data, raw


def target_session(ctx):
    result, token = ctx[0][2].login(LoginRequest(email="staff@example.test",password=PASSWORD),"staff-client")
    ctx[0][5].cookies.set("__Host-shelfcash_session",token,domain="backend.example.test",path="/")
    return token, result.session.csrf_token


def owner_session(ctx, *, fresh=False):
    token=ctx[4]
    if fresh:
        result,token=ctx[0][2].login(LoginRequest(email="owner@example.test",password=PASSWORD),"owner-client")
        ctx[5]["X-CSRF-Token"]=result.session.csrf_token
    ctx[0][5].cookies.set("__Host-shelfcash_session",token,domain="backend.example.test",path="/")


def accept_http(ctx, data, raw, *, key=None, match=None):
    _, csrf = target_session(ctx)
    return ctx[0][5].post(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}/accept",
        headers={"Origin":ORIGIN,"X-CSRF-Token":csrf,"Idempotency-Key":key or str(uuid4()),
                 "If-Match":match or data["invitation"]["version"]},json={"token":raw,"accept":True})


def test_create_accept_atomic_exact_grants_audits_and_readonly_receipt(staff_env):
    ctx=staff_env
    data, raw=create(ctx,grants=("budget.read","menu.read"))
    env, staff, owner, target, owner_token, headers=ctx
    assert raw not in str(data) and "account_exists" not in str(data)
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(StoreMembership.user_id==target.user_id))==0
        intent=fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"]))
        assert raw.encode() not in intent.ciphertext
    target_session(ctx)
    offer=env[5].get(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}",headers={"X-Invitation-Token":raw})
    assert offer.status_code==200 and offer.json()["data"]["can_accept"]
    assert offer.headers["etag"]=='"'+data["invitation"]["version"]+'"'
    assert "delivery" not in offer.text and "issuer_user_id" not in offer.text
    key=str(uuid4())
    response=accept_http(ctx,data,raw,key=key)
    assert response.status_code==201, response.text
    receipt=response.json()["data"]
    with Session(env[1]) as fresh:
        member=fresh.get(StoreMembership,UUID(receipt["membership_id"]))
        assert member.role=="STAFF" and member.user_id==target.user_id and member.store_id==owner.store_id
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==member.id).order_by(MembershipGrant.permission)))==("budget.read","menu.read")
        row=fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"]))
        assert row.status=="accepted" and row.version!=data["invitation"]["version"]
        event=fresh.get(PermissionEventRecord,UUID(receipt["event_id"])).record_json
        assert event["actor_user_id"]==str(target.user_id) and event["issuer_user_id"]==str(owner.user_id)
        assert event["source"]=="INVITATION_ACCEPTANCE" and event["before_grants"]==[]
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==2
    repeat=accept_http(ctx,data,raw,key=key)
    assert repeat.status_code==200 and repeat.json()["data"]==receipt
    assert accept_http(ctx,data,raw).json()["error"]["code"]=="INVITATION_ALREADY_ACCEPTED"
    owner_session(ctx)
    current=staff.memberships(owner_token,owner.store_id)[0].items[0]
    staff.replace(owner_token,owner.store_id,current.membership_id,GrantsRequest(grants=(),reason="Remove"),str(uuid4()),current.version,headers["X-CSRF-Token"],"revoke-grants")
    repeat=accept_http(ctx,data,raw,key=key)
    assert repeat.status_code==200 and repeat.json()["data"]["accepted_grants"]==["budget.read","menu.read"]
    assert env[5].get(f"/api/v1/stores/{owner.store_id}").json()["data"]["membership"]["effective_permissions"]==[]
    with Session(env[1]) as s:
        s.get(StoreMembership,current.membership_id).active=False
        s.commit()
    assert accept_http(ctx,data,raw,key=key).status_code==403


def test_grants_http_cas_replace_empty_noop_retry_current_authority(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    assert accept_http(ctx,data,raw).status_code==201
    env,staff,owner,_,token,headers=ctx
    owner_session(ctx)
    url=f"/api/v1/stores/{owner.store_id}/memberships"
    listing=env[5].get(url).json()["data"]
    assert listing["permission_catalog_version"]=="permissions-v3" and len(listing["permission_catalog"])==43
    item=listing["items"][0]
    path=url+f"/{item['membership_id']}/permissions"
    request_headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":item["version"]}
    body={"grants":["inventory.read","menu.read"],"reason":"New shift"}
    response=env[5].put(path,headers=request_headers,json=body)
    assert response.status_code==200 and response.json()["data"]["changed"]
    result=response.json()["data"]
    assert response.headers["etag"]=='"'+result["membership"]["version"]+'"'
    assert env[5].put(path,headers=request_headers,json=body).json()["data"]==result
    assert env[5].put(path,headers={**request_headers,"Idempotency-Key":str(uuid4())},json=body).status_code==412
    assert env[5].put(path,headers=request_headers,json={**body,"reason":"Other"}).status_code==409
    request_headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":result["membership"]["version"]}
    noop=env[5].put(path,headers=request_headers,json=body).json()["data"]
    assert not noop["changed"] and noop["event_id"] is None and noop["membership"]["version"]==result["membership"]["version"]
    empty=env[5].put(path,headers={**request_headers,"Idempotency-Key":str(uuid4())},json={"grants":[],"reason":"Withdraw"})
    assert empty.status_code==200 and empty.json()["data"]["membership"]["grants"]==[]
    with Session(env[1]) as fresh:
        mid=UUID(item["membership_id"])
        assert not tuple(fresh.scalars(select(MembershipGrant).where(MembershipGrant.membership_id==mid)))
        assert fresh.get(StoreMembership,mid).authorization_revision>1
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord).where(PermissionEventRecord.membership_id==mid))==3
    audit=env[5].get(f"/api/v1/stores/{owner.store_id}/permission-events").json()["data"]["items"]
    assert {e["source"] for e in audit}=={"ASSISTED_PROVISIONING","INVITATION_ACCEPTANCE","OWNER_CHANGE"}
    with Session(env[1]) as s:
        own=s.scalar(select(StoreMembership).where(StoreMembership.user_id==owner.user_id))
        own.active=False
        s.commit()
    assert env[5].put(path,headers=request_headers,json=body).status_code==404


def test_grants_lost_ack_replay_preserves_later_change_and_current_authority(staff_env, monkeypatch):
    from sqlalchemy.exc import OperationalError
    ctx = staff_env
    data, raw = create(ctx)
    assert accept_http(ctx, data, raw).status_code == 201
    owner_session(ctx)
    env, _, owner, _, _, headers = ctx
    listing = f'/api/v1/stores/{owner.store_id}/memberships'
    member = env[5].get(listing).json()['data']['items'][0]
    mid = UUID(member['membership_id'])
    path = listing + f'/{mid}/permissions'
    key = str(uuid4())
    request_headers = {**headers, 'Idempotency-Key': key, 'If-Match': member['version']}
    body = dict(grants=['inventory.read', 'menu.read'], reason='Synthetic lost acknowledgment')
    original = Session.commit
    injected = []

    def lost_ack(session):
        changing = any(isinstance(row, StaffRequestReceipt) and row.operation.endswith('/permissions')
                       for row in session.new)
        original(session)
        if changing and not injected:
            injected.append(True)
            raise OperationalError('synthetic lost ACK', {}, Exception('synthetic'))

    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lost_ack)
        assert env[5].put(path, headers=request_headers, json=body).status_code == 503
    assert injected
    with Session(env[1]) as fresh:
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(
            MembershipGrant.membership_id == mid).order_by(MembershipGrant.permission))) == ('inventory.read', 'menu.read')
        event_count = fresh.scalar(select(func.count()).select_from(PermissionEventRecord))
    current = env[5].get(listing).json()['data']['items'][0]
    later = env[5].put(path, headers={**headers, 'Idempotency-Key': str(uuid4()), 'If-Match': current['version']},
                      json=dict(grants=[], reason='Later explicit removal'))
    assert later.status_code == 200, later.text
    with ThreadPoolExecutor(2) as pool:
        replays = list(pool.map(lambda _: env[5].put(path, headers=request_headers, json=body), range(2)))
    assert all(r.status_code == 200 for r in replays)
    assert replays[0].json()['data'] == replays[1].json()['data']
    assert replays[0].json()['data']['membership']['grants'] == body['grants']
    assert env[5].get(listing).json()['data']['items'][0]['grants'] == []
    conflict = env[5].put(path, headers=request_headers, json={**body, 'reason': 'Changed intent'})
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'IDEMPOTENCY_KEY_REUSED'
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(MembershipGrant).where(MembershipGrant.membership_id == mid)) == 0
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord)) == event_count + 1
        own = fresh.scalar(select(StoreMembership).where(StoreMembership.user_id == owner.user_id))
        own.active = False
        fresh.commit()
    assert env[5].put(path, headers=request_headers, json=body).status_code == 404


@pytest.mark.parametrize("change,code", [({"role":"OWNER"},"VALIDATION_ERROR"),({"grants":["unknown"]},"UNKNOWN_PERMISSION"),({"grants":["menu.read","menu.read"]},"VALIDATION_ERROR"),({"grants":["menu.read","inventory.read"]},"VALIDATION_ERROR"),({"permission_catalog_version":"old"},"PERMISSION_CATALOG_CHANGED")])
def test_create_rejects_invalid_fields(staff_env,change,code):
    env,_,owner,_,_,headers=staff_env
    response=env[5].post(f"/api/v1/stores/{owner.store_id}/staff-invitations",headers={**headers,"Idempotency-Key":str(uuid4())},
        json=dict(email="other@example.test",grants=["menu.read"],permission_catalog_version="permissions-v3",reason="test")|change)
    assert response.json()["error"]["code"]==code
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StaffInvitation))==0


def test_owner_only_cross_store_filters_and_headers(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,_,_,headers=ctx
    foreign=setup(env,"foreign@example.test")
    base=f"/api/v1/stores/{owner.store_id}"
    assert env[5].get(base+"/memberships?role=OWNER").status_code==422
    assert env[5].get(base+"/staff-invitations?view=events&status=pending").status_code==422
    assert env[5].get(base+"/staff-invitations?unknown=x").status_code==422
    assert env[5].post(base+"/staff-invitations",json={}).status_code==403
    assert env[5].post(base+"/staff-invitations",headers={"Origin":ORIGIN},json=dict(email="x@example.test",grants=[],permission_catalog_version="permissions-v3",reason="x")).status_code==422
    login(env,"foreign@example.test")
    assert env[5].get(base+"/memberships").status_code==404
    assert env[5].get(base+"/staff-invitations").status_code==404
    assert accept_http(ctx,data,raw).status_code==201
    for suffix in ("/memberships","/permission-events","/staff-invitations"):
        assert env[5].get(base+suffix).status_code==403
    # HTTP login to the foreign account revoked the previous browser session.
    # Restore a valid Owner session to test cross-Store 404, not stale-session 401.
    from app.models.auth import AuthSession
    from app.infrastructure.auth_crypto import digest
    with Session(env[1]) as fresh:
        assert fresh.get(AuthSession,digest(ctx[4])).revoked_at is not None
    owner_session(ctx,fresh=True)
    own=env[5].get(f"/api/v1/stores/{foreign.store_id}/memberships")
    assert own.status_code==404
    target_url=base+f"/staff-invitations/{uuid4()}/actions"
    r=env[5].post(target_url,headers={**headers,"Idempotency-Key":str(uuid4())},json={"action":"revoke","reason":"test"})
    assert r.status_code==428
    r=env[5].post(base+f"/staff-invitations/{data['invitation']['invitation_id']}/actions",headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":data["invitation"]["version"],"X-CSRF-Token":"wrong"},json={"action":"revoke","reason":"test"})
    assert r.status_code==403


def test_reissue_revoke_expiry_and_existing_membership(staff_env):
    ctx=staff_env
    data,old=create(ctx)
    env,staff,owner,target,token,headers=ctx
    assert env[5].post(f"/api/v1/stores/{owner.store_id}/staff-invitations",headers={**headers,"Idempotency-Key":str(uuid4())},json=dict(email="staff@example.test",grants=[],permission_catalog_version="permissions-v3",reason="duplicate")).json()["error"]["code"]=="INVITATION_ALREADY_PENDING"
    path=f"/api/v1/stores/{owner.store_id}/staff-invitations/{data['invitation']['invitation_id']}/actions"
    action=env[5].post(path,headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":data["invitation"]["version"]},json=dict(action="reissue",grants=[],permission_catalog_version="permissions-v3",reason="new offer"))
    assert action.status_code==200,action.text
    new=action.json()["data"]
    with Session(env[1]) as fresh:
        row=fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"]))
        intent=fresh.get(InvitationDeliveryIntent,UUID(new["delivery"]["attempt_id"]))
        raw=InvitationSecret(staff.settings.auth_delivery_encryption_key).open(intent.ciphertext,delivery_identity(row,intent.id)).get_secret_value()
        assert fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"])).ciphertext is None
    target_session(ctx)
    assert env[5].get(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}",headers={"X-Invitation-Token":old}).status_code==404
    assert accept_http(ctx,new,raw,match=data["invitation"]["version"]).status_code==412
    owner_session(ctx)
    revoke=env[5].post(path,headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":new["invitation"]["version"]},json=dict(action="revoke",reason="cancel"))
    assert revoke.status_code==200 and revoke.json()["data"]["invitation"]["status"]=="revoked"
    revoked=revoke.json()["data"]
    noop=env[5].post(path,headers={**headers,"Idempotency-Key":str(uuid4()),"If-Match":revoked["invitation"]["version"]},json=dict(action="revoke",reason="cancel again"))
    assert noop.status_code==200 and noop.json()["data"]["event_id"] is None
    assert accept_http(ctx,revoked,raw).status_code==410
    target_session(ctx)
    offer=env[5].get(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}",headers={"X-Invitation-Token":raw})
    assert offer.status_code==200 and not offer.json()["data"]["can_accept"]
    owner_session(ctx)
    other,raw2=create(ctx,email="new@example.test")
    env[4][0]+=timedelta(days=7)
    owner_session(ctx,fresh=True)
    listing=env[5].get(f"/api/v1/stores/{owner.store_id}/staff-invitations?status=expired").json()["data"]
    assert len(listing["items"])==1
    with Session(env[1]) as fresh:
        assert fresh.get(StaffInvitation,UUID(other["invitation"]["invitation_id"])).status=="pending"


@pytest.mark.parametrize("case,expected", [("wrong_email",403),("unknown_proof",403),("bad_token",404),("issuer_revoked",409),("existing",409),("inactive_existing",409),("expired",410)])
def test_recipient_guards_no_ghost_membership(staff_env,case,expected):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,target,_,_=ctx
    target_token,csrf=target_session(ctx)
    with Session(env[1]) as s:
        if case=="unknown_proof":s.get(AuthAccount,target.user_id).verification_reference=""
        if case=="issuer_revoked":
            s.scalar(select(StoreMembership).where(StoreMembership.user_id==owner.user_id)).active=False
        if case in {"existing","inactive_existing"}:
            s.add(StoreMembership(id=uuid4(),store_id=owner.store_id,user_id=target.user_id,role="STAFF",active=case=="existing"))
        s.commit()
    if case=="wrong_email":
        target_token=ctx[4]
        csrf=ctx[5]["X-CSRF-Token"]
    if case=="bad_token":raw="credential-token-not-invitation"
    if case=="expired":
        env[4][0]+=timedelta(days=7)
        target_token,csrf=target_session(ctx)
    with pytest.raises(AuthError) as caught:
        staff.accept(target_token,UUID(data["invitation"]["invitation_id"]),AcceptInvitation(token=raw,accept=True),str(uuid4()),data["invitation"]["version"],csrf,"test","guard")
    assert caught.value.status==expected
    with Session(env[1]) as fresh:
        assert fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"])).status=="pending"
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==1


def test_delivery_failure_success_detached_and_immutable_history(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,_,_,_=ctx
    dispatcher=InvitationDispatcher(env[1],staff.settings,staff.clock)
    def broken(address,identifier,secret):
        assert env[1].pool.checkedout()==0
        assert secret.get_secret_value()==raw
        raise OSError("synthetic provider unavailable")
    counts=dispatcher.dispatch("support-test",KEY,broken)
    assert counts==dict(delivered=0,failed=1,cancelled=0)
    with Session(env[1]) as fresh:
        row=fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"]))
        assert row.status=="pending" and row.delivery_status=="failed"
        assert fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"])).ciphertext is None
        assert fresh.scalar(select(func.count()).select_from(InvitationEventRecord))==2
    assert dispatcher.dispatch("support-test",KEY,broken)==dict(delivered=0,failed=0,cancelled=0)
    create(ctx,email="other@example.test")
    def delivered(*args):assert env[1].pool.checkedout()==0
    assert dispatcher.dispatch("support-test",KEY,delivered)["delivered"]==1
    with Session(env[1]) as s:
        event=s.scalar(select(InvitationEventRecord))
        event.record_json={"tampered":True}
        with pytest.raises(IntegrityError):s.commit()


def test_owner_invitation_paging_tamper_snapshot_and_audit(staff_env):
    ctx=staff_env
    data,_=create(ctx)
    create(ctx,email="other@example.test")
    client=ctx[0][5]
    base=f"/api/v1/stores/{ctx[2].store_id}/staff-invitations"
    first=client.get(base+"?limit=1").json()
    cursor=first["meta"]["pagination"]["next_cursor"]
    assert first["meta"]["pagination"]["total_count"]==2
    second=client.get(base,params=dict(limit=1,cursor=cursor))
    assert second.status_code==200 and second.json()["data"]["items"]!=first["data"]["items"]
    assert client.get(base,params=dict(limit=1,cursor=cursor+"x")).status_code==422
    assert client.get(base,params=dict(limit=1,cursor=cursor,status="pending")).status_code==422
    create(ctx,email="third@example.test")
    assert client.get(base,params=dict(limit=1,cursor=cursor)).json()["error"]["code"]=="LIST_VERSION_CHANGED"
    events=client.get(base,params=dict(view="events",invitation_id=data["invitation"]["invitation_id"]))
    assert events.status_code==200 and events.json()["data"]["items"][0]["kind"]=="CREATED"


@pytest.mark.parametrize("op", ["accept","revoke","reissue"])
def test_concurrent_accept_transition_single_membership(staff_env,op):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,target,owner_token,headers=ctx
    target_token,csrf=target_session(ctx)
    identifier=UUID(data["invitation"]["invitation_id"])
    barrier=Barrier(2)
    def run(action):
        barrier.wait(timeout=10)
        try:
            if action=="accept":
                return staff.accept(target_token,identifier,AcceptInvitation(token=raw,accept=True),str(uuid4()),data["invitation"]["version"],csrf,"concurrency","accept")[0]
            body=RevokeInvitation(action="revoke",reason="cancel") if action=="revoke" else ReissueInvitation(action="reissue",grants=(),permission_catalog_version="permissions-v3",reason="rotate")
            return staff.action(owner_token,owner.store_id,identifier,body,str(uuid4()),data["invitation"]["version"],headers["X-CSRF-Token"],"owner")
        except AuthError as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run,"accept"),pool.submit(run,op)]
        results=[f.result(timeout=20) for f in futures]
    assert sum(not isinstance(r,AuthError) for r in results)==1
    with Session(env[1]) as fresh:
        row=fresh.get(StaffInvitation,identifier)
        members=tuple(fresh.scalars(select(StoreMembership).where(StoreMembership.user_id==target.user_id,StoreMembership.store_id==owner.store_id)))
        assert len(members)==(1 if row.status=="accepted" else 0)
        if members:
            assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==members[0].id)))==("menu.read",)
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==2


def test_concurrent_same_key_accept_replay_and_grant_cas(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,_,token,headers=ctx
    target_token,csrf=target_session(ctx)
    identifier=UUID(data["invitation"]["invitation_id"])
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:staff.accept(target_token,identifier,AcceptInvitation(token=raw,accept=True),key,data["invitation"]["version"],csrf,"race","accept"),range(2)))
    assert sorted(r[1] for r in results)==[False,True] and results[0][0]==results[1][0]
    current=staff.memberships(token,owner.store_id)[0].items[0]
    def replace(grants):
        try:return staff.replace(token,owner.store_id,current.membership_id,GrantsRequest(grants=grants,reason="race"),str(uuid4()),current.version,headers["X-CSRF-Token"],"race")
        except AuthError as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(replace,[(),("inventory.read",)]))
    assert sum(isinstance(r,AuthError) and r.status==412 for r in results)==1
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord).where(PermissionEventRecord.membership_id==current.membership_id))==2


def test_atomic_accept_rollback_injected_audit_failure(staff_env,monkeypatch):
    ctx=staff_env
    data,raw=create(ctx)
    token,csrf=target_session(ctx)
    import app.application.use_cases.staff as module
    def broken(*args,**kwargs):raise ValueError("synthetic audit fault")
    monkeypatch.setattr(module,"invitation_event",broken)
    with pytest.raises(ValueError,match="synthetic audit fault"):
        ctx[1].accept(token,UUID(data["invitation"]["invitation_id"]),AcceptInvitation(token=raw,accept=True),str(uuid4()),data["invitation"]["version"],csrf,"rollback","fault")
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(StoreMembership.user_id==ctx[3].user_id))==0
        assert fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"])).status=="pending"
        assert fresh.scalar(select(func.count()).select_from(PermissionEventRecord))==1
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==1


@pytest.mark.parametrize("action", ["owner_revoke","expiry"])
def test_accept_fence_rechecks_after_real_postgresql_lock_wait(staff_env,monkeypatch,action):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,target,_,_=ctx
    token,csrf=target_session(ctx)
    from app.repositories.staff import StaffRepository
    entered,release,waiting=Event(),Event(),Event()
    original=StaffRepository.lock_users
    def observed(repo,identifiers):
        waiting.set()
        return original(repo,identifiers)
    monkeypatch.setattr(StaffRepository,"lock_users",observed)
    def holder():
        with Session(env[1]) as s:
            s.scalar(select(User).where(User.id==owner.user_id).with_for_update())
            entered.set()
            assert release.wait(10)
            if action=="owner_revoke":
                s.scalar(select(StoreMembership).where(StoreMembership.user_id==owner.user_id)).active=False
            s.commit()
    # Expiry test uses a token/session issued shortly before invitation expiry.
    if action=="expiry":
        env[4][0]+=timedelta(days=7)-timedelta(minutes=1)
        token,csrf=target_session(ctx)
    with ThreadPoolExecutor(2) as pool:
        held=pool.submit(holder)
        assert entered.wait(10)
        pending=pool.submit(staff.accept,token,UUID(data["invitation"]["invitation_id"]),AcceptInvitation(token=raw,accept=True),str(uuid4()),data["invitation"]["version"],csrf,"lock-wait","test")
        assert waiting.wait(10) and not pending.done()
        if action=="expiry":env[4][0]+=timedelta(minutes=1)
        release.set()
        held.result(timeout=10)
        with pytest.raises(AuthError,match="INVITATION_AUTHORITY_CHANGED" if action=="owner_revoke" else "INVITATION_EXPIRED"):
            pending.result(timeout=10)
    with Session(env[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(StoreMembership.user_id==target.user_id))==0
        assert fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"])).status=="pending"


@pytest.mark.parametrize("durable", [False,True])
def test_create_commit_error_and_cleanup_never_fabricate_success(staff_env,monkeypatch,durable):
    ctx=staff_env
    env,_,owner,_,_,headers=ctx
    commit,rollback,close=Session.commit,Session.rollback,Session.close
    primary=ValueError("SYNTHETIC-PRIMARY-NO-ECHO")
    def fault(s):
        if any(isinstance(row,StaffRequestReceipt) for row in s.new):
            s.info["injected"]=True
            if durable:commit(s)
            raise primary
        return commit(s)
    def bad_rollback(s):
        rollback(s)
        if s.info.get("injected"):raise OSError("rollback diagnostic")
    def bad_close(s):
        close(s)
        if s.info.get("injected"):raise OSError("close diagnostic")
    with monkeypatch.context() as m:
        m.setattr(Session,"commit",fault)
        m.setattr(Session,"rollback",bad_rollback)
        m.setattr(Session,"close",bad_close)
        response=env[5].post(f"/api/v1/stores/{owner.store_id}/staff-invitations",headers={**headers,"Idempotency-Key":str(uuid4())},
            json=dict(email="failure@example.test",grants=[],permission_catalog_version="permissions-v3",reason="failure test"))
        assert response.status_code==503 and "SYNTHETIC-PRIMARY" not in response.text
    assert any("rollback failed" in n for n in primary.__notes__) and any("close failed" in n for n in primary.__notes__)
    with Session(env[1]) as fresh:
        expected=int(durable)
        assert fresh.scalar(select(func.count()).select_from(StaffInvitation))==expected
        assert fresh.scalar(select(func.count()).select_from(InvitationDeliveryIntent))==expected
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==expected
        assert fresh.scalar(select(func.count()).select_from(InvitationEventRecord))==expected


def test_delivery_commit_uncertainty_no_send_or_duplicate_and_expiry_cleanup(staff_env,monkeypatch):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,_,_,_,_=ctx
    dispatcher=InvitationDispatcher(env[1],staff.settings,staff.clock)
    commit=Session.commit
    def fault(s):
        claimed=any(isinstance(row,InvitationDeliveryIntent) and row.claim for row in s.dirty)
        commit(s)
        if claimed:raise OSError("synthetic lost claim acknowledgement")
    deliveries=[]
    with monkeypatch.context() as m:
        m.setattr(Session,"commit",fault)
        with pytest.raises(OSError):dispatcher.dispatch("support-test",KEY,lambda *a:deliveries.append(a))
    assert not deliveries
    assert dispatcher.dispatch("support-test",KEY,lambda *a:deliveries.append(a))==dict(delivered=0,failed=0,cancelled=0)
    assert not deliveries
    with Session(env[1]) as fresh:
        intent=fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"]))
        assert intent.claim and intent.status=="queued" and intent.ciphertext is not None
    env[4][0]+=timedelta(days=7)
    dispatcher.dispatch("support-test",KEY,lambda *a:deliveries.append(a))
    with Session(env[1]) as fresh:
        intent=fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"]))
        assert intent.status=="failed" and intent.ciphertext is None
        assert fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"])).status=="pending"
    assert not deliveries


def test_owner_create_idempotency_replay_and_store_mutation_throttle(staff_env):
    ctx=staff_env
    key=str(uuid4())
    first,_=create(ctx,key=key)
    again,_=create(ctx,key=key)
    assert first==again
    env,_,owner,_,_,headers=ctx
    base=f"/api/v1/stores/{owner.store_id}/staff-invitations"
    body=dict(email="other@example.test",grants=[],permission_catalog_version="permissions-v3",reason="different")
    assert env[5].post(base,headers={**headers,"Idempotency-Key":key},json=body).status_code==409
    # Nine invalid catalogue mutations count; receipt replay does not count.
    for i in range(9):
        r=env[5].post(base,headers={**headers,"Idempotency-Key":str(uuid4())},json=body|{"permission_catalog_version":"old"})
        assert r.status_code==409
    r=env[5].post(base,headers={**headers,"Idempotency-Key":str(uuid4())},json=body)
    assert r.status_code==429 and int(r.headers["retry-after"])>0
    r=env[5].post(base,headers={**headers,"Idempotency-Key":key},json=dict(email="staff@example.test",grants=["menu.read"],permission_catalog_version="permissions-v3",reason="Synthetic invitation"))
    assert r.status_code==201 and r.json()["data"]==first


def test_accept_pinned_consent_empty_grants_and_token_errors(staff_env):
    ctx=staff_env
    data,raw=create(ctx,grants=())
    env,_,owner,_,_,_=ctx
    token,csrf=target_session(ctx)
    base=f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}"
    for header in ({},{"X-Invitation-Token":"x"*513}):
        r=env[5].get(base,headers=header)
        assert r.status_code==422 and r.json()["error"]["code"]=="INVALID_TOKEN"
    headers={"Origin":ORIGIN,"X-CSRF-Token":csrf,"Idempotency-Key":str(uuid4()),"If-Match":data["invitation"]["version"]}
    for body in ({"token":raw,"accept":False},{"token":raw,"accept":True,"grants":["menu.read"]}):
        assert env[5].post(base+"/accept",headers=headers,json=body).status_code==422
    response=env[5].post(base+"/accept",headers=headers,json={"token":raw,"accept":True})
    assert response.status_code==201 and response.json()["data"]["accepted_grants"]==[]
    assert env[5].get(f"/api/v1/stores/{owner.store_id}").json()["data"]["membership"]["effective_permissions"]==[]


def test_two_dispatchers_one_send_and_reissue_during_delivery(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    env,staff,owner,_,token,headers=ctx
    dispatcher=InvitationDispatcher(env[1],staff.settings,staff.clock)
    entered,release=Event(),Event()
    deliveries=[]
    def send(address,identifier,secret):
        assert env[1].pool.checkedout()==0
        deliveries.append(secret.get_secret_value())
        entered.set()
        assert release.wait(10)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(dispatcher.dispatch,"support-test",KEY,send)
        assert entered.wait(10)
        second=pool.submit(dispatcher.dispatch,"support-test",KEY,send)
        assert second.result(timeout=10)==dict(delivered=0,failed=0,cancelled=0)
        rotated=staff.action(token,owner.store_id,UUID(data["invitation"]["invitation_id"]),
            ReissueInvitation(action="reissue",grants=(),permission_catalog_version="permissions-v3",reason="Rotate in flight"),
            str(uuid4()),data["invitation"]["version"],headers["X-CSRF-Token"],"delivery-race")
        release.set()
        assert first.result(timeout=10)["cancelled"]==1
    assert deliveries==[raw]
    with Session(env[1]) as fresh:
        row=fresh.get(StaffInvitation,UUID(data["invitation"]["invitation_id"]))
        assert row.version==rotated.invitation.version and row.delivery_status=="queued"
        assert fresh.get(InvitationDeliveryIntent,UUID(data["delivery"]["attempt_id"])).ciphertext is None
        assert fresh.get(InvitationDeliveryIntent,rotated.delivery.attempt_id).ciphertext is not None
    target_token,_=target_session(ctx)
    with pytest.raises(AuthError,match="INVITATION_NOT_FOUND"):
        staff.offer(target_token,row.id,raw,"old-mail")


def test_cross_store_invitation_and_wrong_account_offer_no_private_facts(staff_env):
    ctx=staff_env
    data,raw=create(ctx)
    env,_,owner,_,_,headers=ctx
    base=f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}"
    wrong=env[5].get(base,headers={"X-Invitation-Token":raw})
    assert wrong.status_code==403 and wrong.json()["error"]["code"]=="INVITATION_ACCOUNT_MISMATCH"
    assert "staff@example.test" not in wrong.text and str(owner.store_id) not in wrong.text and "menu.read" not in wrong.text
    target_session(ctx)
    unknown=env[5].get(f"/api/v1/staff-invitations/{uuid4()}",headers={"X-Invitation-Token":"bad"})
    bad=env[5].get(base,headers={"X-Invitation-Token":"bad"})
    assert unknown.status_code==bad.status_code==404
    assert unknown.json()["error"]==bad.json()["error"]
    owner_session(ctx)
    foreign=setup(env,"foreign-owner@example.test")
    bad_scope=env[5].post(f"/api/v1/stores/{foreign.store_id}/staff-invitations/{data['invitation']['invitation_id']}/actions",
        headers={**headers,"If-Match":data["invitation"]["version"],"Idempotency-Key":str(uuid4())},json=dict(action="revoke",reason="spoof store"))
    assert bad_scope.status_code==404
    existing=env[5].post(f"/api/v1/stores/{owner.store_id}/staff-invitations",headers={**headers,"Idempotency-Key":str(uuid4())},
        json=dict(email="owner@example.test",grants=[],permission_catalog_version="permissions-v3",reason="Owner must not become Staff"))
    assert existing.status_code==409 and existing.json()["error"]["code"]=="MEMBERSHIP_ALREADY_EXISTS"
    with Session(env[1]) as fresh:
        owner_member=fresh.scalar(select(StoreMembership).where(StoreMembership.store_id==owner.store_id,StoreMembership.user_id==owner.user_id))
        owner_membership_id=owner_member.id
    request_headers={**headers,"If-Match":"irrelevant-version","Idempotency-Key":str(uuid4())}
    forbidden=env[5].put(f"/api/v1/stores/{owner.store_id}/memberships/{owner_membership_id}/permissions",
        headers=request_headers,json=dict(grants=[],reason="Cannot edit Owner"))
    assert forbidden.status_code==422 and forbidden.json()["error"]["code"]=="INVALID_TARGET"
    accepted=accept_http(ctx,data,raw).json()["data"]
    with Session(env[1]) as s:
        s.get(StoreMembership,UUID(accepted["membership_id"])).active=False
        s.commit()
    owner_session(ctx)
    inactive=env[5].put(f"/api/v1/stores/{owner.store_id}/memberships/{accepted['membership_id']}/permissions",
        headers={**headers,"If-Match":accepted["authorization_version_at_acceptance"],"Idempotency-Key":str(uuid4())},
        json=dict(grants=[],reason="Must not reactivate"))
    assert inactive.status_code==409 and inactive.json()["error"]["code"]=="MEMBERSHIP_INACTIVE"


def test_grant_replace_audit_failure_rolls_back_all(staff_env,monkeypatch):
    ctx=staff_env
    data,raw=create(ctx)
    assert accept_http(ctx,data,raw).status_code==201
    env,staff,owner,_,token,headers=ctx
    current=staff.memberships(token,owner.store_id)[0].items[0]
    import app.application.use_cases.staff as module
    def fault(*args,**kwargs):raise ValueError("synthetic permission audit fault")
    monkeypatch.setattr(module,"permission_event",fault)
    with pytest.raises(ValueError):
        staff.replace(token,owner.store_id,current.membership_id,GrantsRequest(grants=(),reason="rollback"),str(uuid4()),current.version,headers["X-CSRF-Token"],"fault")
    assert staff.memberships(token,owner.store_id)[0].items[0]==current
    with Session(env[1]) as fresh:
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id==current.membership_id)))==("menu.read",)
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt))==2


def test_dispatch_claim_refreshes_stale_preread_after_lock_wait(staff_env,monkeypatch):
    ctx=staff_env
    create(ctx)
    env,staff,*_=ctx
    from app.repositories.staff import StaffRepository
    original=StaffRepository.invitation
    pre_read=Barrier(2)
    def synchronized(repo,identifier,store_id=None,*,locked=False):
        if locked and not repo.session.info.get("synchronized"):
            repo.session.info["synchronized"]=True
            pre_read.wait(timeout=10)
        return original(repo,identifier,store_id,locked=locked)
    monkeypatch.setattr(StaffRepository,"invitation",synchronized)
    dispatcher=InvitationDispatcher(env[1],staff.settings,staff.clock)
    deliveries=[]
    # Restrict barrier to claim, not finalization, whose fresh Session does not
    # pre-read an intent into its identity map.
    def send(*args):
        deliveries.append(args[1])
        monkeypatch.setattr(StaffRepository,"invitation",original)
    with ThreadPoolExecutor(2) as pool:
        outcomes=list(pool.map(lambda _:dispatcher.dispatch("support-test",KEY,send),range(2)))
    assert len(deliveries)==1 and sum(o["delivered"] for o in outcomes)==1
    with Session(env[1]) as fresh:
        intent=fresh.scalar(select(InvitationDeliveryIntent))
        assert intent.status=="delivered" and intent.claim is not None and intent.ciphertext is None
