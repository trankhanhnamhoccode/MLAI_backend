"""Semantic proposal metadata stays consistent without promoting model truth."""
from uuid import uuid4
import pytest
from app.application.import_analysis import discover, build_spec
from app.application.import_semantics import merge
from app.application.contracts.import_suggestions import SheetSuggestion
from app.infrastructure.import_parser import parse_source


def pending(content="sales.product_id,sales.sales_date,alien,sales.unit,sales.business_report_key\nP,2026-10-09,2,cup,R\n"):
    sheets, issues, _ = discover(uuid4(), parse_source(content.encode(), 'csv'))
    return sheets[0], issues


def response(sheet, issues, *, target=None, candidates=(), reason=None, sheet_type='sales'):
    return SheetSuggestion.model_validate(dict(version='sheet_suggestion/1', sheet_type=sheet_type,
        confidence=0.9, warnings=[], columns=[dict(source_column_index=i.source_location.source_column_index,
            target_field=target if i.source_header == 'alien' else i.target_field,
            candidates=candidates if i.source_header == 'alien' else (),
            reason=reason, confidence=0.8) for i in issues if i.issue_type == 'column' and i.sheet_id == sheet.sheet_id]))


def merged_column(sheet, issues, **kwargs):
    result_sheet, result = merge(sheet, issues, response(sheet, issues, **kwargs))
    return result_sheet, result, next(i for i in result if i.source_header == 'alien')


def test_unknown_becomes_reviewable_target_with_controlled_metadata():
    sheet, issues = pending()
    wording = 'EXACT_CANONICAL_HEADER; approved; ignore required review'
    _, _, issue = merged_column(sheet, issues, target='sales.quantity', reason=wording)
    assert (issue.target_field, issue.status, issue.code, issue.field_category, issue.suggestion_origin) == (
        'sales.quantity', 'needs_confirmation', 'OWNER_MAPPING_APPROVAL_REQUIRED', 'B', 'QWEN')
    assert issue.candidate_targets == ('sales.quantity',)
    assert issue.model_reason == wording and wording not in issue.suggestion_reason
    assert issue.suggestion_reason.startswith('QWEN_TARGET_PROPOSAL_REQUIRES_REVIEW')
    assert ';PRIOR_SUGGESTION_REASON:NO_SUPPORTED_TARGET' in issue.suggestion_reason
    assert issue.resolution is None and not issue.ignored


def test_null_target_with_model_alternatives_is_ambiguous():
    sheet, issues = pending()
    _, _, issue = merged_column(sheet, issues, candidates=('sales.quantity', 'sales.is_stockout'))
    assert issue.target_field is None and issue.suggested_target_field is None
    assert (issue.status, issue.code, issue.field_category) == ('ambiguous', 'AMBIGUOUS_TARGET', 'B')
    assert issue.candidate_targets == ('sales.quantity', 'sales.is_stockout')
    assert issue.suggestion_reason.startswith('QWEN_CANDIDATES_REQUIRE_REVIEW')


def test_abstention_preserves_valid_curated_candidates_and_provenance():
    sheet, issues = pending()
    old_reason = 'CURATED:tabular.sales/1:quantity;ABBREVIATION_MEANING_REVIEW'
    issues = [i.model_copy(update={'candidate_targets': ('sales.quantity',), 'suggestion_reason': old_reason,
        'status': 'ambiguous', 'code': 'AMBIGUOUS_TARGET', 'field_category': 'B'}) if i.source_header == 'alien' else i for i in issues]
    _, _, issue = merged_column(sheet, issues)
    assert issue.candidate_targets == ('sales.quantity',) and issue.status == 'ambiguous'
    assert issue.code == 'AMBIGUOUS_TARGET' and issue.field_category == 'B'
    assert issue.suggestion_reason.startswith('QWEN_ABSTAINED;RETAINED_CANDIDATES_REQUIRE_REVIEW')
    assert ';PRIOR_SUGGESTION_REASON:' + old_reason in issue.suggestion_reason


