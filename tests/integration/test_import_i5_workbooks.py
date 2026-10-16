"""Unchanged supplied workbooks are input evidence, never implicit business facts."""
import hashlib
from uuid import UUID
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Product, Ingredient, SalesDaily, Recipe, InventoryLot, InventoryMovement, SupplierTerm, ImportHistoryRecord
from app.models.import_staging import ImportBatch, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store
from tests.integration.test_import_commit import analyzed_files
from tests.integration.test_import_rule_review import summary
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_staging import post
from tests.integration.import_i5_evidence import CASES, SOURCE_DIRECTORY, cells_by_sheet, save, i5_trace

pytestmark = pytest.mark.usefixtures('i5_trace')


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['file'][:2])
def test_supplied_workbook_hash_cells_api_blockers_and_no_canonical_writes(fresh_store, monkeypatch, case):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('original input cannot call provider'))
    path = SOURCE_DIRECTORY / case['file']
    if not path.is_file():
        pytest.skip('I5 original workbook absent: explicitly supply I5_WORKBOOK_DIRECTORY')
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == case['sha256']
    cells = cells_by_sheet(path)
    assert list(cells) == case['sheets']
    for sheet, expected in case['cells'].items():
        for coordinate, value in expected.items():
            assert cells[sheet][coordinate] == value
    context = fresh_store
    ident = analyzed_files(context, [(path.name, content)])
    current = summary(context, ident)
    assert [sh['name'] for sh in current['sheets']] == case['sheets']
    assert all(not sh['ignored'] for sh in current['sheets'])
    assert not current['binding_refs'] and current['semantic_calls_used'] == 0
    for sheet in current['sheets']:
        fields = context[0][5].get('/api/v1/imports/' + ident + '/sheets/' + sheet['sheet_id'] + '/field-options')
        assert fields.status_code == 200, fields.text
    # This is a synthetic acceptance source scope, not a claim about the actual
    # business source, units, dates, loss, price/MOQ, identity or receipt semantics.
    for issue in listing(context, ident):
        if issue['issue_type'] == 'source_context':
            changed = mapping(context, ident, issue, {'resolution': dict(kind='source_context',
                source_system_key='I5-SUPPLIED-' + case['file'][:2], report_type='inspection',
                evidence_reference='I5 controlled test scope; original SHA256 ' + case['sha256'])})
            assert changed.status_code == 200, changed.text
    current = summary(context, ident)
    assert not current['can_preview'] and current['semantic_calls_used'] == 0
    assert all(not issue['ignored'] for issue in listing(context, ident))
    denied = []
    for profile in current['profile_proposals']:
        assert profile['missing_fields'] or profile['spec'] is None
        response = post(context, f'/stores/{context[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
            dict(decision='approve_activate', proposal_revision=profile['proposal_revision'],
                 expected_active_version=profile['active_version'], reason='I5 refuses undeclared source facts'),
            match=profile['lifecycle_revision'])
        assert response.status_code == 409 and response.json()['error']['code'] == 'UNRESOLVED_REQUIRED_FIELDS'
        denied.append(response.json()['error']['code'])
    read = context[0][5].get('/api/v1/imports/' + ident).json()['data']
    response = post(context, '/imports/' + ident + '/process', dict(phase='preview',
        mapping_revision=current['mapping_revision']), match=read['import_revision'])
    assert response.status_code == 409, response.text
    with Session(context[0][1]) as fresh:
        counts = {model.__tablename__: fresh.scalar(select(func.count()).select_from(model))
                  for model in (Product, Ingredient, SalesDaily, Recipe, InventoryLot, InventoryMovement, SupplierTerm, ImportHistoryRecord)}
        assert all(n == 0 for n in counts.values())
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
        batch = fresh.get(ImportBatch, UUID(ident))
        assert not batch.analysis_json.get('completion')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']
    save('original-' + case['file'][:2], dict(case=case, import_id=ident, status='PASS',
        actual='blocked_without_business_declarations; no rows/sheets ignored or committed',
        blockers=current['blockers'], missing_fields=[p['missing_fields'] for p in current['profile_proposals']],
        approval_errors=denied, preview_error=response.json()['error'], canonical_counts=counts))
