"""I1 proposals versus source proof, immutable versions and current review guards."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import import_templates
from app.models import SalesDaily
from app.models.import_staging import ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, analyzed, approved, post
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_rule_review import summary, declare_context


def curated_sales(imp):
    return ("Ngày bán,Tên món,SL,sales.unit,sales.business_report_key\n"
            f"2026-10-09,{imp[4]},3,cup,REPORT-C\n").encode()


def test_curated_proposals_cannot_activate_or_preview_without_semantic_review(imp):
    ident = analyzed(imp, curated_sales(imp))
    before = summary(imp, ident)
    assert before["binding_refs"] == [] and not before["can_preview"]
    quantity = next(i for i in listing(imp, ident) if i["source_header"] == "SL")
    assert quantity["target_field"] == "sales.quantity"
    assert quantity["status"] == "needs_confirmation" and quantity["field_category"] == "B"
    assert "CURATED:tabular.sales/1:quantity" in quantity["suggestion_reason"]
    declared = declare_context(imp, ident)
    profile = declared["profile_proposals"][0]
    assert "column:2" in profile["missing_fields"]
    rejected = post(imp, f"/stores/{imp[1].store_id}/mapping-profiles/{profile['profile_id']}/decisions",
                    dict(decision="approve_activate", proposal_revision=profile["proposal_revision"],
                         expected_active_version=None, reason="Synthetic score does not authorize"),
                    match=profile["lifecycle_revision"])
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "UNRESOLVED_REQUIRED_FIELDS"
    read = imp[0][5].get("/api/v1/imports/" + ident).json()["data"]
    blocked = post(imp, "/imports/" + ident + "/process",
                   dict(phase="preview", mapping_revision=declared["mapping_revision"]),
                   match=read["import_revision"])
    assert blocked.status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_manual_classification_uses_same_contextual_columns_as_analyze(imp):
    ident = analyzed(imp, "Ngày sử dụng,Tên NL,SL,ĐVT\n2026-10-09,unbound,2,g\n".encode())
    first = listing(imp, ident)
    expected = {i["source_header"]: (i["target_field"], i["candidate_targets"], i["suggestion_reason"])
                for i in first if i["issue_type"] == "column"}
    classification = next(i for i in first if i["issue_type"] == "classification")
    for kind in ("sales", "usage_history"):
        changed = mapping(imp, ident, classification, dict(resolution=dict(
            kind="sheet_type", sheet_type=kind, reason="Synthetic manual classification")))
        assert changed.status_code == 200, changed.text
        if kind == "sales":
            assert next(i for i in listing(imp, ident) if i["source_header"] == "SL")["target_field"] is None
    actual = {i["source_header"]: (i["target_field"], i["candidate_targets"], i["suggestion_reason"])
              for i in listing(imp, ident) if i["issue_type"] == "column"}
    assert actual == expected
    current = summary(imp, ident)
    assert current["binding_refs"] == [] and not current["can_preview"]
    assert all(not p["spec"] or not p["spec"]["identity_rules"] for p in current["profile_proposals"])


def test_manual_classification_preserves_explicit_mapping_then_drops_incompatible_target(imp):
    ident = analyzed(imp, "Ngày sử dụng,Tên NL,SL,ĐVT\n2026-10-09,unbound,2,g\n".encode())
    quantity = next(i for i in listing(imp, ident) if i["source_header"] == "SL")
    # Deliberately differs from the curated quantity proposal.
    changed = mapping(imp, ident, quantity, dict(target_field="usage_history.evidence_reference"))
    assert changed.status_code == 200, changed.text
    explicit = next(i for i in listing(imp, ident) if i["source_header"] == "SL")
    classification = next(i for i in listing(imp, ident) if i["issue_type"] == "classification")
    for step, kind in enumerate(("usage_history", "sales", "usage_history")):
        changed = mapping(imp, ident, classification, dict(resolution=dict(
            kind="sheet_type", sheet_type=kind, reason="Synthetic explicit resolution boundary")))
        assert changed.status_code == 200, changed.text
        current = next(i for i in listing(imp, ident) if i["source_header"] == "SL")
        if step == 0:
            assert current["target_field"] == explicit["target_field"]
            assert current["status"] == "resolved"
            assert current["suggestion_origin"] == "MANUAL"
            assert current["resolved_by"] == explicit["resolved_by"]
        elif kind == "sales":
            assert current["target_field"] is None and current["status"] != "resolved"
            assert current["resolution"] is None and current["resolved_by"] is None
        else:
            assert current["target_field"] == "usage_history.quantity"
            assert current["status"] == "needs_confirmation" and current["resolution"] is None
            assert current["resolved_by"] is None
    assert not summary(imp, ident)["binding_refs"]


def test_template_version_changes_preserve_signature_and_source_scoped_reuse(imp, monkeypatch):
    content = curated_sales(imp)
    first = analyzed(imp, content)
    original = approved(imp, first)
    signature = summary(imp, first)["sheets"][0]["schema_signature"]
    monkeypatch.setattr(import_templates, "TEMPLATES", tuple(
        replace(t, version=2) for t in import_templates.TEMPLATES))
    second = analyzed(imp, content)
    pending = summary(imp, second)
    assert pending["sheets"][0]["schema_signature"] == signature
    assert not pending["binding_refs"]  # Same signature and system template still are not source proof.
    assert "tabular.sales/2:quantity" in next(
        i for i in listing(imp, second) if i["source_header"] == "SL")["suggestion_reason"]
    reused = declare_context(imp, second, dict(source_system_key="POS-A", report_type="daily-sales"))
    assert reused["binding_refs"][0]["version"] == original["approved_version"]
    third = analyzed(imp, content)
    different = declare_context(imp, third, dict(source_system_key="POS-OTHER", report_type="daily-sales"))
    assert not different["binding_refs"] and not different["can_preview"]
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportProfileVersion, (UUID(original["profile_id"]), original["approved_version"]))
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_provider_cannot_resolve_duplicate_with_curated_provenance(imp, monkeypatch):
    from pydantic import SecretStr
    from app.infrastructure import import_suggestions
    from app.application.contracts.import_suggestions import SheetSuggestion

    calls = []

    def propose(settings, sheet, raw, filename, rule, selected, diagnostics):
        calls.append(sheet.sheet_id)
        return SheetSuggestion.model_validate(dict(version="sheet_suggestion/1", sheet_type="usage_history",
            confidence=1.0, warnings=[], columns=[dict(source_column_index=c["source_column_index"],
                target_field="usage_history.quantity" if c["source_column_index"] == 2 else c["target_field"],
                confidence=1.0) for c in rule["columns"]])), None

    monkeypatch.setattr(import_suggestions, "suggest_sheet", propose)
    imp[2].settings = imp[2].settings.model_copy(update={
        "import_llm_suggestions_enabled": True, "openrouter_api_key": SecretStr("I5-SYNTHETIC-ONLY")})
    ident = analyzed(imp, "Ngày sử dụng,Tên NL,SL,Lượng thực dùng,ĐVT,alien\n2026-10-09,unbound,2,3,g,x\n".encode())
    from tests.integration.import_semantic_helpers import request_semantics
    request_semantics(imp, ident)
    duplicates = [i for i in listing(imp, ident) if i["source_header"] in {"SL", "Lượng thực dùng"}]
    assert len(calls) == 1 and len(duplicates) == 2
    assert all(i["target_field"] is None and i["status"] == "ambiguous" for i in duplicates)
    assert all(i["suggestion_reason"].startswith("DUPLICATE_OR_AMBIGUOUS_TARGET") for i in duplicates)
    assert "CURATED:tabular.usage/1:quantity" in duplicates[0]["suggestion_reason"]
