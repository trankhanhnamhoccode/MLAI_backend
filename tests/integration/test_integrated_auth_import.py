"""Public Staff grants v3 govern real Import history with the same live session."""
import base64
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.application.use_cases.staff import StaffUseCases
from app.infrastructure.auth_crypto import digest
from app.models import ImportHistoryRecord, InventoryMovement, StoreMembership
from app.models.auth import MembershipGrant
from tests.integration.test_auth_public import env, setup
from tests.integration.test_import_classification import confirm
from tests.integration.test_import_commit import finished, ready
from tests.integration.test_import_history_a2 import accept, ingredient, records
from tests.integration.test_import_rule_review import declare_context, summary
from tests.integration.test_import_staging import analyzed, csv_source, imp, previewed
from tests.integration.test_staff_public import (
    accept_http, create, owner_session, target_session,
)

BASE_GRANTS = tuple(sorted((
    'import.create', 'import.upload', 'import.analyze', 'import.read',
    'import.preview', 'import.commit', 'mapping.read', 'mapping.propose',
    'menu.read', 'ingredient.read', 'recipe.read', 'inventory.read',
    'sales.read', 'supplier.read', 'procurement.cost.read', 'budget.read',
)))
NEW_KEYS = frozenset((
    'calendar.read', 'calendar.write', 'usage.history.read', 'usage.history.write',
    'purchase.history.read', 'purchase.history.write',
))


@pytest.mark.parametrize('schema,prefix', [
    ('calendar_events', 'calendar'),
    ('usage_history', 'usage.history'),
    ('purchase_history', 'purchase.history'),
])
def test_owner_api_grants_staff_history_import_and_live_revoke(imp, ingredient, schema, prefix):
    e, owner, service, owner_headers, product = imp
    content = csv_source(schema, [records(schema, imp, ingredient)])
    # Owner reviews the exact reusable spec; no history business row is committed.
    ready(imp, content)
    settings = e[0].model_copy(update={
        'auth_delivery_encryption_key': SecretStr(base64.b64encode(bytes(range(32))).decode()),
    })
    staff = StaffUseCases(e[2], settings)
    e[5].app.state.staff = staff
    target = setup(e, 'staff@example.test', store=False)
    context = e, staff, owner, target, e[5].cookies.get('__Host-shelfcash_session'), owner_headers
    invitation, raw = create(context, grants=BASE_GRANTS)
    sent = []
    delivered = InvitationDispatcher(e[1], settings, lambda: e[4][0]).dispatch(
        settings.auth_operator_id, settings.auth_operator_key,
        lambda address, invitation_id, secret: sent.append(digest(secret.get_secret_value())),
    )
    assert delivered == {'delivered': 1, 'failed': 0, 'cancelled': 0}
    assert sent == [digest(raw)]  # Fake delivery only; retain no clear token in evidence.
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(StoreMembership).where(
            StoreMembership.user_id == target.user_id)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord)) == 0
    acceptance_key = str(uuid4())
    accepted = accept_http(context, invitation, raw, key=acceptance_key)
    assert accepted.status_code == 201, accepted.text
    mid = UUID(accepted.json()['data']['membership_id'])
    staff_token, csrf = target_session(context)
    staff_headers = {'Origin': owner_headers['Origin'], 'X-CSRF-Token': csrf}
    staff_import = e, owner, service, staff_headers, product
    context_url = f'/api/v1/stores/{owner.store_id}'
    initial = e[5].get(context_url)
    assert initial.status_code == 200, initial.text
    assert set(initial.json()['data']['membership']['effective_permissions']) == set(BASE_GRANTS)
    assert not NEW_KEYS & set(initial.json()['data']['membership']['effective_permissions'])

    owner_session(context)
    members_url = f'/api/v1/stores/{owner.store_id}/memberships'
    listing = e[5].get(members_url).json()['data']
    assert listing['permission_catalog_version'] == 'permissions-v3'
    member = next(row for row in listing['items'] if row['membership_id'] == str(mid))
    path = members_url + f'/{mid}/permissions'
    granted = set(BASE_GRANTS) | {prefix + '.read', prefix + '.write'}
    changed = e[5].put(path, headers={**owner_headers, 'Idempotency-Key': str(uuid4()),
        'If-Match': member['version']}, json={'grants': sorted(granted), 'reason': 'Explicit history shift'})
    assert changed.status_code == 200, changed.text
    e[5].cookies.set('__Host-shelfcash_session', staff_token, domain='backend.example.test', path='/')
    current = e[5].get(context_url)
    assert set(current.json()['data']['membership']['effective_permissions']) == granted
    ident = analyzed(staff_import, content)
    assert not summary(staff_import, ident)['binding_refs']
    reused = declare_context(staff_import, ident, {'source_system_key': 'POS-A', 'report_type': 'daily-sales'})
    assert reused['can_preview'] and reused['profile_proposals'] == []
    read = previewed(staff_import, ident)
    confirmed = confirm(staff_import, ident, read)
    assert confirmed.status_code == 200, confirmed.text
    completed = finished(staff_import, ident, accept(
        staff_import, ident, read, confirmed.json()['data']['import_revision']))
    assert completed['canonical_references'][0]['history_record']['domain'] == schema
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord)) == 1
        assert set(fresh.scalars(select(MembershipGrant.permission).where(
            MembershipGrant.membership_id == mid))) == granted
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0

    owner_session(context)
    remaining = granted - {prefix + '.write'}
    revoked = e[5].put(path, headers={**owner_headers, 'Idempotency-Key': str(uuid4()),
        'If-Match': changed.json()['data']['membership']['version']},
        json={'grants': sorted(remaining), 'reason': 'Revoke history writes'})
    assert revoked.status_code == 200, revoked.text
    # Restore exactly the same Staff session: authority cannot be cached in it.
    e[5].cookies.set('__Host-shelfcash_session', staff_token, domain='backend.example.test', path='/')
    assert set(e[5].get(context_url).json()['data']['membership']['effective_permissions']) == remaining
    replay = e[5].post(f"/api/v1/staff-invitations/{invitation['invitation']['invitation_id']}/accept",
        headers={**staff_headers, 'Idempotency-Key': acceptance_key,
                 'If-Match': invitation['invitation']['version']}, json={'token': raw, 'accept': True})
    assert replay.status_code == 200 and replay.json()['data'] == accepted.json()['data']
    assert set(e[5].get(context_url).json()['data']['membership']['effective_permissions']) == remaining
    new_record = dict(records(schema, imp, ingredient), source_record_key='new-after-revoke')
    another = analyzed(staff_import, csv_source(schema, [new_record]))
    declare_context(staff_import, another, {'source_system_key': 'POS-A', 'report_type': 'daily-sales'})
    new_read = previewed(staff_import, another)
    review = confirm(staff_import, another, new_read)
    # Confirmation already requires current domain write authority; a revoked
    # actor cannot freeze a usable confirmation or reach canonical acceptance.
    assert review.status_code == 403 and review.json()['error']['code'] == 'PERMISSION_DENIED'
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord)) == 1
        assert set(fresh.scalars(select(MembershipGrant.permission).where(
            MembershipGrant.membership_id == mid))) == remaining
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0
