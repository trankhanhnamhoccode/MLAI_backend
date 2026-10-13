from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.application.import_sales_groups import finish_sales
from app.application.import_commit import commit_rows
from app.application.contracts.import_mapping import CommitRequest
from app.application.contracts.auth import AuthError
from tests.unit.test_import_preview import case as preview_case

DAY = '2026-10-09'


def case(*args, **kwargs):
    kwargs.setdefault('semantics', 'daily_total')
    return preview_case(*args, **kwargs)


def source(pid, quantity='0', key='report', **extra):
    return dict(product_id=pid, sales_date=DAY, quantity=quantity, unit='cup', business_report_key=key, **extra)


def snapshot(pid, quantity=None, flag=None):
    return dict(products=[dict(id=str(pid), selling_unit='cup')],
        sales_daily=[] if quantity is None else [dict(product_id=str(pid), sales_date=DAY,
            quantity=quantity, is_stockout=flag)])


@pytest.mark.parametrize('flag', [True, False, None])
def test_stockout_three_states_preview_no_zero_inference(flag):
    pid = uuid4()
    row, = case('sales', [source(pid, is_stockout=flag)], snapshot(pid))
    assert not row.blockers and row.after.quantity == '0'
    assert row.after.is_stockout is flag and row.normalized_source_stockout is flag
    assert row.sales_contributions[0].is_stockout is flag


def test_reimport_missing_stockout_requires_explicit_batch_policy():
    pid = uuid4()
    row, = case('sales', [source(pid, '105')], snapshot(pid, '100', True))
    assert 'STOCKOUT_UPDATE_DECLARATION_REQUIRED' in {b.code for b in row.blockers}
    row, = case('sales', [source(pid, '105')], snapshot(pid, '100', True),
        context_fields={'missing_stockout': 'not_provided'})
    assert not row.blockers and row.before.is_stockout is True and row.after.is_stockout is None
    assert row.proposed_action == 'REPLACE_DAILY_TOTAL' and row.confirmation_required


def test_value_aliases_only_explicit_reviewed_tokens():
    pid = uuid4()
    row, = case('sales', [source(pid, is_stockout='YES')], snapshot(pid))
    assert row.blockers[0].code == 'STOCKOUT_VALUE_ALIAS_REQUIRED'
    row, = case('sales', [source(pid, is_stockout='YES')], snapshot(pid),
        context_fields={'stockout_aliases': [{'token': 'YES', 'value': True}]})
    assert not row.blockers and row.after.is_stockout is True
    assert 'declared_stockout_aliases' in next(p.applied_rule_ids for p in row.provenance if p.field == 'is_stockout')


def test_quantity_only_preserves_exact_prior_contribution_not_canonical_inference():
    pid = uuid4()
    data = snapshot(pid, '100', True)
    data['import_sales_sources'] = [dict(product_id=str(pid), sales_date=DAY,
        source_system_key='POS-A', report_type='report-1', business_report_key='report',
        source_revision=1, canonical_revision=1, source_quantity='100', canonical_quantity='100',
        source_stockout=True, canonical_stockout=True, semantics='daily_total')]
    row, = case('sales', [source(pid, '105', is_stockout=None)], data,
        context_fields={'missing_stockout': 'quantity_only'})
    assert not row.blockers and row.after.quantity == '105' and row.after.is_stockout is True
    assert row.normalized_source_stockout is True and row.stockout_update == 'quantity_only'
    row, = case('sales', [source(pid, '105')], data, context_fields={'missing_stockout': 'not_provided'})
    assert not row.blockers and row.after.is_stockout is None


