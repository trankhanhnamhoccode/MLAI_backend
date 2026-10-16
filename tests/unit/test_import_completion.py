"""Completion issue references classify work, not business truth or click counts."""
from uuid import uuid4
from app.application.contracts import import_mapping as dto
from app.application.import_completion import issue_guidance


def test_distinct_work_kinds_and_null_semantics_are_preserved():
    sid, fid = uuid4(), uuid4()
    sheet = dto.SheetInfo(sheet_id=sid, file_id=fid, profile_id=None, name='source',
                          schema_signature='test', row_count=1, headers=('unknown',))
    issues = [dto.MappingIssue(mapping_id=uuid4(), sheet_id=sid, issue_type=kind,
        code='NEEDS_REVIEW', status='unmatched', source_location=dto.SourceLocation(file_id=fid, sheet_id=sid),
        resolution_origin='UNRESOLVED', target_field=None, suggested_ignore=True)
        for kind in ('classification', 'column', 'source_context', 'identity', 'conversion', 'schema_blocker')]
    result = issue_guidance([*issues, issues[1]], [sheet], [], can_resolve=False)
    assert len(result) == 6  # One entry per issue ID, never per code/possible action.
    assert [i.category for i in result] == ['classification', 'column_mapping', 'source_context',
        'entity_resolution', 'conversion_business_declaration', 'conversion_business_declaration']
    assert all(i.action == 'resolve_mapping' and not i.can_act for i in result)
    ignored = issues[1].model_copy(update={'ignored': True})
    assert issue_guidance([ignored], [sheet], [], can_resolve=True) == ()
