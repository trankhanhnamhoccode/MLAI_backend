"""I2 source-before-provider, explicit scope, replay and publication fences."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from app.models import SalesDaily, StoreMembership
from app.models.import_staging import ImportBatch, ImportJob, ImportProfileVersion, ImportProfile
from app.infrastructure import import_suggestions
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import analyzed, approved, post, sales_bytes, previewed
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_classification import listing, mapping
from tests.integration.import_semantic_helpers import request_semantics, semantic_imp as imp, base_imp


def ambiguous(imp):
    return analyzed(imp, sales_bytes(imp).replace(b'sales.quantity', b'alien'))


def test_discovery_and_source_reuse_never_call_provider(imp, monkeypatch):
    imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': True})
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('provider forbidden'))
    ident = ambiguous(imp)
    pending = summary(imp, ident)
    assert pending['semantic_suggestions'][0]['reason'] == 'SOURCE_CONTEXT_REQUIRED'
    assert not pending['binding_refs'] and not pending['can_preview']
    read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
    denied = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
        mapping_revision=pending['mapping_revision'], sheet_ids=[pending['sheets'][0]['sheet_id']]), match=read['import_revision'])
    assert denied.status_code == 409 and denied.json()['error']['code'] == 'SOURCE_CONTEXT_REQUIRED'
    first = analyzed(imp)
    version = approved(imp, first)
    second = analyzed(imp)
    reused = declare_context(imp, second, dict(source_system_key='POS-A', report_type='daily-sales'))
    assert reused['can_preview'] and reused['binding_refs'][0]['version'] == version['approved_version']
    assert reused['profile_proposals'] == []
    assert reused['semantic_suggestions'][0]['reason'] == 'APPROVED_BINDING_APPLIED'
    different = analyzed(imp)
    other = declare_context(imp, different, dict(source_system_key='OTHER', report_type='daily-sales'))
    assert not other['binding_refs']


def test_explicit_fallback_replay_outage_and_manual_completion(imp, monkeypatch):
    calls = []
    def unavailable(*args):
        assert imp[0][1].pool.checkedout() == 0
        calls.append(args[1].sheet_id)
        assert all(c['column_index'] == 2 for r in args[2]['rows'] for c in r['cells'])
        assert set(args[4]) == {'sheet_type', 'columns'}
        return None, 'LLM_UNAVAILABLE'
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', unavailable)
    ident = ambiguous(imp)
    assert not calls
    declared = declare_context(imp, ident, dict(source_system_key='POS-A', report_type='daily-sales'))
    assert declared['semantic_suggestions'][0]['eligible']
    before = listing(imp, ident)
    read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
    body = dict(phase='semantic_suggestions', mapping_revision=declared['mapping_revision'],
                sheet_ids=[declared['sheets'][0]['sheet_id']])
    key = str(uuid4())
    accepted = post(imp, '/imports/' + ident + '/process', body, key=key, match=read['import_revision'])
    assert accepted.status_code == 202, accepted.text
    assert summary(imp, ident)['active_job_id'] == accepted.json()['data']['job_id']
    assert summary(imp, ident)['semantic_suggestions'][0]['reason'] == 'JOB_PENDING'
    assert post(imp, '/imports/' + ident + '/process', body, key=key, match=read['import_revision']).json()['data'] == accepted.json()['data']
    imp[2].run_one()
    job = imp[0][5].get('/api/v1/jobs/' + accepted.json()['data']['job_id']).json()['data']
    assert job['result']['outcomes'][0]['status'] == 'unavailable' and len(calls) == 1
    replay = post(imp, '/imports/' + ident + '/process', body, key=key, match=read['import_revision'])
    assert replay.json()['data'] == accepted.json()['data'] and imp[2].run_one() is None and len(calls) == 1
    conflict = post(imp, '/imports/' + ident + '/process', {**body, 'sheet_ids': [str(uuid4())]}, key=key, match=read['import_revision'])
    assert conflict.status_code == 409
    after = listing(imp, ident)
    assert [(i['mapping_id'], i['target_field'], i['status']) for i in before] == [(i['mapping_id'], i['target_field'], i['status']) for i in after]
    unknown = next(i for i in after if i['source_header'] == 'alien')
    assert mapping(imp, ident, unknown, {'target_field': 'sales.quantity'}).status_code == 200
    approved(imp, ident)
    assert previewed(imp, ident)['preview']['rows'][0]['after']['quantity'] == '105'
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


@pytest.mark.parametrize('field', ['mapping_revision', 'analysis_id', 'source', 'binding', 'membership'])
@pytest.mark.parametrize('during_provider', [False, True])
def test_changed_inputs_and_authority_never_publish_partial_semantics(imp, monkeypatch, field, during_provider):
    imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': True})
    calls = []
    ident = ambiguous(imp)
    accepted = request_semantics(imp, ident, run=False)
    def mutate():
        with Session(imp[0][1]) as s:
            batch = s.get(ImportBatch, UUID(ident))
            if field == 'membership':
                s.scalar(select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id,
                    StoreMembership.user_id == batch.actor_id)).active = False
            elif field == 'analysis_id':
                batch.analysis_id = uuid4()
            elif field == 'mapping_revision':
                setattr(batch, field, 'synthetic-edit')
            else:
                data = dict(batch.analysis_json)
                if field == 'binding':
                    data['bindings'] = [{'sheet_id': data['sheets'][0]['sheet_id'], 'profile_id': str(uuid4()), 'version': 'changed', 'content_digest': 'changed'}]
                else:
                    data['issues'] = [{**i, 'resolution': {'resolution': {**i['resolution']['resolution'], 'source_system_key': 'OTHER'}}}
                                      if i['issue_type'] == 'source_context' else i for i in data['issues']]
                batch.analysis_json = data
            s.commit()
    def unavailable(*args):
        calls.append(1)
        if during_provider:
            mutate()
        return None, 'LLM_UNAVAILABLE'
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', unavailable)
    if not during_provider:
        mutate()
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        job = fresh.get(ImportJob, UUID(accepted['job_id']))
        batch = fresh.get(ImportBatch, UUID(ident))
        assert job.status == 'failed' and job.result_json is None
        assert job.error_json['code'] in {'SEMANTIC_INPUT_STALE', 'PERMISSION_DENIED'}
        assert len(calls) == int(during_provider)
        assert job.input_json['semantic_attempts'] == int(during_provider)
        assert not batch.analysis_json.get('warnings')
        assert next(i for i in batch.analysis_json['issues'] if i.get('source_header') == 'alien')['target_field'] is None
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_sealed_file_set_is_immutable_with_pending_semantic_job(imp, monkeypatch):
    ident = ambiguous(imp)
    accepted = request_semantics(imp, ident, run=False)
    with Session(imp[0][1]) as s:
        batch = s.get(ImportBatch, UUID(ident))
        original = batch.file_set_version
        batch.file_set_version = 'forbidden-edit'
        with pytest.raises(DBAPIError, match='sealed import source set'):
            s.commit()
        s.rollback()
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: (None, 'LLM_UNAVAILABLE'))
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportBatch, UUID(ident)).file_set_version == original
        assert fresh.get(ImportJob, UUID(accepted['job_id'])).status == 'completed'


@pytest.mark.parametrize('scope', [[], ['duplicate'], ['foreign']])
def test_invalid_scope_does_not_enqueue(imp, scope):
    ident = ambiguous(imp)
    declared = declare_context(imp, ident)
    sid = declared['sheets'][0]['sheet_id']
    ids = [] if not scope else [sid, sid] if scope == ['duplicate'] else [str(uuid4())]
    read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
    response = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
        mapping_revision=declared['mapping_revision'], sheet_ids=ids), match=read['import_revision'])
    assert response.status_code == 422
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportJob).where(ImportJob.operation == 'import_semantic_suggestions')) == 0


@pytest.mark.parametrize('action', ['approve', 'retire'])
@pytest.mark.parametrize('during_provider', [False, True])
def test_profile_lifecycle_changes_fence_before_call_and_publication(imp, monkeypatch, action, during_provider):
    first = analyzed(imp) if action == 'retire' else ambiguous(imp)
    if action == 'approve':
        alien = next(i for i in listing(imp, first) if i['source_header'] == 'alien')
        assert mapping(imp, first, alien, dict(target_field='sales.quantity')).status_code == 200
    else:
        original = approved(imp, first)
    ident = ambiguous(imp)
    accepted = request_semantics(imp, ident, run=False)
    calls = []
    def change_profile():
        if action == 'approve':
            approved(imp, first)
        else:
            with Session(imp[0][1]) as s:
                profile = s.get(ImportProfile, UUID(original['profile_id']))
                lifecycle = profile.lifecycle_revision
            response = post(imp, f"/stores/{imp[1].store_id}/mapping-profiles/{original['profile_id']}/decisions",
                dict(decision='retire', active_version=original['approved_version'], reason='Synthetic retirement'), match=lifecycle)
            assert response.status_code == 200, response.text
    def unavailable(*args):
        calls.append(1)
        if during_provider:
            change_profile()
        return None, 'LLM_UNAVAILABLE'
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', unavailable)
    if not during_provider:
        change_profile()
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        job = fresh.get(ImportJob, UUID(accepted['job_id']))
        assert job.status == 'failed' and job.error_json['code'] == 'SEMANTIC_INPUT_STALE'
        assert len(calls) == int(during_provider)
        assert job.result_json is None
    if action == 'approve':
        pending = summary(imp, ident)
        assert pending['semantic_suggestions'][0]['reason'] == 'RECHECK_SOURCE_REUSE'
        reused = declare_context(imp, ident, dict(source_system_key='POS-A', report_type='daily-sales'))
        assert reused['binding_refs'] and reused['profile_proposals'] == []


def test_multifile_sources_are_explicit_and_read_projection_does_not_bind(imp, monkeypatch):
    content = sales_bytes(imp).replace(b'sales.quantity', b'alien').replace(str(imp[4]).encode(), b'KNOWN-ALIAS')
    first = analyzed(imp, content)
    alien = next(i for i in listing(imp, first) if i['source_header'] == 'alien')
    assert mapping(imp, first, alien, dict(target_field='sales.quantity')).status_code == 200
    approved(imp, first, resolutions={'UNKNOWN_PRODUCT': dict(kind='identity_binding', canonical_id=str(imp[4]))})
    ident = post(imp, f'/stores/{imp[1].store_id}/imports', {'data_date': '2026-10-09'}).json()['data']['import_id']
    uploaded = imp[0][5].post('/api/v1/imports/' + ident + '/files',
        files=[('files[]', ('same.csv', content.replace(b'REPORT-1', f'REPORT-{n+1}'.encode()), 'text/csv')) for n in range(2)],
        data={'client_file_ids[]': [str(uuid4()), str(uuid4())]},
        headers={**imp[3], 'Idempotency-Key': str(uuid4())}).json()['data']
    response = post(imp, '/imports/' + ident + '/analyze', dict(file_set_version=uploaded['file_set_version'],
        accepted_file_ids=[f['file_id'] for f in uploaded['items']], acknowledged_rejected_client_file_ids=[]), match=uploaded['import_revision'])
    assert response.status_code == 202, response.text
    imp[2].run_one()
    source_issues = [i for i in listing(imp, ident) if i['issue_type'] == 'source_context']
    assert len(source_issues) == 2
    for issue, source in zip(source_issues, ('POS-A', 'POS-B')):
        changed = mapping(imp, ident, issue, dict(resolution=dict(kind='source_context', source_system_key=source,
            report_type='daily-sales', sales_semantics='daily_total', evidence_reference='Explicit separate source')))
        assert changed.status_code == 200, changed.text
    before = summary(imp, ident)
    assert len(before['binding_refs']) == 1
    eligible = [e['sheet_id'] for e in before['semantic_suggestions'] if e['eligible']]
    assert eligible == [source_issues[1]['sheet_id']]
    with Session(imp[0][1]) as s:
        digest = s.get(ImportBatch, UUID(ident)).mapping_revision
    for _ in range(2):
        assert summary(imp, ident)['binding_refs'] == before['binding_refs']
    with Session(imp[0][1]) as s:
        assert s.get(ImportBatch, UUID(ident)).mapping_revision == digest
    calls = []
    protected = [i for i in listing(imp, ident) if i['sheet_id'] == source_issues[0]['sheet_id']]
    assert not any(i['issue_type'] == 'identity' for i in protected)
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *args: (calls.append(str(args[1].sheet_id)) or (None, 'LLM_UNAVAILABLE')))
    request_semantics(imp, ident, eligible, declare=False)
    assert calls == eligible
    after = summary(imp, ident)
    assert after['binding_refs'] == before['binding_refs']
    assert [i for i in listing(imp, ident) if i['sheet_id'] == source_issues[0]['sheet_id']] == protected
    assert any(i['issue_type'] == 'identity' and i['source_header'] == 'KNOWN-ALIAS' and i['status'] == 'unmatched'
               for i in listing(imp, ident) if i['sheet_id'] == eligible[0])
    assert next(i for i in listing(imp, ident) if i['sheet_id'] == eligible[0] and i['issue_type'] == 'source_context')['resolution']['resolution']['source_system_key'] == 'POS-B'


def test_new_key_cannot_expand_analysis_budget(imp, monkeypatch):
    imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': True})
    calls = []
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *args: (calls.append(1) or (None, 'LLM_UNAVAILABLE')))
    ident = ambiguous(imp)
    for _ in range(2):
        request_semantics(imp, ident, declare=not calls)
    assert len(calls) == 2
    current = summary(imp, ident)
    assert current['semantic_calls_used'] == current['semantic_call_limit'] == 2
    assert current['semantic_suggestions'][0]['reason'] == 'LLM_CALL_LIMIT'
    read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
    response = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
        mapping_revision=current['mapping_revision'], sheet_ids=[current['sheets'][0]['sheet_id']]), match=read['import_revision'])
    assert response.status_code == 409 and response.json()['error']['code'] == 'LLM_CALL_LIMIT'
    # Accounting is a durable operational input, not a publication side effect.
    with Session(imp[0][1]) as s:
        jobs = s.scalars(select(ImportJob).where(ImportJob.import_id == UUID(ident),
            ImportJob.operation == 'import_semantic_suggestions')).all()
        assert len(jobs) == 2 and sum(j.input_json['semantic_attempts'] for j in jobs) == 2


def test_multiple_approved_candidates_cannot_be_selected_by_provider(imp, monkeypatch):
    first = analyzed(imp)
    original = approved(imp, first)
    with Session(imp[0][1]) as s:
        profile = s.get(ImportProfile, UUID(original['profile_id']))
        version = s.get(ImportProfileVersion, (profile.id, original['approved_version']))
        other_id = uuid4()
        s.add(ImportProfile(**{**{c.key: getattr(profile, c.key) for c in profile.__table__.columns}, 'id': other_id}))
        s.flush()
        s.add(ImportProfileVersion(**{**{c.key: getattr(version, c.key) for c in version.__table__.columns}, 'profile_id': other_id}))
        s.commit()
    imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': True})
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('ambiguous source cannot call provider'))
    ident = analyzed(imp)
    issue = next(i for i in listing(imp, ident) if i['issue_type'] == 'source_context')
    response = mapping(imp, ident, issue, dict(resolution=dict(kind='source_context', source_system_key='POS-A',
        report_type='daily-sales', evidence_reference='Ambiguous approved profiles')))
    assert response.status_code == 409 and response.json()['error']['code'] == 'PROFILE_MATCH_AMBIGUOUS'
    assert not summary(imp, ident)['binding_refs']


def test_manual_and_ignored_columns_are_not_samples_or_overwritten(imp, monkeypatch):
    from app.application.contracts.import_suggestions import SheetSuggestion
    content = sales_bytes(imp).replace(b'sales.quantity', b'alien').decode().splitlines()
    ident = analyzed(imp, (content[0] + ',manual,skip\n' + content[1] + ',false,PRIVATE-IGNORED\n').encode())
    manual = next(i for i in listing(imp, ident) if i['source_header'] == 'manual')
    ignored = next(i for i in listing(imp, ident) if i['source_header'] == 'skip')
    assert mapping(imp, ident, manual, dict(target_field='sales.is_stockout')).status_code == 200
    assert mapping(imp, ident, ignored, dict(resolution=dict(kind='ignored_optional_field', evidence_reference='Synthetic ignore'))).status_code == 200
    protected = {i['source_header']: i for i in listing(imp, ident) if i['source_header'] in {'manual', 'skip'}}
    def propose(settings, sheet, raw, filename, rule, selected, diagnostics):
        assert all(c['column_index'] == 2 for row in raw['rows'] for c in row['cells'])
        return SheetSuggestion.model_validate(dict(version='sheet_suggestion/1', sheet_type='sales', confidence=1.0,
            warnings=[], columns=[dict(source_column_index=c['source_column_index'],
                target_field='sales.quantity' if c['source_column_index'] == 2 else None,
                confidence=1.0) for c in rule['columns']])), None
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', propose)
    request_semantics(imp, ident)
    after = {i['source_header']: i for i in listing(imp, ident) if i['source_header'] in {'manual', 'skip'}}
    for header in protected:
        for key in ('target_field', 'status', 'resolution', 'resolved_by', 'ignored', 'suggestion_origin'):
            assert after[header][key] == protected[header][key]
    assert next(i for i in listing(imp, ident) if i['source_header'] == 'alien')['target_field'] == 'sales.quantity'
    assert not summary(imp, ident)['can_preview']


@pytest.mark.parametrize('headers', ['NCT,Tên hàng,SLN,ĐVT,Giá nhập',
                                    'Loại điều kiện,Áp dụng cho NL,Giá trị', 'Date,Weekend,Holiday'])
def test_source_declaration_does_not_make_known_unsupported_workflow_model_eligible(imp, monkeypatch, headers):
    imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': True})
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('known unsupported workflow'))
    ident = analyzed(imp, (headers + '\n' + ','.join(['x'] * len(headers.split(','))) + '\n').encode())
    current = declare_context(imp, ident)
    assert current['semantic_suggestions'][0]['reason'] == 'UNSUPPORTED_WORKFLOW'
    assert not current['binding_refs'] and not current['can_preview']
    read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
    rejected = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
        mapping_revision=current['mapping_revision'], sheet_ids=[current['sheets'][0]['sheet_id']]), match=read['import_revision'])
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'UNSUPPORTED_WORKFLOW'
