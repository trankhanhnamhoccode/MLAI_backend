"""Source declarations gate reuse; row identity and retirement remain independent."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, analyzed, approved, post, sales_bytes
from tests.integration.test_import_rule_review import declare_context, summary
from tests.integration.test_import_classification import listing, mapping
from tests.integration.test_import_commit import ready, commit
from app.models import Product, SalesDaily
from app.models.import_staging import ImportProfileVersion, ImportProfile, ImportBatch


@pytest.mark.parametrize("canonical", [True, False])
def test_same_headers_new_entity_does_not_imply_profile_change(imp, canonical):
    first = analyzed(imp)
    decision = approved(imp, first)
    pid = uuid4()
    with Session(imp[0][1]) as session:
        session.add(Product(id=pid, store_id=imp[1].store_id, name="Synthetic new item",
            selling_unit="cup", active=True))
        session.commit()
    token = str(pid) if canonical else "NEW-ITEM"
    content = sales_bytes(imp).replace(str(imp[4]).encode(), token.encode())
    second = analyzed(imp, content)
    before = summary(imp, second)
    assert before["binding_refs"] == [] and not before["can_preview"]
    if canonical:
        classification = next(i for i in listing(imp, second) if i["issue_type"] == "classification")
        reviewed = mapping(imp, second, classification, dict(resolution=dict(kind="sheet_type",
            sheet_type="sales", reason="Synthetic compatible classification before source")))
        assert reviewed.status_code == 200
    resolved = declare_context(imp, second, dict(source_system_key="POS-A", report_type="daily-sales"))
    assert resolved["binding_refs"][0]["version"] == decision["approved_version"]
    assert resolved["profile_proposals"] == []
    assert resolved["can_preview"] == canonical
    if not canonical:
        unknown = next(i for i in listing(imp, second) if i["issue_type"] == "identity")
        assert unknown["source_header"] == token and unknown["status"] == "unmatched"
        response = mapping(imp, second, unknown, dict(resolution=dict(kind="identity_binding", canonical_id=str(pid))))
        assert response.status_code == 200 and response.json()["data"]["approval_required"]
        changed = summary(imp, second)
        assert not changed["can_preview"]  # An added reusable alias really changes spec.
        assert changed["profile_proposals"][0]["spec"]["source_provenance"]["evidence_references"][0] == "Synthetic explicit source"
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_retirement_after_acceptance_blocks_worker_and_fresh_reuse(imp):
    ident, read, revision = ready(imp)
    accepted = commit(imp, ident, read, revision)
    assert accepted.status_code == 202
    ref = read["preview"]["summary"]["mapping_bindings"][0]
    with Session(imp[0][1]) as session:
        profile = session.get(ImportProfile, UUID(ref["profile_id"]))
        lifecycle, active = profile.lifecycle_revision, profile.active_version
    retired = post(imp, f"/stores/{imp[1].store_id}/mapping-profiles/{ref['profile_id']}/decisions",
        dict(decision="retire", active_version=active, reason="Synthetic policy test"), match=lifecycle)
    assert retired.status_code == 200
    jid = accepted.json()["data"]["job_id"]
    assert imp[2].run_one() == UUID(jid)
    job = imp[0][5].get("/api/v1/jobs/" + jid).json()["data"]
    assert job["status"] == "failed" and job["error"]["code"] == "MAPPING_VERSION_RETIRED"
    second = analyzed(imp)
    resolved = declare_context(imp, second, dict(source_system_key="POS-A", report_type="daily-sales"))
    assert not resolved["can_preview"] and not resolved["binding_refs"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_pending_signature_only_pin_has_no_source_authority(imp):
    ident, read, revision = ready(imp)
    # Reproduce the prior analyze artifact: approved pin, no batch source proof.
    with Session(imp[0][1]) as session:
        batch = session.get(ImportBatch, UUID(ident))
        analysis = dict(batch.analysis_json)
        analysis["issues"] = [{**i, "resolution": None, "resolved_by": None}
            if i["issue_type"] == "source_context" else i for i in analysis["issues"]]
        batch.analysis_json = analysis
        session.commit()
    current = summary(imp, ident)
    assert not current["can_preview"]
    assert "SOURCE_CONTEXT_REQUIRED" in {n["code"] for n in current["blockers"]}
    rejected = commit(imp, ident, read, revision)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "SOURCE_CONTEXT_REQUIRED"
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
