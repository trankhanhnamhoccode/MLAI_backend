"""B4 linked HTTP/PostgreSQL acceptance. All mail is captured by fake adapters."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.provisioning import ProvisionStoreCommand, IssueCredentialCommand
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.use_cases.staff import StaffUseCases
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.domain.permissions import PERMISSIONS
from app.infrastructure.auth_crypto import digest, verify_password
from app.models import Store, StoreMembership, User
from app.models.auth import AuthAccount, AuthSession, CredentialToken, MembershipGrant, AuthAudit
from app.models.staff import StaffInvitation, StaffRequestReceipt, InvitationEventRecord, PermissionEventRecord
from tests.integration.test_email_verification import env, signup, delivered_token, complete, post, EMAIL, PASSWORD, ORIGIN
from tests.integration.test_password_reset import reset_env, request_reset, reset_token, finish, NEW_PASSWORD

COOKIE = '__Host-shelfcash_session'
NEW_KEYS = tuple(sorted(('calendar.read', 'calendar.write', 'usage.history.read',
    'usage.history.write', 'purchase.history.read', 'purchase.history.write')))


def restore(client, login):
    client.cookies.clear()
    client.cookies.set(COOKIE, login[0], domain='backend.example.test', path='/')


def http_login(env, email, password=PASSWORD):
    # Each actor/device has its own browser cookie jar; login rotates its prior cookie.
    env[6].cookies.clear()
    response = post(env, 'login', {'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return env[6].cookies.get(COOKIE), response.json()['data']['session']['csrf_token']


def provision_owner(env):
    settings = env[7]
    tool = AssistedProvisioning(env[0], settings, clock=lambda: env[1][0])
    email = 'owner@example.test'
    def store(existing=None):
        return tool.provision(ProvisionStoreCommand(request_reference=str(uuid4()),
            evidence_reference='Synthetic verified owner', email=email,
            display_name='Synthetic owner', store_name='Synthetic cafe', existing_user_id=existing),
            settings.auth_operator_id, settings.auth_operator_key)
    first = store()
    sent = []
    tool.issue(IssueCredentialCommand(user_id=first.user_id, purpose='SETUP',
        request_reference=str(uuid4()), evidence_reference='Synthetic owner setup', verified_email=email),
        settings.auth_operator_id, settings.auth_operator_key,
        lambda address, secret: sent.append(secret.get_secret_value()))
    result = finish(env, sent[0], PASSWORD)
    assert result.status_code == 200 and 'set-cookie' not in result.headers
    second = store(first.user_id)
    return first, second, http_login(env, email), sent[0]


def mutation_headers(login, version=None, key=None):
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': login[1], 'Idempotency-Key': key or str(uuid4())}
    if version is not None:
        headers['If-Match'] = version
    return headers


def invitation(env, store, owner, *, email=EMAIL, version='permissions-v3', grants=('menu.read',)):
    restore(env[6], owner)
    response = env[6].post(f'/api/v1/stores/{store}/staff-invitations',
        headers=mutation_headers(owner), json={'email': email, 'grants': list(grants),
            'permission_catalog_version': version, 'reason': 'Synthetic invitation'})
    if version != 'permissions-v3':
        assert response.status_code == 409 and response.json()['error']['code'] == 'PERMISSION_CATALOG_CHANGED'
        return
    assert response.status_code == 201, response.text
    messages = []
    dispatcher = InvitationDispatcher(env[0], env[7], clock=lambda: env[1][0])
    assert dispatcher.dispatch(env[7].auth_operator_id, env[7].auth_operator_key,
        lambda address, identifier, secret: messages.append((address, identifier, secret.get_secret_value())))['delivered'] == 1
    data = response.json()['data']['invitation']
    assert messages[0][:2] == (email, UUID(data['invitation_id']))
    return data, messages[0][2]


def decision(env, login, offer, raw, action='accept', *, key=None, headers=None):
    restore(env[6], login)
    body = {'token': raw, 'accept': True} if action == 'accept' else {'token': raw, 'reason': 'Synthetic refusal'}
    return env[6].post(f"/api/v1/staff-invitations/{offer['invitation_id']}/{action}",
        headers=mutation_headers(login, offer['version'], key) | (headers or {}), json=body)


def context(env, store, login):
    restore(env[6], login)
    return env[6].get(f'/api/v1/stores/{store}')


@pytest.mark.parametrize('registered_before_invite', [True, False])
def test_linked_signup_invitation_live_grants_multistore_decline_and_reset(reset_env, registered_before_invite, caplog):
    e = reset_env[0]
    e[6].app.state.staff = StaffUseCases(e[2], e[7])
    secrets = [PASSWORD, NEW_PASSWORD]
    if registered_before_invite:
        signup(e)
        verification = delivered_token(e)
        secrets.append(verification)
        assert complete(e, verification).status_code == 200
        with Session(e[0]) as fresh:
            for model in (Store, StoreMembership, MembershipGrant, AuthSession):
                assert fresh.scalar(select(func.count()).select_from(model)) == 0
    first, second, owner, setup_raw = provision_owner(e)
    secrets.append(setup_raw)
    invitation(e, first.store_id, owner, version='permissions-v2')
    offer, raw = invitation(e, first.store_id, owner)
    secrets.append(raw)
    if not registered_before_invite:
        with Session(e[0]) as fresh:
            assert fresh.scalar(select(User).where(User.email == EMAIL)) is None
        signup(e)
        verification = delivered_token(e)
        secrets.append(verification)
        assert finish(e, verification).status_code == 400  # VERIFY cannot become N7 credentials token.
        response = complete(e, verification)
        assert response.status_code == 200 and 'set-cookie' not in response.headers
    holder = http_login(e, EMAIL)
    assert e[6].get('/api/v1/auth/me').status_code == 200
    assert e[6].get('/api/v1/stores').json()['data']['items'] == []
    assert context(e, first.store_id, holder).status_code == 404
    assert context(e, second.store_id, holder).status_code == 404
    read = e[6].get(f"/api/v1/staff-invitations/{offer['invitation_id']}", headers={'X-Invitation-Token': raw})
    assert read.status_code == 200 and read.json()['data']['can_accept']
    assert decision(e, holder, offer, raw, headers={'Origin': 'https://wrong.example.test'}).status_code == 403
    assert decision(e, holder, offer, raw, headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    assert finish(e, raw).status_code == 400
    assert complete(e, raw).status_code == 400
    key = str(uuid4())
    accepted = decision(e, holder, offer, raw, key=key)
    assert accepted.status_code == 201, accepted.text
    receipt = accepted.json()['data']
    mid = UUID(receipt['membership_id'])
    with Session(e[0]) as fresh:
        member = fresh.get(StoreMembership, mid)
        uid = member.user_id
        assert member.store_id == first.store_id and member.role == 'STAFF'
        assert tuple(fresh.scalars(select(MembershipGrant.permission).where(MembershipGrant.membership_id == mid))) == ('menu.read',)
        assert fresh.get(StaffInvitation, UUID(offer['invitation_id'])).status == 'accepted'
    assert context(e, first.store_id, holder).json()['data']['membership']['effective_permissions'] == ['menu.read']
    assert context(e, second.store_id, holder).status_code == 404
    # Catalogue updates never expand an existing Staff grant set.
    restore(e[6], holder)
    assert e[6].get(f'/api/v1/stores/{first.store_id}/memberships').status_code == 403
    e[6].cookies.clear()
    assert e[6].get(f'/api/v1/stores/{first.store_id}/memberships').status_code == 401
    restore(e[6], owner)
    members_url = f'/api/v1/stores/{first.store_id}/memberships'
    listing_response = e[6].get(members_url)
    assert listing_response.status_code == 200, listing_response.text
    listing = listing_response.json()['data']
    assert listing['permission_catalog_version'] == 'permissions-v3' and len(listing['permission_catalog']) == 43
    item = listing['items'][0]
    path = members_url + f'/{mid}/permissions'
    invalid = e[6].put(path, headers=mutation_headers(owner, item['version']),
        json={'grants': ['unknown.key'], 'reason': 'Unknown grant'})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'UNKNOWN_PERMISSION'
    changed = e[6].put(path, headers=mutation_headers(owner, item['version']),
        json={'grants': sorted(PERMISSIONS), 'reason': 'Explicit full catalogue grant'})
    assert changed.status_code == 200, changed.text
    assert set(context(e, first.store_id, holder).json()['data']['membership']['effective_permissions']) == PERMISSIONS
    restore(e[6], owner)
    stale = e[6].put(path, headers=mutation_headers(owner, item['version']),
        json={'grants': [], 'reason': 'Stale revoke'})
    assert stale.status_code == 412
    revoked = e[6].put(path, headers=mutation_headers(owner, changed.json()['data']['membership']['version']),
        json={'grants': [], 'reason': 'Revoke all including history keys'})
    assert revoked.status_code == 200
    assert context(e, first.store_id, holder).json()['data']['membership']['effective_permissions'] == []
    replay = decision(e, holder, offer, raw, key=key)
    assert replay.status_code == 200 and replay.json()['data'] == receipt
    assert context(e, first.store_id, holder).json()['data']['membership']['effective_permissions'] == []
    declined_offer, declined_raw = invitation(e, second.store_id, owner)
    secrets.append(declined_raw)
    declined = decision(e, holder, declined_offer, declined_raw, 'decline')
    assert declined.status_code == 200 and declined.json()['data']['next_action'] == 'return_to_stores'
    assert context(e, second.store_id, holder).status_code == 404
    with Session(e[0]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(StoreMembership.user_id == uid)) == 1
        assert fresh.scalar(select(func.count()).select_from(MembershipGrant).where(MembershipGrant.membership_id == mid)) == 0
    restore(e[6], owner)
    blocked = e[6].post(f'/api/v1/stores/{second.store_id}/staff-invitations/{declined_offer["invitation_id"]}/actions',
        headers=mutation_headers(owner, declined.json()['data']['version']),
        json={'action': 'reissue', 'grants': ['menu.read'], 'permission_catalog_version': 'permissions-v3', 'reason': 'Try reissue'})
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'INVITATION_STATE_CONFLICT'
    new_offer, new_raw = invitation(e, second.store_id, owner, grants=NEW_KEYS)
    secrets.append(new_raw)
    assert new_offer['invitation_id'] != declined_offer['invitation_id']
    assert decision(e, holder, new_offer, new_raw).status_code == 201
    assert context(e, first.store_id, holder).json()['data']['membership']['effective_permissions'] == []
    assert context(e, second.store_id, holder).json()['data']['membership']['effective_permissions'] == list(NEW_KEYS)
    restore(e[6], holder)
    assert len(e[6].get('/api/v1/stores').json()['data']['items']) == 2
    # Membership revocation uses the existing persisted-state boundary: no new API invented.
    with Session(e[0]) as s:
        s.get(StoreMembership, mid).active = False
        s.commit()
    assert context(e, first.store_id, holder).status_code == 404
    assert decision(e, holder, offer, raw, key=key).status_code == 403
    assert context(e, second.store_id, holder).status_code == 200
    device2 = http_login(e, EMAIL)
    with Session(e[0]) as fresh:
        old_hash = fresh.get(User, uid).password_hash
    request_reset(reset_env)
    reset_raw = reset_token(reset_env)
    secrets.append(reset_raw)
    assert complete(e, reset_raw).status_code == 400
    assert decision(e, holder, new_offer, reset_raw).status_code == 404
    assert finish(e, reset_raw, 'short').status_code == 422
    with Session(e[0]) as fresh:
        assert fresh.get(User, uid).password_hash == old_hash
        assert fresh.get(AuthSession, digest(holder[0])).revoked_at is None
        assert fresh.get(AuthSession, digest(device2[0])).revoked_at is None
    for session in (holder, device2):
        restore(e[6], session)
        assert e[6].get('/api/v1/auth/me').status_code == 200
    result = finish(e, reset_raw)
    assert result.status_code == 200 and 'set-cookie' not in result.headers
    for session in (holder, device2):
        restore(e[6], session)
        assert e[6].get('/api/v1/auth/me').status_code == 401
        assert e[6].get(f'/api/v1/stores/{second.store_id}').status_code == 401
    assert post(e, 'login', {'email': EMAIL, 'password': PASSWORD}).status_code == 401
    renewed = http_login(e, EMAIL, NEW_PASSWORD)
    assert context(e, second.store_id, renewed).json()['data']['membership']['effective_permissions'] == list(NEW_KEYS)
    assert context(e, first.store_id, renewed).status_code == 404
    assert context(e, first.store_id, owner).status_code == 200
    with Session(e[0]) as fresh:
        assert verify_password(fresh.get(User, uid).password_hash, NEW_PASSWORD)
        assert fresh.get(CredentialToken, digest(reset_raw)).consumed_at is not None
        assert all(row.revoked_at is not None for row in fresh.scalars(select(AuthSession).where(
            AuthSession.user_id == uid, AuthSession.digest != digest(renewed[0]))))
        assert fresh.get(StoreMembership, mid).active is False
        durable = str([row.record_json for model in (StaffRequestReceipt, InvitationEventRecord, PermissionEventRecord)
            for row in fresh.scalars(select(model))])
        durable += str([(row.evidence_reference, row.request_reference) for row in fresh.scalars(select(AuthAudit))])
    for secret in secrets:
        assert secret not in durable and secret not in caplog.text
