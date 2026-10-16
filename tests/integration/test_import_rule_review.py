"""Full-spec Owner approval, immutable reuse and drift with fresh DB evidence."""

from uuid import uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SalesDaily
from app.models.import_staging import ImportProfileVersion
from tests.integration.test_import_staging import imp, env, analyzed, post, sales_bytes


def summary(imp, ident):
    response = imp[0][5].get('/api/v1/imports/' + ident + '/mapping-summary?include_profile_details=true&include_clean_sheets=true')
    assert response.status_code == 200, response.text
    return response.json()['data']


def declare_context(imp, ident, context=None):
    base = '/api/v1/imports/' + ident
    items = imp[0][5].get(base + '/mappings?review_only=false&limit=100').json()['data']['items']
    context_issue = next(i for i in items if i['issue_type'] == 'source_context')
    revision = summary(imp, ident)['mapping_revision']
    response = imp[0][5].patch(base + '/mappings/' + context_issue['mapping_id'], json={
        'resolution': {'kind': 'source_context', 'source_system_key': 'POS-GROUP',
                       'report_type': 'daily-sales', 'evidence_reference': 'Synthetic explicit source',
                       'sales_semantics': 'daily_total', **(context or {})},
    }, headers={**imp[3], 'Idempotency-Key': str(uuid4()), 'If-Match': '"' + revision + '"'})
    assert response.status_code == 200, response.text
    return summary(imp, ident)


def test_owner_reviews_group_reuses_without_provider_and_detects_drift(imp, monkeypatch):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet',
                        lambda *a: (_ for _ in ()).throw(AssertionError('provider forbidden')))
    first = analyzed(imp)
    proposed = declare_context(imp, first)
    profile = proposed['profile_proposals'][0]
    assert profile['missing_fields'] == [] and profile['spec'] is not None
    assert not proposed['can_preview']
    assert proposed['progress']['unresolved'] > 0  # proposal is not approval
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
    response = post(imp, '/stores/' + str(imp[1].store_id) + '/mapping-profiles/' + profile['profile_id'] + '/decisions', {
        'decision': 'approve_activate', 'proposal_revision': profile['proposal_revision'],
        'expected_active_version': None, 'reason': 'Synthetic full sheet review',
    }, match=profile['lifecycle_revision'])
    assert response.status_code == 200, response.text
    approved = response.json()['data']['approved_version']
    reviewed = summary(imp, first)
    assert reviewed['can_preview'] and reviewed['progress']['unresolved'] == 0
    second = analyzed(imp)
    unselected = summary(imp, second)
    assert not unselected['can_preview'] and unselected['binding_refs'] == []
    reused = declare_context(imp, second)
    assert reused['can_preview']
    assert reused['sheets'][0]['classification_origin'] == 'REUSED'
    with Session(imp[0][1]) as s:
        versions = s.scalars(select(ImportProfileVersion)).all()
        assert len(versions) == 1 and versions[0].version == approved
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0
    # Extra unlabelled source data is structural drift, never silently discarded.
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: (None, 'LLM_UNAVAILABLE'))
    content = sales_bytes(imp).decode().splitlines()
    changed = analyzed(imp, (content[0] + ',new business field\n' + content[1] + ',review me\n').encode())
    drift = declare_context(imp, changed)
    assert not drift['can_preview']
    assert 'PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT' in {w['code'] for w in drift['warnings']}
    assert drift['profile_proposals'][0]['missing_fields']
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_optional_model_sheet_budget_keeps_manual_flow(imp, monkeypatch):
    from app.infrastructure import import_suggestions
    from pydantic import SecretStr
    imp[2].settings = imp[2].settings.model_copy(update={
        'import_llm_suggestions_enabled': True, 'openrouter_api_key': SecretStr('SYNTHETIC-ONLY')})
    called = []

    def unavailable(*args):
        called.append(args[1].sheet_id)
        assert imp[0][1].pool.checkedout() == 0
        return None, 'LLM_UNAVAILABLE'

    monkeypatch.setattr(import_suggestions, 'suggest_sheet', unavailable)
    batch = post(imp, '/stores/' + str(imp[1].store_id) + '/imports', {'data_date': '2026-10-09'}).json()['data']
    ident = batch['import_id']
    files = [('files[]', (str(i) + '.csv', ('unknown,date,qty\nrow-' + str(i) + ',x,1\n').encode(), 'text/csv')) for i in range(3)]
    upload = imp[0][5].post('/api/v1/imports/' + ident + '/files',
        files=files, data={'client_file_ids[]': [str(uuid4()) for _ in files]},
        headers={**imp[3], 'Idempotency-Key': str(uuid4())})
    assert upload.status_code == 200, upload.text
    accepted = upload.json()['data']
    job = post(imp, '/imports/' + ident + '/analyze', {
        'file_set_version': accepted['file_set_version'],
        'accepted_file_ids': [f['file_id'] for f in accepted['items']],
        'acknowledged_rejected_client_file_ids': [],
    }, match=accepted['import_revision'])
    assert job.status_code == 202, job.text
    imp[2].run_one()
    assert called == []
    from tests.integration.import_semantic_helpers import request_semantics
    request_semantics(imp, ident)
    result = summary(imp, ident)
    assert len(called) == 2 and len(result['sheets']) == 3
    assert 'LLM_CALL_LIMIT' in {w['code'] for w in result['warnings']}
    assert not result['can_preview']
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
