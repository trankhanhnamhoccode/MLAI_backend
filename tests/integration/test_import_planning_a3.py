"""A3 gaps only: public Staff invitation -> source reuse -> canonical commit.

All facts are synthetic public imports; the owned PostgreSQL fixture resets only
the configured Import DB. No provider, browser, new feature or business seed.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.use_cases.import_staging import ImportStaging
from app.models import Product, SalesDaily
from app.models.auth import MembershipGrant
from app.models.import_staging import ImportProfileVersion
from tests.integration.test_auth_public import env, ORIGIN
from tests.integration.test_staff_public import (
    staff_env, create, accept_http, owner_session, target_session,
)
from tests.integration.test_import_staging import csv_source, approved, previewed, post
from tests.integration.test_import_commit import analyzed_files, commit, confirm, finished
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_rule_review import declare_context, summary
from tests.integration.test_import_setup_stock import review_batch, complete
from tests.integration.test_readiness_context import config, readiness, known_facts, read


def test_staff_public_grants_source_reuse_commit_and_alias_change_needs_owner(staff_env, monkeypatch):
    import pytest
    from app.infrastructure import import_suggestions

    monkeypatch.setattr(import_suggestions, 'suggest_sheet',
        lambda *a, **kw: pytest.fail('A3 cannot invoke provider'))
    e, _, owner, _, _, owner_headers = staff_env
    service = ImportStaging(e[2], e[0].model_copy(update={'import_llm_suggestions_enabled': False}))
    e[5].app.state.import_staging = service
    c = e, owner, service, owner_headers, None
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 0
    menu = analyzed_files(c, [('menu.csv', csv_source('products', [dict(
        source_business_key='COFFEE', name='A3 synthetic coffee', selling_unit='cup',
        sku='A3-COFFEE', price=None, active=True)]))])
    review_batch(c, menu, creations={'COFFEE': ('product', dict(
        name='A3 synthetic coffee', selling_unit='cup', sku='A3-COFFEE', price=None, active=True))})
    complete(c, menu)
    with Session(e[1]) as fresh:
        pid = fresh.scalar(select(Product.id))
    content = csv_source('sales', [dict(product_id=str(pid), sales_date='2026-10-09',
        quantity='2', unit='cup', business_report_key='A3-DAY-1', is_stockout=False)])
    first = analyzed_files(c, [('sales.csv', content)])
    decision = approved(c, first)
    # Approved profile alone never grants import/domain rights. Owner explicitly
    # invites the Staff through public N12/N19 with only existing permissions.
    grants = ('import.create','import.upload','import.analyze','import.read','import.preview','import.commit',
        'mapping.read','mapping.propose','menu.read','ingredient.read','recipe.read',
        'sales.read','sales.record','inventory.read','supplier.read','procurement.cost.read','budget.read')
    grants = tuple(sorted(grants))
    invitation, raw = create(staff_env, grants=grants)
    accepted = accept_http(staff_env, invitation, raw)
    assert accepted.status_code == 201, accepted.text
    membership = UUID(accepted.json()['data']['membership_id'])
    _, csrf = target_session(staff_env)
    staff = e, owner, service, {'Origin': ORIGIN, 'X-CSRF-Token': csrf}, pid
    second = analyzed_files(staff, [('sales.csv', content)])
    before = summary(staff, second)
    assert not before['binding_refs'] and not before['can_preview']
    reused = declare_context(staff, second, dict(source_system_key='POS-A', report_type='daily-sales'))
    assert reused['can_preview'] and reused['profile_proposals'] == []
    assert reused['binding_refs'][0]['version'] == decision['approved_version']
    read = previewed(staff, second)
    reviewed = confirm(staff, second, read)
    assert reviewed.status_code == 200, reviewed.text
    result = finished(staff, second, commit(staff, second, read, reviewed.json()['data']['import_revision']))
    with Session(e[1]) as fresh:
        sale, = fresh.scalars(select(SalesDaily)).all()
        assert sale.quantity == 2 and sale.is_stockout is False
        assert set(fresh.scalars(select(MembershipGrant.permission).where(
            MembershipGrant.membership_id == membership))) == set(grants)
        assert result['canonical_references'][0]['provenance']['quantity']['source_column_index'] == 2
    # Unknown row token blocks despite identical headers/source. Explicit alias
    # binding changes the persisted spec and requires Owner approval; Staff cannot.
    third = analyzed_files(staff, [('sales.csv', content.replace(str(pid).encode(), b'NEW-TOKEN'))])
    unresolved = declare_context(staff, third, dict(source_system_key='POS-A', report_type='daily-sales'))
    assert not unresolved['can_preview'] and unresolved['profile_proposals'] == []
    unknown = next(i for i in listing(staff, third) if i['issue_type'] == 'identity')
    bound = mapping(staff, third, unknown, dict(resolution=dict(kind='identity_binding',canonical_id=str(pid))))
    assert bound.status_code == 200 and bound.json()['data']['approval_required']
    pending = summary(staff, third)
    assert not pending['can_preview']
    proposal, = pending['profile_proposals']
    body = dict(decision='approve_activate', proposal_revision=proposal['proposal_revision'],
        expected_active_version=proposal['active_version'], reason='A3 reviewed exact alias binding')
    denied = post(staff, f"/stores/{owner.store_id}/mapping-profiles/{proposal['profile_id']}/decisions",
        body, match=proposal['lifecycle_revision'])
    assert denied.status_code == 403, denied.text
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion).where(
            ImportProfileVersion.profile_id == UUID(decision['profile_id']))) == 1
    owner_session(staff_env)
    approved_alias = post(c, f"/stores/{owner.store_id}/mapping-profiles/{proposal['profile_id']}/decisions",
        body, match=proposal['lifecycle_revision'])
    assert approved_alias.status_code == 200, approved_alias.text
    _, csrf = target_session(staff_env)
    staff[3]['X-CSRF-Token'] = csrf
    reread = previewed(staff, third)
    confirmed = confirm(staff, third, reread)
    assert confirmed.status_code == 200, confirmed.text
    replay = finished(staff, third, commit(staff, third, reread, confirmed.json()['data']['import_revision']))
    assert replay['outcome'] == 'no_changes'
    with Session(e[1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 1
        assert fresh.scalar(select(SalesDaily.quantity)) == 2


def test_unsupported_safety_floor_excludes_other_ingredient_and_future_period(readiness):
    """Persisted unsupported rule fixture, not an importable business default.

