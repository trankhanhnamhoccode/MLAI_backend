"""I4 read-only guidance follows existing full-spec review and current rights."""
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, analyzed, sales_bytes, approved, previewed, post
from tests.integration.test_mapping_submissions import submit
from tests.integration.test_import_rule_review import summary, declare_context
from app.models import SalesDaily
from app.models.import_staging import ImportBatch


def test_guidance_separates_manual_semantics_from_full_spec_review_and_is_readonly(imp):
    ident = analyzed(imp, sales_bytes(imp).replace(b'sales.quantity', b'alien'))
    before = summary(imp, ident)
    guidance = before['completion_guidance']
    assert guidance['scope'] == 'batch'
    assert guidance['issue_denominator'] == before['counters']['batch']['total']
    assert {'classification', 'column_mapping', 'source_context'} <= {i['category'] for i in guidance['issues']}
    assert all(i['mapping_id'] for i in guidance['issues'])
    assert not guidance['profiles']  # Discovery has not fabricated a source-scoped profile.
    assert guidance['preview']['category'] == 'preview_validation'
    with Session(imp[0][1]) as fresh:
        batch = fresh.get(ImportBatch, UUID(ident))
        state = (batch.revision, batch.mapping_revision, batch.analysis_json)
    assert summary(imp, ident)['completion_guidance'] == guidance
    with Session(imp[0][1]) as fresh:
        batch = fresh.get(ImportBatch, UUID(ident))
        assert (batch.revision, batch.mapping_revision, batch.analysis_json) == state
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    declared = declare_context(imp, ident)
    assert not declared['completion_guidance']['profiles'][0]['review_ready']
    assert any(i['action'] == 'resolve_mapping' and i['category'] == 'column_mapping'
               for i in declared['completion_guidance']['issues'])


def test_exact_proposals_need_full_spec_review_without_per_column_resolution(imp):
    ident = analyzed(imp)
    current = declare_context(imp, ident)
    guidance = current['completion_guidance']
    assert guidance['profiles'][0]['review_ready']
    assert guidance['profiles'][0]['can_owner_review']
    assert all(i['action'] == 'review_full_spec' for i in guidance['issues'])
    assert not current['can_preview']


def test_preview_domain_errors_are_separate_and_guidance_does_not_change_counter_scope(imp):
    ident = analyzed(imp, sales_bytes(imp, quantity='-1'))
    approved(imp, ident)
    read = previewed(imp, ident)
    assert read['preview']['summary']['blockers']
    current = summary(imp, ident)
    guidance = current['completion_guidance']
    assert guidance['issues'] == []
    assert guidance['preview']['preview_id'] == read['preview']['summary']['preview_id']
    assert guidance['preview']['code'] == 'INSPECT_PREVIEW_ROW_DOMAIN_RESULTS'
    filtered = imp[0][5].get('/api/v1/imports/' + ident +
        '/mapping-summary?status=unmatched&include_clean_sheets=true').json()['data']
    assert filtered['counters']['filtered']['total'] == 0
    assert filtered['completion_guidance'] == guidance
    assert guidance['issue_denominator'] == filtered['counters']['batch']['total']


def test_stale_submission_guides_resubmit_and_retired_reuse_never_reviews_another_batch(imp):
    ident = analyzed(imp)
    declare_context(imp, ident)
    response, profile, _ = submit(imp, ident)
    row = response.json()['data']
    changed = declare_context(imp, ident, {'evidence_reference': 'Explicit corrected source evidence'})
    guide = changed['completion_guidance']['profiles'][0]
    assert guide['submission_state'] == 'stale' and guide['submission_id'] == row['submission_id']
    assert guide['can_submit']
    resubmitted, profile, _ = submit(imp, ident)
    assert resubmitted.status_code == 201, resubmitted.text
    result = post(imp, f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate', proposal_revision=profile['proposal_revision'],
             expected_active_version=None, reason='Review corrected evidence'), match=profile['lifecycle_revision'])
    assert result.status_code == 200, result.text
    approved_profile = result.json()['data']
    other = analyzed(imp)
    reused = declare_context(imp, other)
    assert reused['completion_guidance']['profiles'][0]['binding_usable']
    assert reused['completion_guidance']['profiles'][0]['allowed_actions'] == []
    retired = post(imp, f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='retire', active_version=approved_profile['active_version'], reason='Explicit retirement'),
        match=approved_profile['lifecycle_revision'])
    assert retired.status_code == 200, retired.text
    guide = summary(imp, other)['completion_guidance']['profiles'][0]
    assert not guide['binding_usable'] and not guide['can_owner_review'] and not guide['can_submit']
    assert guide['reason_codes'] == ['MAPPING_VERSION_RETIRED']
    assert guide['source_context_mapping_id']
    assert guide['allowed_actions'] == ['resolve_source_context']


