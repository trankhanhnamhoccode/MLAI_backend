"""Staff → pinned Owner review → Staff continuation; no provider or implicit writes."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.application.use_cases.import_staging import ImportStaging
from app.application.use_cases.notification_delivery import NotificationDispatcher
from app.application.contracts.staff import GrantsRequest
from app.domain.permissions import PERMISSIONS
from app.models import Product, SalesDaily
from app.models.auth import MembershipGrant
from app.models.import_staging import ImportBatch, ImportProfileVersion
from app.models.collaboration import MappingSubmissionRecord
from tests.integration.test_auth_public import env, ORIGIN
from tests.integration.test_staff_public import staff_env, create, accept_http, target_session, owner_session
from tests.integration.test_import_staging import analyzed, sales_bytes, previewed, post
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_classification import listing, mapping, confirm
from tests.integration.test_import_commit import commit, finished
from tests.integration.test_mapping_submissions import submit


def staff_context(ctx, grants):
    data, raw = create(ctx, grants=tuple(sorted(grants)))
    assert accept_http(ctx, data, raw).status_code == 201
    _, csrf = target_session(ctx)
    service = ImportStaging(ctx[0][2], ctx[0][0])
    ctx[0][5].app.state.import_staging = service
    pid = uuid4()
    with Session(ctx[0][1]) as s:
        s.add(Product(id=pid, store_id=ctx[2].store_id, name='Explicit test Product', selling_unit='cup', active=True))
        s.commit()
    return ctx[0], ctx[2], service, {'Origin': ORIGIN, 'X-CSRF-Token': csrf}, pid


def grant(ctx, permissions):
    owner_session(ctx)
    member = ctx[1].memberships(ctx[4], ctx[2].store_id)[0].items[0]
    ctx[1].replace(ctx[4], ctx[2].store_id, member.membership_id,
        GrantsRequest(grants=tuple(sorted(permissions)), reason='Explicit test grant change'),
        str(uuid4()), member.version, ctx[5]['X-CSRF-Token'], 'test')


def switch_staff(ctx, staff):
    _, csrf = target_session(ctx)
    return (*staff[:3], {'Origin': ORIGIN, 'X-CSRF-Token': csrf}, staff[4])


@pytest.mark.parametrize('new_entity', [False, True])
def test_staff_owner_staff_approval_is_not_commit_or_domain_grant(staff_env, monkeypatch, new_entity):
    ctx = staff_env
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider must remain off'))
    grants = PERMISSIONS - {'sales.record'}
    staff = staff_context(ctx, grants)
    content = sales_bytes(staff)
    if new_entity:
        content = content.replace(str(staff[4]).encode(), b'NEW-COFFEE')
    ident = analyzed(staff, content)
    declared = declare_context(staff, ident)
    if new_entity:
        guide = declared['completion_guidance']
        assert not guide['profiles'][0]['can_submit']
        entity = next(i for i in listing(staff, ident) if i['issue_type'] == 'identity')
        assert any(i['mapping_id'] == entity['mapping_id'] and i['category'] == 'entity_resolution'
                   for i in guide['issues'])
        changed = mapping(staff, ident, entity, {'resolution': dict(kind='new_entity_proposal', entity='product',
            source_business_key='NEW-COFFEE', metadata=dict(name='Explicit new coffee', selling_unit='cup',
                sku='NEW-COFFEE', price=None, active=True), evidence_reference='Explicit proposed Product')})
        assert changed.status_code == 200, changed.text
    prepared = summary(staff, ident)
    guide = prepared['completion_guidance']['profiles'][0]
    assert guide['review_ready'] and guide['can_submit'] and not guide['can_owner_review']
    assert not prepared['can_preview']
    response, profile, _ = submit(staff, ident)
    assert response.status_code == 201, response.text
    row = response.json()['data']
    queued = summary(staff, ident)['completion_guidance']['profiles'][0]
    assert queued['submission_id'] == row['submission_id'] and not queued['can_submit']
    base = f'/api/v1/stores/{ctx[2].store_id}/mapping-submissions'
    owner_session(ctx)
    owner = (staff[0], staff[1], staff[2], ctx[5], staff[4])
    pinned = ctx[0][5].get(base + '/' + row['submission_id']).json()['data']
    assert pinned['spec'] == prepared['profile_proposals'][0]['spec']
    assert pinned['source']['evidence_references'] and pinned['evidence']['cells']
    assert NotificationDispatcher(ctx[0][1], ctx[0][2].clock).dispatch() == 1
    notification = ctx[0][5].get('/api/v1/notifications').json()['data']['items'][0]
    read = ctx[0][5].patch('/api/v1/notifications/' + notification['notification_id'], json={'read': True},
        headers={**ctx[5], 'Idempotency-Key': str(uuid4()), 'If-Match': '"' + notification['version'] + '"'})
    assert read.status_code == 200, read.text
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(MappingSubmissionRecord, UUID(row['submission_id'])).state == 'submitted'
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    result = post(owner, f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate', proposal_revision=profile['proposal_revision'], expected_active_version=None,
             submission_id=row['submission_id'], expected_submission_version=row['version'], reason='Review exact pinned spec'),
        match=profile['lifecycle_revision'])
    assert result.status_code == 200, result.text
    staff = switch_staff(ctx, staff)
    refreshed = summary(staff, ident)
    guidance = refreshed['completion_guidance']
    assert guidance['profiles'][0]['binding_usable'] and guidance['profiles'][0]['submission_state'] == 'approved'
    assert not guidance['profiles'][0]['can_submit'] and not guidance['profiles'][0]['can_owner_review']
    assert refreshed['can_preview'] and guidance['preview']['can_request_preview']
    assert not any(i['category'] == 'source_context' for i in guidance['issues'])
    assert not refreshed['completion_guidance']['issues']
    preview = previewed(staff, ident)
    assert confirm(staff, ident, preview).status_code == 403  # Approval does not grant sales.record.
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert fresh.scalar(select(func.count()).select_from(Product)) == 1
        assert 'sales.record' not in fresh.scalars(select(MembershipGrant.permission)).all()
    grant(ctx, PERMISSIONS)
    staff = switch_staff(ctx, staff)
    preview = ctx[0][5].get('/api/v1/imports/' + ident + '?include_preview=true').json()['data']
    confirmed = confirm(staff, ident, preview)
    assert confirmed.status_code == 200, confirmed.text
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    completion = finished(staff, ident, commit(staff, ident, preview, confirmed.json()['data']['import_revision']))
    with Session(ctx[0][1]) as fresh:
        sale = fresh.scalar(select(SalesDaily))
        assert sale.quantity == 105
        assert fresh.scalar(select(func.count()).select_from(Product)) == 1 + int(new_entity)
        assert fresh.get(ImportBatch, UUID(ident)).analysis_json['completion']
    assert completion['commit_id']
    # Source must be explicit per upload; an unchanged approved spec needs no N5 again.
    again = analyzed(staff, content)
    reused = declare_context(staff, again)
    assert reused['can_preview'] and reused['profile_proposals'] == []
    assert reused['completion_guidance']['issues'] == []
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1


def test_current_grants_control_guidance_and_revoke_blocks_source_reads(staff_env):
    ctx = staff_env
    staff = staff_context(ctx, PERMISSIONS)
    ident = analyzed(staff)
    declare_context(staff, ident)
    grant(ctx, PERMISSIONS - {'mapping.propose', 'import.preview'})
    staff = switch_staff(ctx, staff)
    guide = summary(staff, ident)['completion_guidance']
    assert not guide['profiles'][0]['can_submit'] and not guide['profiles'][0]['can_owner_review']
    assert 'PERMISSION_DENIED' in guide['profiles'][0]['reason_codes']
    assert all(not i['can_act'] for i in guide['issues'])
    assert not guide['preview']['can_request_preview']
    grant(ctx, PERMISSIONS - {'sales.read'})
    switch_staff(ctx, staff)
    assert ctx[0][5].get('/api/v1/imports/' + ident + '/mapping-summary').status_code == 403


@pytest.mark.parametrize('decision', ['request_changes', 'reject'])
def test_staff_reads_owner_changes_and_explicitly_resubmits_new_pins(staff_env, decision):
    ctx = staff_env
    staff = staff_context(ctx, PERMISSIONS)
    ident = analyzed(staff)
    declare_context(staff, ident)
    response, profile, _ = submit(staff, ident)
    row = response.json()['data']
    owner_session(ctx)
    owner = (staff[0], staff[1], staff[2], ctx[5], staff[4])
    result = post(owner, f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision=decision, proposal_revision=profile['proposal_revision'], reason='Clarify source evidence',
             submission_id=row['submission_id'], expected_submission_version=row['version']),
        match=profile['lifecycle_revision'])
    assert result.status_code == 200, result.text
    staff = switch_staff(ctx, staff)
    guide = summary(staff, ident)['completion_guidance']['profiles'][0]
    assert guide['submission_state'] == ('changes_requested' if decision == 'request_changes' else 'rejected')
    changed = declare_context(staff, ident, {'evidence_reference': 'Staff explicitly clarified source evidence'})
    assert not any(i['category'] == 'source_context' for i in changed['completion_guidance']['issues'])
    again, current, _ = submit(staff, ident)
    assert again.status_code == 201, again.text
    assert again.json()['data']['submission_id'] != row['submission_id']
    assert current['proposal_revision'] != profile['proposal_revision']
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(MappingSubmissionRecord, UUID(row['submission_id'])).state in {'changes_requested', 'rejected'}
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