The main Store flow seeds no facts. This isolated negative case reuses the
existing readiness fixture to test exactly the computed dependency/date fence.
"""
    from datetime import date
    from uuid import uuid4
    from app.models import BusinessConstraint, Ingredient

    c = readiness
    ingredient, _ = known_facts(c)
    unrelated = uuid4()
    common = dict(store_id=c[1].store_id, scope_type='INGREDIENT',
        constraint_type='MIN_SAFETY_STOCK', numeric_value=0, unit='ml',
        version=1, effective_to=None, active=True)
    with Session(c[0][1]) as s, s.begin():
        s.add(Ingredient(id=unrelated, store_id=c[1].store_id, name='Unused synthetic ingredient',
            base_unit='ml', expiry_tracking=False, active=True))
        s.flush()
        s.add_all([
            BusinessConstraint(id=uuid4(), scope_id=unrelated, effective_from=date(2026,10,10), **common),
            BusinessConstraint(id=uuid4(), scope_id=ingredient, effective_from=date(2026,10,17), **common),
        ])
    outside = read(c)
    assert outside.status_code == 200, outside.text
    assert outside.json()['data']['scope_estimate']['estimated_computable_product_count'] == 1
    assert 'MIN_SAFETY_STOCK_UNSUPPORTED' not in {
        b['code'] for b in outside.json()['data']['actions'][0]['blockers']}
    with Session(c[0][1]) as s, s.begin():
        s.add(BusinessConstraint(id=uuid4(), scope_id=ingredient,
            effective_from=date(2026,10,10), effective_to=date(2026,10,16),
            **{**{k:v for k,v in common.items() if k != 'effective_to'}, 'version':2}))
    inside = read(c)
    assert inside.status_code == 200, inside.text
    action = inside.json()['data']['actions'][0]
    assert not action['can_execute']
    assert 'MIN_SAFETY_STOCK_UNSUPPORTED' in {b['code'] for b in action['blockers']}
    assert read(c, 'forecast').json()['data']['actions'][0]['can_execute']
