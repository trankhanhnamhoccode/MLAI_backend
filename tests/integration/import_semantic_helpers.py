"""Explicit source declaration and optional I05 invocation for synthetic tests."""
from uuid import uuid4
from tests.integration.test_import_staging import post
import pytest
from pydantic import SecretStr
from tests.integration.test_import_staging import imp as base_imp


@pytest.fixture
def semantic_imp(base_imp):
    """Fake-provider tests still need a valid effective gateway configuration."""
    base_imp[2].settings = base_imp[2].settings.model_copy(update={
        'import_llm_suggestions_enabled': True,
        'openrouter_api_key': SecretStr('SYNTHETIC-ONLY')})
    return base_imp


def request_semantics(imp, ident, sheet_ids=None, *, declare=True, run=True):
    client = imp[0][5]
    base = '/api/v1/imports/' + ident
    summary = client.get(base + '/mapping-summary?include_clean_sheets=true').json()['data']
    sheet_ids = sheet_ids if sheet_ids is not None else [s['sheet_id'] for s in summary['sheets']]
    if declare:
        items = client.get(base + '/mappings?review_only=false&limit=100').json()['data']['items']
        for issue in items:
            if issue['issue_type'] != 'source_context' or issue['sheet_id'] not in sheet_ids:
                continue
            summary = client.get(base + '/mapping-summary').json()['data']
            response = client.patch(base + '/mappings/' + issue['mapping_id'], json={'resolution': {
                'kind': 'source_context', 'source_system_key': 'POS-A', 'report_type': 'daily-sales',
                'sales_semantics': 'daily_total', 'evidence_reference': 'Synthetic per-sheet declaration'}},
                headers={**imp[3], 'Idempotency-Key': str(uuid4()), 'If-Match': '"' + summary['mapping_revision'] + '"'})
            assert response.status_code == 200, response.text
    summary = client.get(base + '/mapping-summary').json()['data']
    read = client.get(base).json()['data']
    response = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
        mapping_revision=summary['mapping_revision'], sheet_ids=sheet_ids), match=read['import_revision'])
    assert response.status_code == 202, response.text
    accepted = response.json()['data']
    if run:
        imp[2].run_one()
        job = client.get('/api/v1/jobs/' + accepted['job_id']).json()['data']
        assert job['status'] == 'completed', job
    return accepted
