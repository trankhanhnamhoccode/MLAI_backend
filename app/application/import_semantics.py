"""Detached semantic proposals; explicit resolutions and duplicates stay protected."""
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_suggestions import SheetSuggestion
from app.application.import_descriptors import options


def eligible_column(issue: dto.MappingIssue) -> bool:
    return (issue.issue_type == "column" and not issue.ignored
            and issue.status not in {"resolved", "auto_mapped"} and issue.resolution is None
            and issue.target_field is None
            and not (issue.suggestion_reason or "").startswith("DUPLICATE_OR_AMBIGUOUS_TARGET"))


def _reason(current: str, prior: str | None) -> str:
    return current + (";PRIOR_SUGGESTION_REASON:" + prior if prior else "")


def merge(sheet: dto.SheetInfo, issues: list[dto.MappingIssue], suggestion: SheetSuggestion
          ) -> tuple[dto.SheetInfo, list[dto.MappingIssue]]:
    """Provider outputs remain human-review proposals, never reusable bindings."""
    if sheet.ignored:
        return sheet, list(issues)
    if sheet.selected_type is not None and suggestion.sheet_type != sheet.selected_type:
        raise ValueError("Suggestion cannot replace supported selected schema")
    supported = {o.key for o in options(suggestion.sheet_type) if o.available}
    proposals = {c.source_column_index: c for c in suggestion.columns}
    changed = []
    classified = False
    for issue in issues:
        if issue.sheet_id != sheet.sheet_id:
            changed.append(issue)
            continue
        if eligible_column(issue) and issue.suggestion_origin not in {"MANUAL", "REUSED"}:
            proposal = proposals[issue.source_location.source_column_index]
            target = proposal.target_field
            if target is not None and target not in supported:
                raise ValueError("Suggestion target must be supported in selected schema")
            model_candidates = tuple(c for c in proposal.candidates if c in supported)
            candidates = tuple(dict.fromkeys(
                ((target,) if target else ())
                + tuple(c for c in issue.candidate_targets if c in supported)
                + model_candidates))[:4]
            if target:
                status, code, category = "needs_confirmation", "OWNER_MAPPING_APPROVAL_REQUIRED", "B"
                reason = "QWEN_TARGET_PROPOSAL_REQUIRES_REVIEW"
            elif candidates:
                status, code, category = "ambiguous", "AMBIGUOUS_TARGET", "B"
                reason = ("QWEN_CANDIDATES_REQUIRE_REVIEW" if model_candidates else
                          "QWEN_ABSTAINED;RETAINED_CANDIDATES_REQUIRE_REVIEW")
            else:
                status, code, category = "unmatched", "UNKNOWN_SOURCE_FIELD", "C"
                reason = "QWEN_ABSTAINED_NO_SUPPORTED_PROPOSAL"
            issue = issue.model_copy(update={
                "target_field": target,
                "suggested_target_field": target,
                "candidate_targets": candidates,
                "model_reason": proposal.reason,
                "suggestion_origin": "QWEN", "confidence": proposal.confidence,
                "status": status, "code": code, "field_category": category,
                "suggestion_reason": _reason(reason, issue.suggestion_reason),
            })
        elif (issue.issue_type == "classification" and sheet.selected_type is None
              and not issue.ignored and issue.suggestion_origin not in {"MANUAL", "REUSED"}
              and issue.status not in {"resolved", "auto_mapped"} and issue.resolution is None):
            classified = True
            proposed = suggestion.sheet_type is not None
            issue = issue.model_copy(update={"suggestion_origin": "QWEN",
                "confidence": suggestion.confidence,
                "status": "needs_confirmation" if proposed else "unmatched",
                "code": "SHEET_TYPE_PROPOSED" if proposed else "UNSUPPORTED_OR_UNRESOLVED_SHEET",
                "field_category": "B" if proposed else "C",
                "suggestion_reason": _reason("QWEN_SHEET_TYPE_PROPOSAL_REQUIRES_REVIEW" if proposed
                    else "QWEN_SHEET_TYPE_ABSTAINED", issue.suggestion_reason)})
        changed.append(issue)
    if classified:
        sheet = sheet.model_copy(update={"selected_type": suggestion.sheet_type,
            "suggested_type": suggestion.sheet_type, "classification_origin": "QWEN",
            "confidence": suggestion.confidence})
    return sheet, changed
