"""Read-only manual completion and existing MQ01 readiness, without persistence."""
from collections.abc import Sequence
from uuid import UUID
from app.application.contracts import import_mapping as dto


def review_blockers(*, sealed: bool, analyzed: bool, job_active: bool, completed: bool,
                    spec: dto.ProfileSpec | None, missing: Sequence[str],
                    issues: Sequence[dto.MappingIssue]) -> tuple[str, ...]:
    """Exactly the existing MQ01 policy; build_spec remains its semantic gate."""
    blockers = []
    if not sealed or not analyzed:
        blockers.append('IMPORT_NOT_ANALYZED')
    if job_active:
        blockers.append('IMPORT_JOB_ACTIVE')
    if completed:
        blockers.append('IMPORT_ALREADY_COMMITTED')
    if missing or spec is None:
        blockers.append('UNRESOLVED_REQUIRED_FIELDS')
    if blockers:
        return tuple(blockers)
    for issue in issues:
        resolved = issue.status in ('resolved', 'auto_mapped')
        candidate = (issue.status == 'needs_confirmation' and issue.suggestion_origin == 'RULE'
                     and issue.issue_type in ('column', 'classification')
                     and issue.source_location is not None)
        if not resolved and not candidate:
            blockers.append(issue.code)
        if issue.issue_type == 'source_context' and not issue.resolved_by:
            blockers.append('SOURCE_CONTEXT_REQUIRED')
    if spec is not None and not spec.source_provenance.evidence_references:
        blockers.append('SOURCE_CONTEXT_REQUIRED')
    return tuple(sorted(set(blockers)))


def issue_guidance(issues: Sequence[dto.MappingIssue], sheets: Sequence[dto.SheetInfo],
                   profiles: Sequence[dto.CompletionProfileGuidance], *,
                   can_resolve: bool) -> tuple[dto.CompletionIssueGuidance, ...]:
    categories = {'classification': 'classification', 'column': 'column_mapping',
                  'source_context': 'source_context', 'identity': 'entity_resolution',
                  'conversion': 'conversion_business_declaration',
                  'schema_blocker': 'conversion_business_declaration'}
    by_sheet = {p.sheet_id: p for p in profiles}
    sheet_ids = {sh.sheet_id: sh.profile_id for sh in sheets if not sh.ignored}
    result = []
    seen: set[UUID] = set()
    for issue in issues:
        if (issue.mapping_id in seen or issue.sheet_id not in sheet_ids or issue.ignored
                or issue.status in {'resolved', 'auto_mapped'}):
            continue
        seen.add(issue.mapping_id)
        profile = by_sheet.get(issue.sheet_id)
        grouped = bool(profile and profile.review_ready and issue.suggestion_origin == 'RULE'
                       and issue.status == 'needs_confirmation'
                       and issue.issue_type in {'column', 'classification'})
        result.append(dto.CompletionIssueGuidance(mapping_id=issue.mapping_id,
            sheet_id=issue.sheet_id, profile_id=sheet_ids[issue.sheet_id],
            category=categories[issue.issue_type], code=issue.code,
            action='review_full_spec' if grouped else 'resolve_mapping',
            can_act=bool(profile.can_owner_review) if grouped else can_resolve))
    return tuple(result)