def test_reused_profile_identifies_missing_batch_declaration_without_reapproval(imp):
    from tests.integration.test_import_field_value_bindings import review, shared, activate
    from tests.integration.test_import_classification import mapping
    from app.models.import_staging import ImportProfileVersion
    content = ('\n'.join(','.join(line.split(',')[:-1]) for line in sales_bytes(imp).decode().splitlines()) + '\n').encode()
    first = analyzed(imp, content)
    review(imp, first)
    assert shared(imp, first, 'sales.business_report_key', 'REPORT-1').status_code == 200
    activate(imp, first)
    ident = analyzed(imp, content)
    reused = declare_context(imp, ident, {'source_system_key': 'POS-A', 'report_type': 'DAILY'})
    assert not reused['can_preview']
    guide = reused['completion_guidance']
    assert guide['issues'] == []
    assert len(guide['declarations']) == 1
    task = guide['declarations'][0]
    assert task['category'] == 'conversion_business_declaration'
    assert task['target_field'] == 'sales.business_report_key' and task['can_act']
    assert guide['profiles'][0]['binding_usable'] and not guide['profiles'][0]['can_owner_review']
    response = mapping(imp, ident, {'mapping_id': task['mapping_id']}, {'resolution': dict(kind='shared_value',
        target_field=task['target_field'], scope='IMPORT_VALUE', value='REPORT-2', evidence_reference='Explicit current report')})
    assert response.status_code == 200, response.text
    assert not response.json()['data']['approval_required']
    updated = summary(imp, ident)
    assert updated['can_preview'] and updated['completion_guidance']['declarations'] == []
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_current_pending_submission_wins_over_tied_historical_order(imp, monkeypatch):
    from app.repositories.collaboration import CollaborationRepository
    from app.models.collaboration import MappingSubmissionRecord
    ident = analyzed(imp)
    declare_context(imp, ident)
    old, _, _ = submit(imp, ident)
    declare_context(imp, ident, {'evidence_reference': 'Clarified source before resubmission'})
    current, profile, _ = submit(imp, ident)
    assert current.status_code == 201, current.text
    old_id, current_id = old.json()['data']['submission_id'], current.json()['data']['submission_id']
    with Session(imp[0][1]) as fresh:
        assert fresh.get(MappingSubmissionRecord, UUID(old_id)).submitted_at == fresh.get(
            MappingSubmissionRecord, UUID(current_id)).submitted_at
    original = CollaborationRepository.submissions
    def historical_first(repo, *args):
        # Equal timestamps can put historical UUIDs first in the existing queue order.
        return sorted(original(repo, *args), key=lambda row: row.state == 'submitted')
    monkeypatch.setattr(CollaborationRepository, 'submissions', historical_first)
    guide = summary(imp, ident)['completion_guidance']['profiles'][0]
    assert guide['submission_id'] == current_id
    assert guide['submission_state'] == 'submitted' and not guide['can_submit']
    approved = post(imp, f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate', proposal_revision=profile['proposal_revision'],
             expected_active_version=None, reason='Review current tied task'), match=profile['lifecycle_revision'])
    assert approved.status_code == 200, approved.text
    guide = summary(imp, ident)['completion_guidance']['profiles'][0]
    assert guide['submission_id'] == current_id and guide['submission_state'] == 'approved'