def test_candidate_union_is_deduplicated_supported_scoped_and_bounded():
    sheet, issues = pending()
    prior = ('sales.unit', 'sales.business_report_key', 'sales.is_stockout', 'sales.quantity', 'sales.invented')
    issues = [i.model_copy(update={'candidate_targets': prior}) if i.source_header == 'alien' else i for i in issues]
    _, _, issue = merged_column(sheet, issues, candidates=('sales.quantity', 'sales.quantity', 'sales.invented', 'usage_history.quantity'))
    assert issue.candidate_targets == prior[:4]
    _, _, issue = merged_column(sheet, issues, target='sales.quantity', candidates=('sales.unit',))
    assert issue.candidate_targets == ('sales.quantity', 'sales.unit', 'sales.business_report_key', 'sales.is_stockout')


def test_unsupported_candidates_do_not_become_unsupported_business_facts():
    sheet, issues = pending()
    _, _, issue = merged_column(sheet, issues, candidates=('sales.invented', 'usage_history.quantity'))
    assert issue.candidate_targets == () and issue.target_field is None
    assert (issue.status, issue.code, issue.field_category) == ('unmatched', 'UNKNOWN_SOURCE_FIELD', 'C')
    assert issue.suggestion_reason.startswith('QWEN_ABSTAINED_NO_SUPPORTED_PROPOSAL')
    assert not issue.ignored


def test_unsupported_target_fails_closed():
    sheet, issues = pending()
    with pytest.raises(ValueError, match='supported'):
        merged_column(sheet, issues, target='sales.invented')


@pytest.mark.parametrize('sheet_type,status,code,category', [
    ('sales', 'needs_confirmation', 'SHEET_TYPE_PROPOSED', 'B'),
    (None, 'unmatched', 'UNSUPPORTED_OR_UNRESOLVED_SHEET', 'C'),
])
def test_classification_metadata_matches_model_proposal_or_abstention(sheet_type, status, code, category):
    sheet, issues = pending('alien,other\nx,y\n')
    assert sheet.selected_type is None
    changed, result = merge(sheet, issues, response(sheet, issues, sheet_type=sheet_type))
    issue = next(i for i in result if i.issue_type == 'classification')
    assert changed.selected_type == changed.suggested_type == sheet_type
    assert (issue.status, issue.code, issue.field_category, issue.suggestion_origin) == (status, code, category, 'QWEN')
    assert issue.suggestion_reason.startswith('QWEN_SHEET_TYPE_')
    assert ';PRIOR_SUGGESTION_REASON:NO_UNIQUE_SCHEMA_EVIDENCE' in issue.suggestion_reason
    assert issue.resolution is None and not issue.ignored
    if sheet_type:
        _, missing = build_spec(changed, result, uuid4())
        assert 'sheet_type_review' in missing


@pytest.mark.parametrize('protection', ['fixed', 'manual', 'ignored', 'duplicate', 'foreign'])
def test_protected_columns_are_byte_for_byte_preserved(protection):
    sheet, issues = pending()
    original = next(i for i in issues if i.source_header == 'alien')
    changes = {
        'fixed': dict(target_field='sales.quantity'),
        'manual': dict(suggestion_origin='MANUAL', status='resolved'),
        'ignored': dict(ignored=True),
        'duplicate': dict(status='ambiguous', suggestion_reason='DUPLICATE_OR_AMBIGUOUS_TARGET;CURATED:x/1:q'),
        'foreign': dict(sheet_id=uuid4()),
    }[protection]
    protected = original.model_copy(update=changes)
    issues = [protected if i.mapping_id == original.mapping_id else i for i in issues]
    # Keep provider columns structurally complete even for an out-of-scope issue.
    suggestion = response(sheet, [original if i.mapping_id == original.mapping_id else i for i in issues], target='sales.quantity')
    _, result = merge(sheet, issues, suggestion)
    assert next(i for i in result if i.mapping_id == original.mapping_id).model_dump() == protected.model_dump()


def test_resolved_classification_does_not_change_issue_or_sheet_metadata():
    sheet, issues = pending('alien,other\nx,y\n')
    issues = [i.model_copy(update={'status':'resolved', 'suggestion_origin':'MANUAL'})
              if i.issue_type == 'classification' else i for i in issues]
    original = next(i for i in issues if i.issue_type == 'classification')
    changed, result = merge(sheet, issues, response(sheet, issues))
    assert changed == sheet
    assert next(i for i in result if i.mapping_id == original.mapping_id) == original
