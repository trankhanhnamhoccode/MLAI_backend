"""B3 real HTTP/guarded PostgreSQL, synthetic identities and fake delivery only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.auth import AuthError
from app.application.contracts.staff import AcceptInvitation, DeclineInvitation, RevokeInvitation
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.models import Store, StoreMembership, User
from app.models.auth import AuthAccount, MembershipGrant
from app.models.staff import InvitationDeliveryIntent, InvitationEventRecord, StaffInvitation, StaffRequestReceipt
from tests.integration.test_auth_public import env, setup, ORIGIN, KEY
from tests.integration.test_staff_public import staff_env, create, target_session, owner_session, accept_http


def decline_http(ctx, data, raw, *, key=None, reason='Synthetic refusal', match=None, headers=None):
    token, csrf = target_session(ctx)
    return ctx[0][5].post(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}/decline",
        headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf, 'Idempotency-Key': key or str(uuid4()),
            'If-Match': match or data['invitation']['version']} | (headers or {}),
        json={'token': raw, 'reason': reason})


def target_memberships(session, ctx):
    return tuple(session.scalars(select(StoreMembership).where(StoreMembership.user_id == ctx[3].user_id)))


def test_fake_email_offer_decline_fresh_persistence_and_no_authority(staff_env):
    ctx = staff_env
    data, raw = create(ctx, grants=('budget.read', 'menu.read'))
    sent = []
    dispatcher = InvitationDispatcher(ctx[0][1], ctx[1].settings, ctx[1].clock)
    assert dispatcher.dispatch('support-test', KEY,
        lambda address, identifier, secret: sent.append((address, identifier, secret.get_secret_value())))['delivered'] == 1
    assert sent[0][0] == 'staff@example.test' and sent[0][2] == raw
    identifier = UUID(data['invitation']['invitation_id'])
    target_session(ctx)
    url = f'/api/v1/staff-invitations/{identifier}'
    offer = ctx[0][5].get(url, headers={'X-Invitation-Token': raw})
    assert offer.status_code == 200 and offer.json()['data']['can_decline']
    with Session(ctx[0][1]) as fresh:
        grant_count = fresh.scalar(select(func.count()).select_from(MembershipGrant))
    key = str(uuid4())
    response = decline_http(ctx, data, raw, key=key, match=offer.headers['etag'])
    assert response.status_code == 200, response.text
    receipt = response.json()['data']
    assert receipt['status'] == 'declined' and receipt['next_action'] == 'return_to_stores'
    assert receipt['version'] != data['invitation']['version']
    assert raw not in response.text and response.headers['cache-control'] == 'no-store'
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation, identifier)
        event = fresh.get(InvitationEventRecord, UUID(receipt['event_id'])).record_json
        assert row.status == 'declined' and row.declined_at is not None and row.version == receipt['version']
        assert event['kind'] == 'DECLINED' and event['recipient_user_id'] == str(ctx[3].user_id)
        assert event['reason'] == 'Synthetic refusal' and event['before_version'] == data['invitation']['version']
        assert not target_memberships(fresh, ctx)
        assert fresh.scalar(select(func.count()).select_from(MembershipGrant)) == grant_count
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 2
    terminal = ctx[0][5].get(url, headers={'X-Invitation-Token': raw})
    assert terminal.status_code == 200
    assert terminal.json()['data']['invitation']['declined_at'] == receipt['declined_at']
    assert terminal.json()['data']['can_accept'] is False and terminal.json()['data']['can_decline'] is False
    assert ctx[0][5].get('/api/v1/stores').json()['data']['items'] == []
    assert ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}').status_code == 404
    # Same body/If-Match replay; original matching quoted header is part of the digest.
    repeat = decline_http(ctx, data, raw, key=key, match=offer.headers['etag'])
    assert repeat.status_code == 200 and repeat.json()['data'] == receipt


def test_declined_terminal_reissue_blocked_new_identity_accepts_filters_and_events(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    assert decline_http(ctx, data, raw).status_code == 200
    assert accept_http(ctx, data, raw).json()['error']['code'] == 'INVITATION_STATE_CONFLICT'
    assert decline_http(ctx, data, raw).json()['error']['code'] == 'INVITATION_STATE_CONFLICT'
    owner_session(ctx)
    base = f'/api/v1/stores/{ctx[2].store_id}/staff-invitations'
    listing = ctx[0][5].get(base, params={'status': 'declined'}).json()['data']['items']
    assert len(listing) == 1 and listing[0]['declined_at'] is not None
    events = ctx[0][5].get(base, params={'view': 'events', 'invitation_id': data['invitation']['invitation_id']})
    assert 'DECLINED' in {e['kind'] for e in events.json()['data']['items']}
    for action in ('reissue', 'revoke'):
        body = {'action': action, 'reason': 'Owner retry'}
        if action == 'reissue': body.update(grants=['menu.read'], permission_catalog_version='permissions-v3')
        response = ctx[0][5].post(base + f"/{data['invitation']['invitation_id']}/actions",
            headers=ctx[5] | {'Idempotency-Key': str(uuid4()), 'If-Match': listing[0]['version']}, json=body)
        assert response.status_code == 409 and response.json()['error']['code'] == 'INVITATION_STATE_CONFLICT'
    new, new_raw = create(ctx)
    assert new['invitation']['invitation_id'] != data['invitation']['invitation_id']
    assert accept_http(ctx, new, new_raw).status_code == 201
    target_session(ctx)
    # A terminal declined offer remains readable even after a later membership exists.
    offer = ctx[0][5].get(f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}",
        headers={'X-Invitation-Token': raw})
    assert offer.status_code == 200 and offer.json()['data']['can_decline'] is False
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(StaffInvitation, UUID(data['invitation']['invitation_id'])).status == 'declined'
        assert len(target_memberships(fresh, ctx)) == 1


@pytest.mark.parametrize('change,status,code', [
    ('token',404,'INVITATION_NOT_FOUND'), ('holder',404,'INVITATION_NOT_FOUND'),
    ('unverified',401,'UNAUTHENTICATED'), ('inactive',401,'UNAUTHENTICATED'),
    ('proof',403,'ACCOUNT_EMAIL_NOT_VERIFIED'), ('issuer',409,'INVITATION_AUTHORITY_CHANGED'),
    ('issuer_membership',409,'INVITATION_AUTHORITY_CHANGED'), ('store',403,'PERMISSION_DENIED'),
    ('expiry',410,'INVITATION_EXPIRED'), ('revoked',410,'INVITATION_REVOKED'),
    ('catalog',409,'PERMISSION_CATALOG_CHANGED'), ('grants',422,'UNKNOWN_PERMISSION'),
    ('stale',412,'INVITATION_REVISION_CONFLICT'), ('csrf',403,'CSRF_CHECK_FAILED'),
])
def test_current_fences_preserve_pending_and_no_authority(staff_env, change, status, code):
    ctx = staff_env
    data, raw = create(ctx)
    token, csrf = target_session(ctx)
    identifier = UUID(data['invitation']['invitation_id'])
    with Session(ctx[0][1]) as s:
        if change == 'holder':
            s.get(User, ctx[3].user_id).email = 'different@example.test'
            s.get(AuthAccount, ctx[3].user_id).verified_email = 'different@example.test'
        elif change == 'unverified':
            account = s.get(AuthAccount, ctx[3].user_id)
            account.verified_at = account.verified_email = account.verification_reference = None
            account.credential_ready = False
        elif change == 'proof': s.get(AuthAccount, ctx[3].user_id).verification_reference = ''
        elif change == 'inactive': s.get(User, ctx[3].user_id).active = False
        elif change == 'issuer': s.get(User, ctx[2].user_id).active = False
        elif change == 'issuer_membership':
            s.scalar(select(StoreMembership).where(StoreMembership.user_id == ctx[2].user_id)).active = False
        elif change == 'store': s.get(Store, ctx[2].store_id).active = False
        elif change == 'expiry': s.get(StaffInvitation, identifier).expires_at = ctx[0][4][0] - timedelta(seconds=1)
        elif change == 'revoked': s.get(StaffInvitation, identifier).status = 'revoked'
        elif change == 'catalog': s.get(StaffInvitation, identifier).permission_catalog_version = 'stale'
        elif change == 'grants': s.get(StaffInvitation, identifier).offered_grants = ['unknown']
        s.commit()
    with pytest.raises(AuthError) as caught:
        ctx[1].decline(token, identifier, DeclineInvitation(token='wrong' if change == 'token' else raw,
            reason='Synthetic refusal'), str(uuid4()), 'stale' if change == 'stale' else data['invitation']['version'],
            'wrong' if change == 'csrf' else csrf, 'test', 'fence')
    assert (caught.value.status, caught.value.code) == (status, code)
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation, identifier)
        assert row.status == ('revoked' if change == 'revoked' else 'pending') and row.declined_at is None
        assert not target_memberships(fresh, ctx)
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 1


@pytest.mark.parametrize('headers,status', [
    ({'Origin':'https://evil.example.test'},403), ({'X-CSRF-Token':''},403),
    ({'If-Match':''},422), ({'Idempotency-Key':''},422),
])
def test_http_origin_csrf_and_invalid_headers(staff_env, headers, status):
    data, raw = create(staff_env)
    assert decline_http(staff_env, data, raw, headers=headers).status_code == status


def test_missing_if_match_and_session_and_accept_false_are_rejected(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    _, csrf = target_session(ctx)
    url = f"/api/v1/staff-invitations/{data['invitation']['invitation_id']}/decline"
    response = ctx[0][5].post(url, headers={'Origin':ORIGIN, 'X-CSRF-Token':csrf,
        'Idempotency-Key':str(uuid4())}, json={'token':raw, 'reason':'Decline'})
    assert response.status_code == 428
    ctx[0][5].cookies.clear()
    assert ctx[0][5].post(url, headers={'Origin':ORIGIN, 'If-Match':data['invitation']['version'],
        'Idempotency-Key':str(uuid4())}, json={'token':raw, 'reason':'Decline'}).status_code == 401
    target_session(ctx)
    response = ctx[0][5].post(url.replace('/decline','/accept'), headers={'Origin':ORIGIN,
        'X-CSRF-Token':csrf, 'If-Match':data['invitation']['version'], 'Idempotency-Key':str(uuid4())},
        json={'token':raw, 'accept':False})
    assert response.status_code == 422


@pytest.mark.parametrize('change', ['proof','issuer','store','holder','inactive'])
def test_replay_current_authority_and_no_new_transition(staff_env, change):
    ctx = staff_env
    data, raw = create(ctx)
    key = str(uuid4())
    receipt = decline_http(ctx, data, raw, key=key).json()['data']
    token, csrf = target_session(ctx)
    with Session(ctx[0][1]) as s:
        if change == 'proof': s.get(AuthAccount, ctx[3].user_id).verification_reference = ''
        elif change == 'issuer': s.get(User, ctx[2].user_id).active = False
        elif change == 'store': s.get(Store, ctx[2].store_id).active = False
        elif change == 'inactive': s.get(User, ctx[3].user_id).active = False
        elif change == 'holder':
            s.get(User, ctx[3].user_id).email = 'new@example.test'
            s.get(AuthAccount, ctx[3].user_id).verified_email = 'new@example.test'
        s.commit()
    with pytest.raises(AuthError):
        ctx[1].decline(token, UUID(data['invitation']['invitation_id']), DeclineInvitation(token=raw,reason='Synthetic refusal'),
            key, data['invitation']['version'], csrf, 'test', 'replay')
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation, UUID(data['invitation']['invitation_id']))
        assert row.status == 'declined' and row.version == receipt['version']
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 2
        assert not target_memberships(fresh, ctx)


def test_key_conflict_rollback_and_lost_commit_ack_replay(staff_env, monkeypatch):
    ctx = staff_env
    data, raw = create(ctx)
    token, csrf = target_session(ctx)
    identifier, key = UUID(data['invitation']['invitation_id']), str(uuid4())
    body = DeclineInvitation(token=raw, reason='Synthetic refusal')
    real_save = ctx[1]._save
    def fail_before_commit(*args):
        real_save(*args)
        raise RuntimeError('Synthetic rollback')
    monkeypatch.setattr(ctx[1], '_save', fail_before_commit)
    with pytest.raises(RuntimeError):
        ctx[1].decline(token,identifier,body,key,data['invitation']['version'],csrf,'test','rollback')
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(StaffInvitation,identifier).status == 'pending'
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 1
        assert fresh.scalar(select(func.count()).select_from(InvitationEventRecord)) == 1
        assert fresh.get(InvitationDeliveryIntent,UUID(data['delivery']['attempt_id'])).ciphertext is not None
    monkeypatch.setattr(ctx[1], '_save', real_save)
    real_commit = Session.commit
    committed = []
    def lose_ack(session):
        is_decline = any(isinstance(row,StaffRequestReceipt) and row.operation.endswith('/decline') for row in session.new)
        real_commit(session)
        if is_decline:
            committed.append(True)
            raise RuntimeError('Synthetic acknowledgment loss')
    monkeypatch.setattr(Session,'commit',lose_ack)
    with pytest.raises(RuntimeError):
        ctx[1].decline(token,identifier,body,key,data['invitation']['version'],csrf,'test','lost-ack')
    assert committed == [True]
    monkeypatch.setattr(Session,'commit',real_commit)
    replay = ctx[1].decline(token,identifier,body,key,data['invitation']['version'],csrf,'test','retry')
    assert replay.status == 'declined'
    with pytest.raises(AuthError) as caught:
        ctx[1].decline(token,identifier,DeclineInvitation(token=raw,reason='Different reason'),key,
            data['invitation']['version'],csrf,'test','conflict')
    assert caught.value.code == 'IDEMPOTENCY_KEY_REUSED'
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 2
        assert fresh.scalar(select(func.count()).select_from(InvitationEventRecord)) == 2
        assert not target_memberships(fresh,ctx)
        assert fresh.get(InvitationDeliveryIntent,UUID(data['delivery']['attempt_id'])).ciphertext is None


@pytest.mark.parametrize('competitor', ['accept','decline','revoke','same_key','all'])
def test_concurrent_single_terminal_transition(staff_env, competitor):
    ctx = staff_env
    data, raw = create(ctx)
    token, csrf = target_session(ctx)
    identifier, revision, key = UUID(data['invitation']['invitation_id']), data['invitation']['version'], str(uuid4())
    barrier = Barrier(3 if competitor == 'all' else 2)
    def run(operation):
        barrier.wait(timeout=10)
        try:
            if operation == 'accept':
                return ctx[1].accept(token,identifier,AcceptInvitation(token=raw,accept=True),str(uuid4()),revision,csrf,'race','accept')[0]
            if operation == 'revoke':
                return ctx[1].action(ctx[4],ctx[2].store_id,identifier,RevokeInvitation(action='revoke',reason='Owner cancel'),
                    str(uuid4()),revision,ctx[5]['X-CSRF-Token'],'revoke')
            return ctx[1].decline(token,identifier,DeclineInvitation(token=raw,reason='Synthetic refusal'),
                key if competitor == 'same_key' else str(uuid4()),revision,csrf,'race','decline')
        except AuthError as error: return error
    with ThreadPoolExecutor(max_workers=3 if competitor == 'all' else 2) as pool:
        operations = ['decline','accept','revoke'] if competitor == 'all' else ['decline',competitor]
        futures = [pool.submit(run,operation) for operation in operations]
        results = [future.result(timeout=30) for future in futures]
    assert sum(not isinstance(r,AuthError) for r in results) == (2 if competitor == 'same_key' else 1)
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation,identifier)
        events = [event.record_json for event in fresh.scalars(select(InvitationEventRecord))]
        assert len([event for event in events if event['kind'] in {'ACCEPTED','DECLINED','REVOKED'}]) == 1
        assert len(target_memberships(fresh,ctx)) == (1 if row.status == 'accepted' else 0)
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 2


def test_http_commit_ack_loss_503_then_exact_receipt_replay(staff_env, monkeypatch):
    from sqlalchemy.exc import OperationalError
    ctx = staff_env
    data, raw = create(ctx)
    commit = Session.commit
    lost = []
    def fault(session):
        is_decline = any(isinstance(row,StaffRequestReceipt) and row.operation.endswith('/decline') for row in session.new)
        commit(session)
        if is_decline:
            lost.append(True)
            raise OperationalError('synthetic commit',{},RuntimeError('synthetic acknowledgment loss'))
    monkeypatch.setattr(Session,'commit',fault)
    key = str(uuid4())
    response = decline_http(ctx,data,raw,key=key)
    assert response.status_code == 503 and lost == [True]
    assert raw not in response.text
    monkeypatch.setattr(Session,'commit',commit)
    replay = decline_http(ctx,data,raw,key=key)
    assert replay.status_code == 200
    with Session(ctx[0][1]) as fresh:
        row = fresh.get(StaffInvitation,UUID(data['invitation']['invitation_id']))
        assert row.version == replay.json()['data']['version']
        assert fresh.scalar(select(func.count()).select_from(StaffRequestReceipt)) == 2
        assert fresh.scalar(select(func.count()).select_from(InvitationEventRecord)) == 2
        assert not target_memberships(fresh,ctx)


@pytest.mark.parametrize('state,expected', [('expired','INVITATION_EXPIRED'),('revoked','INVITATION_REVOKED'),('declined','INVITATION_STATE_CONFLICT')])
def test_state_errors_precede_issuer_change_for_first_execution(staff_env, state, expected):
    ctx = staff_env
    data, raw = create(ctx)
    if state == 'declined': assert decline_http(ctx,data,raw).status_code == 200
    token, csrf = target_session(ctx)
    with Session(ctx[0][1]) as s:
        row = s.get(StaffInvitation,UUID(data['invitation']['invitation_id']))
        if state == 'expired': row.expires_at = ctx[0][4][0] - timedelta(seconds=1)
        elif state == 'revoked': row.status = 'revoked'
        s.get(User,ctx[2].user_id).active = False
        s.commit()
    with pytest.raises(AuthError) as caught:
        ctx[1].decline(token,UUID(data['invitation']['invitation_id']),DeclineInvitation(token=raw,reason='Refuse'),
            str(uuid4()),data['invitation']['version'],csrf,'priority','state')
    assert caught.value.code == expected


@pytest.mark.parametrize('change', ['expiry','issuer','store','proof'])
def test_decline_fences_after_postgresql_lock_wait(staff_env, monkeypatch, change):
    from app.repositories.staff import StaffRepository
    ctx = staff_env
    data, raw = create(ctx)
    identifier = UUID(data['invitation']['invitation_id'])
    if change == 'expiry': ctx[0][4][0] += timedelta(days=7) - timedelta(minutes=1)
    token, csrf = target_session(ctx)
    entered, release, waiting = Event(), Event(), Event()
    original = StaffRepository.lock_users
    def observed(repo, identifiers):
        waiting.set()
        return original(repo, identifiers)
    monkeypatch.setattr(StaffRepository, 'lock_users', observed)
    def holder():
        with Session(ctx[0][1]) as s:
            s.scalar(select(User).where(User.id == ctx[2].user_id).with_for_update())
            entered.set()
            assert release.wait(10)
            if change == 'issuer': s.get(User,ctx[2].user_id).active = False
            elif change == 'store': s.get(Store,ctx[2].store_id).active = False
            elif change == 'proof': s.get(AuthAccount,ctx[3].user_id).verification_reference = ''
            s.commit()
    with ThreadPoolExecutor(2) as pool:
        held = pool.submit(holder)
        assert entered.wait(10)
        pending = pool.submit(ctx[1].decline,token,identifier,DeclineInvitation(token=raw,reason='Refuse'),
            str(uuid4()),data['invitation']['version'],csrf,'wait','fence')
        try:
            assert waiting.wait(10) and not pending.done()
            if change == 'expiry': ctx[0][4][0] += timedelta(minutes=1)
        finally:
            release.set()
        held.result(timeout=10)
        with pytest.raises(AuthError) as caught: pending.result(timeout=10)
    expected = {'expiry':'INVITATION_EXPIRED', 'issuer':'INVITATION_AUTHORITY_CHANGED',
        'store':'PERMISSION_DENIED', 'proof':'ACCOUNT_EMAIL_NOT_VERIFIED'}
    assert caught.value.code == expected[change]
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(StaffInvitation,identifier).status == 'pending'
        assert not target_memberships(fresh,ctx)


def test_replay_preserves_receipt_after_expiry_and_later_membership(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    key = str(uuid4())
    receipt = decline_http(ctx,data,raw,key=key).json()['data']
    owner_session(ctx)
    new, new_raw = create(ctx)
    assert accept_http(ctx,new,new_raw).status_code == 201
    ctx[0][4][0] += timedelta(days=8)
    replay = decline_http(ctx,data,raw,key=key)
    assert replay.status_code == 200 and replay.json()['data'] == receipt
    with Session(ctx[0][1]) as fresh:
        assert len(target_memberships(fresh,ctx)) == 1
        events = [row.record_json for row in fresh.scalars(select(InvitationEventRecord))]
        assert len([e for e in events if e['kind']=='DECLINED']) == 1


def test_recipient_rate_limit_shared_and_failed_decline_has_no_authority(staff_env):
    ctx = staff_env
    data, raw = create(ctx)
    token, csrf = target_session(ctx)
    for _ in range(30):
        with pytest.raises(AuthError, match='INVITATION_NOT_FOUND'):
            ctx[1].decline(token,UUID(data['invitation']['invitation_id']),DeclineInvitation(token='wrong',reason='Refuse'),
                str(uuid4()),data['invitation']['version'],csrf,'limit','failed')
    with pytest.raises(AuthError) as caught:
        ctx[1].decline(token,UUID(data['invitation']['invitation_id']),DeclineInvitation(token=raw,reason='Refuse'),
            str(uuid4()),data['invitation']['version'],csrf,'limit','blocked')
    assert caught.value.status == 429
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(StaffInvitation,UUID(data['invitation']['invitation_id'])).status == 'pending'
        assert not target_memberships(fresh,ctx)