def test_new_daily_report_key_does_not_prove_independence_even_with_equal_quantity():
    pid = uuid4()
    data = snapshot(pid, '100', False)
    data['import_sales_sources'] = [dict(product_id=str(pid), sales_date=DAY,
        source_system_key='OTHER', report_type='report-1', business_report_key='report-A',
        source_revision=1, canonical_revision=1, source_quantity='100', canonical_quantity='100',
        source_stockout=False, canonical_stockout=False, semantics='daily_total')]
    row, = case('sales', [source(pid, '100', 'report-B', is_stockout=False)], data)
    assert 'SALES_OVERLAP_UNRESOLVED' in {b.code for b in row.blockers}


def test_old_pending_sales_preview_requires_fresh_plan_not_implicit_stockout_write():
    pid = uuid4()
    row, = case('sales', [source(pid, '100', is_stockout=False)], snapshot(pid))
    body = CommitRequest(phase='commit', preview_id=uuid4(), preview_digest='digest', confirm=True, resolutions=())
    preview = SimpleNamespace(content_json={'summary': {'blockers': []}, 'rows': [row.model_dump(mode='json')]})
    assert commit_rows(preview, body)[0].sales_contributions
    preview.content_json['rows'][0].pop('sales_contributions')
    with pytest.raises(AuthError) as error:
        commit_rows(preview, body)
    assert error.value.code == 'SALES_PLAN_REVIEW_REQUIRED'


def grouped(pid, entries, data=None):
    data = data or snapshot(pid)
    rows = []
    specs = {}
    for quantity, key, flag in entries:
        row, = case('sales', [source(pid, quantity, key, is_stockout=flag)], data,
            semantics='disjoint_contribution')
        rows.append(row)
        specs[str(row.source_location.sheet_id)] = SimpleNamespace(
            scope=SimpleNamespace(source_system_key='POS-A', report_type='report-1'), sales_semantics='disjoint_contribution')
    result, = finish_sales(rows, specs, data)
    return result


def test_independent_batch_sum_order_and_unknown_false():
    pid = uuid4()
    entries = [('100', 'A', False), ('105', 'B', None)]
    for order in (entries, list(reversed(entries))):
        row = grouped(pid, order)
        assert not row.blockers and row.after.quantity == '205' and row.after.is_stockout is None
        assert row.proposed_action == 'MERGE_DISJOINT_SALES' and row.confirmation_required
        assert [c.business_report_key for c in row.sales_contributions] == ['A', 'B']
        assert len(row.source_locations) == 2


def test_same_contribution_exact_duplicate_collapses_but_conflict_blocks_both_orders():
    pid = uuid4()
    row = grouped(pid, [('100', 'A', False), ('100', 'A', False)])
    assert not row.blockers and row.after.quantity == '100' and len(row.sales_contributions) == 1
    assert len(row.sales_contributions[0].source_locations) == 2
    for entries in ([('100', 'A', False), ('105', 'A', False)], [('105', 'A', False), ('100', 'A', False)]):
        row = grouped(pid, entries)
        assert row.proposed_action == 'BLOCKED'
        assert {b.code for b in row.blockers} == {'SALES_CONTRIBUTION_CONFLICT'}


@pytest.mark.parametrize('entries', [
    [('100', 'A', None)],  # B's true hides A's observation correction in aggregate.
    [('105', 'A', False), ('100', 'B', True)],  # Quantity revisions cancel in total.
])
def test_contribution_correction_requires_resolution_even_when_aggregate_unchanged(entries):
    pid = uuid4()
    data = snapshot(pid, '205', True)
    data['import_sales_sources'] = [dict(product_id=str(pid), sales_date=DAY,
        source_system_key='POS-A', report_type='report-1', business_report_key=key,
        source_revision=1, canonical_revision=1, source_quantity=quantity,
        canonical_quantity='205', source_stockout=flag, canonical_stockout=True,
        semantics='disjoint_contribution') for key, quantity, flag in [('A', '100', False), ('B', '105', True)]]
    row = grouped(pid, entries, data)
    assert not row.blockers and row.after.quantity == '205' and row.after.is_stockout is True
    assert row.proposed_action == 'REPLACE_DAILY_TOTAL' and row.confirmation_required
