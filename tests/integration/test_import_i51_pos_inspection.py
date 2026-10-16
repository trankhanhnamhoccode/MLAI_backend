"""Original POS inspection and blocked preview without establishing business facts."""
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
import hashlib
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, Ingredient, SalesDaily, Recipe, InventoryLot, InventoryMovement, ImportHistoryRecord
from app.models.import_staging import ImportBatch, ImportProfile, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store
from tests.integration.test_import_commit import analyzed_files
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_staging import post
from tests.integration.import_i5_evidence import CASES, SOURCE_DIRECTORY, cells_by_sheet, save, i5_trace


def test_original_pos_scope_inspection_keeps_ambiguity_and_preview_has_no_canonical_effects(fresh_store, monkeypatch, i5_trace):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider forbidden'))
    pos_case, menu_case = CASES[0], CASES[5]
    originals = [SOURCE_DIRECTORY / c['file'] for c in (pos_case, menu_case)]
    if not all(p.is_file() for p in originals):
        pytest.skip('Original POS/Menu absent; source-faithful acceptance remains BLOCKED')
    for path, case in zip(originals, (pos_case, menu_case)):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
    pos_name, menu_name = pos_case['sheets'][1], menu_case['sheets'][0]
    pos, menu = cells_by_sheet(originals[0])[pos_name], cells_by_sheet(originals[1])[menu_name]
    physical = sorted({int(k[1:]) for k in pos if k.startswith('A') and k[1:].isdigit() and int(k[1:]) >= 4})
    assert len(physical) == 945
    keys, quantities, flags, discrepancies = [], {}, Counter(), []
    for number in physical:
        day = date(1899, 12, 30) + timedelta(days=int(pos[f'A{number}']))
        token, amount = pos[f'B{number}'], Decimal(pos[f'C{number}'])
        assert amount >= 0 and amount == amount.to_integral_value()
        keys.append((day, token))
        quantities[number] = amount
        flags[pos[f'F{number}']] += 1
        if Decimal(pos[f'E{number}']) != amount * Decimal(pos[f'D{number}']):
            discrepancies.append(number)
    assert len(set(keys)) == 945 and len({k[0] for k in keys}) == 189
    assert min(k[0] for k in keys) == date(2026, 1, 1) and max(k[0] for k in keys) == date(2026, 7, 8)
    assert sum(v == 0 for v in quantities.values()) == 23
    assert sorted(flags.values()) == [18, 927]
    candidates = [dict(pos_token=menu[f'C{n}'], menu_row=n, source_code=menu[f'A{n}'],
                       unit=menu[f'E{n}'], price=menu[f'H{n}'], status=menu[f'J{n}'],
                       binding_status='PROPOSAL_NOT_CANONICAL_BINDING') for n in range(4, 9)]
    assert {k[1] for k in keys} == {c['pos_token'] for c in candidates}
    assert len({c['source_code'] for c in candidates}) == 5
    context = fresh_store  # Auth/empty Store only; no catalog prerequisites.
    ident = analyzed_files(context, [(originals[0].name, originals[0].read_bytes())])
    current = summary(context, ident)
    sheet = next(s for s in current['sheets'] if s['name'] == pos_name)
    assert sheet['excel_date_system'] == '1900' and sheet['header_row'] == 3
    assert sheet['row_count'] == 1155  # Includes 210 styled empty physical rows.
    for sh in current['sheets']:
        response = context[0][5].get(f'/api/v1/imports/{ident}/sheets/{sh["sheet_id"]}/field-options')
        assert response.status_code == 200, response.text
    readme = next(s for s in current['sheets'] if s['name'] == 'README')
    issue = next(i for i in listing(context, ident) if i['sheet_id'] == readme['sheet_id'] and i['issue_type'] == 'classification')
    response = mapping(context, ident, issue, {'resolution': dict(kind='sheet_type', sheet_type=None,
        ignored=True, acknowledgment=True, reason='User-approved POS scope; README remains raw evidence')})
    assert response.status_code == 200, response.text
    for column in (3, 4, 6):  # User explicitly excludes price/revenue/promotion fields.
        issue = next(i for i in listing(context, ident) if i['sheet_id'] == sheet['sheet_id']
                     and i['source_location']['source_column_index'] == column)
        response = mapping(context, ident, issue, {'resolution': dict(kind='ignored_optional_field',
            evidence_reference='User-approved POS scope: preserve D/E/G raw; no other canonical facts')})
        assert response.status_code == 200, response.text
    current = summary(context, ident)
    assert next(s for s in current['sheets'] if s['name'] == 'README')['ignored']
    remaining = listing(context, ident)
    unresolved = [i for i in remaining if i['sheet_id'] == sheet['sheet_id'] and not i['ignored']]
    assert any(i['issue_type'] == 'source_context' and i['status'] != 'resolved' for i in unresolved)
    assert any(i['issue_type'] == 'column' and i['source_location']['source_column_index'] == 2
               and i['status'] != 'resolved' for i in unresolved)
    assert not current['can_preview'] and current['binding_refs'] == [] and current['semantic_calls_used'] == 0
    read = context[0][5].get('/api/v1/imports/' + ident).json()['data']
    response = post(context, '/imports/' + ident + '/process', dict(phase='preview',
        mapping_revision=current['mapping_revision']), match=read['import_revision'])
    assert response.status_code == 409 and response.json()['error']['code'] == 'UNRESOLVED_REQUIRED_FIELDS'
    assert context[2].run_one() is None
    with Session(context[0][1]) as fresh:
        counts = {m.__tablename__: fresh.scalar(select(func.count()).select_from(m))
                  for m in (Product, Ingredient, SalesDaily, Recipe, InventoryLot, InventoryMovement, ImportHistoryRecord)}
        assert all(v == 0 for v in counts.values())
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
        assert all(not p.proposal_json.get('entities') for p in fresh.scalars(select(ImportProfile)))
        batch = fresh.get(ImportBatch, UUID(ident))
        raw = next(s for s in batch.analysis_json['sources'] if s['sheet_id'] == sheet['sheet_id'])
        empty = [r['row_number'] for r in raw['rows'] if all(c['raw'] in (None, '') for c in r['cells'])]
        assert empty == list(range(949, 1159)) and len(raw['rows']) == 1155
        assert not batch.analysis_json.get('completion')
    assert not any(e['path'].split('?')[0].endswith('/decisions') for e in i5_trace)
    for path, case in zip(originals, (pos_case, menu_case)):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
    save('original-pos-inspection', dict(outcome='BLOCKED_PENDING_OWNER_FACTS_NOT_END_TO_END_PASS',
        import_id=ident, source_sha256=pos_case['sha256'], menu_sha256=menu_case['sha256'],
        populated_rows=945, distinct_dates=189, duplicate_product_date_keys=0, zero_quantities=23,
        stockout_source_tokens=dict(flags), revenue_arithmetic_discrepancy_rows=discrepancies,
        styled_empty_rows=empty, data_rows_excluded=0, ignored_sheet='README', ignored_column_indices=[3, 4, 6],
        product_link_candidates=candidates, unresolved_issues=unresolved, summary=current,
        preview_error=response.json()['error'], canonical_counts=counts,
        limits='No source identity/SLX semantics/Product binding approval, no N5/confirm/commit; numeric structure is not business-semantics proof'))
