"""Real PostgreSQL/HTTP extension acceptance; synthetic input, guarded test DB only."""

from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import io
from zipfile import ZipFile
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_import_staging import (
    imp,
    post,
    analyzed,
    approved,
    previewed,
    sales_bytes,
)
from tests.integration.test_auth_public import env
from app.models import Product, SalesDaily, StoreMembership
from app.models.import_staging import (
    ImportBatch,
    ImportProfileVersion,
    ImportPreview,
    ImportAudit,
)
from app.infrastructure import import_suggestions


def mapping(imp, ident, issue, body):
    base = "/api/v1/imports/" + ident
    summary = (
        imp[0][5]
        .get(base + "/mapping-summary?include_profile_details=true")
        .json()["data"]
    )
    return imp[0][5].patch(
        base + "/mappings/" + issue["mapping_id"],
        json=body,
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + summary["mapping_revision"] + '"',
        },
    )


def listing(imp, ident):
    return (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "/mappings?review_only=false&limit=100")
        .json()["data"]["items"]
    )


def confirm(imp, ident, read, key=None):
    revision = (
        read.get("_mapping_revision")
        or imp[0][5]
        .get("/api/v1/imports/" + ident + "/mapping-summary")
        .json()["data"]["mapping_revision"]
    )
    read["_mapping_revision"] = revision
    return post(
        imp,
        "/imports/" + ident + "/process",
        dict(
            phase="confirm_review",
            preview_id=read["preview"]["summary"]["preview_id"],
            preview_digest=read["preview"]["summary"]["digest"],
            mapping_revision=revision,
            confirm=True,
            reason="Synthetic per-import review",
        ),
        key=key,
        match=read["import_revision"],
    )


def test_manual_correction_owner_profile_then_reuse_still_needs_own_confirmation(
    imp, monkeypatch
):
    content = sales_bytes(imp).replace(b"sales.quantity", b"POS custom quantity")
    ident = analyzed(imp, content)
    issue = next(
        i for i in listing(imp, ident) if i["source_header"] == "POS custom quantity"
    )
    changed = mapping(imp, ident, issue, {"target_field": "sales.quantity"})
    assert changed.status_code == 200, changed.text
    decision = approved(imp, ident)
    first = previewed(imp, ident)
    assert first["review_confirmation"] is None and not first["confirmation_usable"]
    key = str(uuid4())
    outcome = confirm(imp, ident, first, key)
    assert outcome.status_code == 200, outcome.text
    receipt = outcome.json()["data"]
    assert confirm(imp, ident, first, key).json()["data"] == receipt
    current = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]
    )
    assert current["confirmation_usable"]
    with Session(imp[0][1]) as fresh:
        profile = fresh.get(
            ImportProfileVersion,
            (UUID(decision["profile_id"]), decision["approved_version"]),
        )
        qty = next(
            f
            for f in profile.spec_json["field_bindings"]
            if f["target_field"] == "sales.quantity"
        )
        assert qty["origin"] == "MANUAL" and qty["confidence"] is None
        audits = fresh.scalars(
            select(ImportAudit).where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
        ).all()
        assert len(audits) == 1 and audits[0].record_json == receipt["confirmation"]
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
    # Analysis has no source proof yet; a custom header may reach the disabled
    # suggestion gateway. Reuse is only eligible after this upload's declaration.
    second = analyzed(imp, content)
    from tests.integration.test_import_rule_review import declare_context, summary as mapping_summary
    unselected = mapping_summary(imp, second)
    assert not unselected["binding_refs"] and not unselected["can_preview"]
    monkeypatch.setattr(
        import_suggestions,
        "suggest_sheet",
        lambda *a: (_ for _ in ()).throw(AssertionError("provider forbidden on reuse")),
    )
    declare_context(imp, second, {"source_system_key": "POS-A", "report_type": "daily-sales"})
    summary = (
        imp[0][5]
        .get("/api/v1/imports/" + second + "/mapping-summary?include_clean_sheets=true")
        .json()["data"]
    )
    assert (
        summary["can_preview"]
        and summary["sheets"][0]["classification_origin"] == "REUSED"
    )
    reused = listing(imp, second)
    assert all(i["suggestion_origin"] == "REUSED" for i in reused)
    preview = previewed(imp, second)
    assert preview["review_confirmation"] is None and not preview["confirmation_usable"]
    assert confirm(imp, second, preview).status_code == 200
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
            )
            == 2
        )
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_change_type_clears_targets_pins_and_confirmation_but_not_retained_evidence(
    imp,
):
    ident = analyzed(imp)
    decision = approved(imp, ident)
    read = previewed(imp, ident)
    assert confirm(imp, ident, read).status_code == 200
    classification = next(
        i for i in listing(imp, ident) if i["issue_type"] == "classification"
    )
    r = mapping(
        imp,
        ident,
        classification,
        {
            "resolution": {
                "kind": "sheet_type",
                "sheet_type": "ingredients",
                "reason": "Correct selected type",
            }
        },
    )
    assert r.status_code == 200, r.text
    summary = (
        imp[0][5]
        .get(
            "/api/v1/imports/" + ident + "/mapping-summary?include_profile_details=true"
        )
        .json()["data"]
    )
    assert summary["sheets"][0]["selected_type"] == "ingredients"
    assert not summary["can_preview"] and summary["binding_refs"] == []
    assert all(
        i["target_field"] is None
        for i in listing(imp, ident)
        if i["issue_type"] == "column"
    )
    after = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]
    )
    assert after["preview"]["stale"] and not after["confirmation_usable"]
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.get(
                ImportProfileVersion,
                (UUID(decision["profile_id"]), decision["approved_version"]),
            ).spec_json["schema"]
            == "sales"
        )
        assert (
            fresh.get(
                ImportPreview, UUID(read["preview"]["summary"]["preview_id"])
            ).digest
            == read["preview"]["summary"]["digest"]
        )
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
            )
            == 1
        )


def test_confirmation_stale_wrong_digest_and_current_revoke(imp):
    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    corrupt = {
        **read,
        "preview": {
            **read["preview"],
            "summary": {**read["preview"]["summary"], "digest": "sha256:" + "0" * 64},
        },
    }
    assert confirm(imp, ident, corrupt).status_code == 409
    assert confirm(imp, ident, read).status_code == 200
    with Session(imp[0][1]) as fresh:
        product = fresh.get(Product, imp[4])
        product.name = "Changed operational fact"
        fresh.commit()
    stale = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]
    )
    assert stale["preview"]["stale"] and not stale["confirmation_usable"]
    assert confirm(imp, ident, stale).status_code == 409
    with Session(imp[0][1]) as fresh:
        member = fresh.scalar(
            select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id)
        )
        member.active = False
        fresh.commit()
    revoked = confirm(imp, ident, stale)
    assert (
        revoked.status_code == 404
        and revoked.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    )


def test_qwen_runs_without_connection_and_invalid_provider_output_keeps_review(
    imp, monkeypatch
):
    from pydantic import SecretStr
    imp[2].settings = imp[2].settings.model_copy(update={
        'import_llm_suggestions_enabled': True, 'openrouter_api_key': SecretStr('SYNTHETIC-ONLY')})
    calls = []

    def unavailable(*args):
        assert imp[0][1].pool.checkedout() == 0
        calls.append(args)
        return None, "LLM_INVALID_OUTPUT"

    monkeypatch.setattr(import_suggestions, "suggest_sheet", unavailable)
    ident = analyzed(imp, sales_bytes(imp).replace(b"sales.quantity", b"alien header"))
    from tests.integration.import_semantic_helpers import request_semantics
    request_semantics(imp, ident)
    summary = (
        imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    )
    assert len(calls) == 1 and not summary["can_preview"]
    assert any(w["code"] == "LLM_INVALID_OUTPUT" for w in summary["warnings"])
    item = next(i for i in listing(imp, ident) if i["source_header"] == "alien header")
    assert (
        mapping(imp, ident, item, {"target_field": "sales.quantity"}).status_code == 200
    )
    approved(imp, ident)
    assert previewed(imp, ident)["preview"]["rows"][0]["after"]["quantity"] == "105"


def test_unsupported_sheet_requires_acknowledged_ignore(imp):
    ident = analyzed(imp, b"Unsupported fact,Alien\n42,x\n")
    classification = next(
        i for i in listing(imp, ident) if i["issue_type"] == "classification"
    )
    resolution = dict(
        kind="sheet_type",
        sheet_type=None,
        ignored=True,
        reason="Not in supported schemas",
    )
    assert (
        mapping(imp, ident, classification, {"resolution": resolution}).status_code
        == 422
    )
    resolution["acknowledgment"] = True
    result = mapping(imp, ident, classification, {"resolution": resolution})
    assert result.status_code == 200, result.text
    summary = (
        imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    )
    assert summary["sheets"][0]["ignored"] and not summary["can_preview"]
    assert any(n["code"] == "NO_DATA_ROWS" for n in summary["blockers"])


def test_multifile_multisheet_indexed_review_and_explicit_ignores(imp):
    from tests.unit.test_import_parser import workbook

    client = imp[0][5]
    created = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    ).json()["data"]
    ident = created["import_id"]
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    cells = '<row r="1"><c r="A1" t="inlineStr"><is><t>Duplicate</t></is></c><c r="B1" t="inlineStr"><is><t>Duplicate</t></is></c></row><row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2</v></c></row>'
    book = workbook(
        cells,
        extra={
            "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="" sheetId="1" r:id="r1"/><sheet name="sales" sheetId="2" r:id="r2"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>',
            "xl/worksheets/sheet2.xml": f'<worksheet xmlns="{ns}"><sheetData>{cells}</sheetData></worksheet>',
        },
    )
    csv = (
        sales_bytes(imp)
        .replace(b"business_report_key\n", b"business_report_key,Memo\n")
        .replace(b"REPORT-1\n", b"REPORT-1,unmapped note\n")
    )
    upload = client.post(
        "/api/v1/imports/" + ident + "/files",
        headers={**imp[3], "Idempotency-Key": str(uuid4())},
        files=[
            ("files[]", ("receipt.csv", csv, "text/csv")),
            (
                "files[]",
                (
                    "display.xlsx",
                    book,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
        data={"client_file_ids[]": [str(uuid4()), str(uuid4())]},
    )
    assert upload.status_code == 200, upload.text
    u = upload.json()["data"]
    job = post(
        imp,
        "/imports/" + ident + "/analyze",
        dict(
            file_set_version=u["file_set_version"],
            accepted_file_ids=[i["file_id"] for i in u["items"]],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=u["import_revision"],
    )
    assert job.status_code == 202 and imp[2].run_one() == UUID(
        job.json()["data"]["job_id"]
    )
    summary = client.get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    assert len(summary["sheets"]) == 3 and len(summary["files"]) == 2
    assert {sh["name"] for sh in summary["sheets"]} >= {"", "sales"}
    unsupported = [sh for sh in summary["sheets"] if sh["selected_type"] is None]
    assert len(unsupported) == 2
    for sh in unsupported:
        issues = [i for i in listing(imp, ident) if i["sheet_id"] == sh["sheet_id"]]
        columns = [i for i in issues if i["issue_type"] == "column"]
        assert [i["source_location"]["source_column_index"] for i in columns] == [0, 1]
        assert all(i["target_field"] is None and not i["ignored"] for i in columns)
        classification = next(i for i in issues if i["issue_type"] == "classification")
        assert (
            mapping(
                imp,
                ident,
                classification,
                {
                    "resolution": dict(
                        kind="sheet_type",
                        sheet_type=None,
                        ignored=True,
                        acknowledgment=True,
                        reason="Explicitly exclude unsupported sheet",
                    )
                },
            ).status_code
            == 200
        )
    memo = next(i for i in listing(imp, ident) if i["source_header"] == "Memo")
    r = mapping(
        imp,
        ident,
        memo,
        {
            "resolution": {
                "kind": "ignored_optional_field",
                "evidence_reference": "Optional memo explicitly ignored",
            }
        },
    )
    assert r.status_code == 200, r.text
    approved(imp, ident)
    read = previewed(imp, ident)
    assert len(read["preview"]["rows"]) == 1
    codes = [w["code"] for w in read["preview"]["summary"]["warnings"]]
    assert (
        codes.count("SHEET_EXPLICITLY_IGNORED") == 2
        and "COLUMN_EXPLICITLY_IGNORED" in codes
    )
    assert confirm(imp, ident, read).status_code == 200
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        retained = fresh.get(
            ImportPreview, UUID(read["preview"]["summary"]["preview_id"])
        )
        assert (
            sum(sh["ignored"] for sh in retained.content_json["reviewed_sheets"]) == 2
        )
        ignores = [
            i
            for i in retained.content_json["reviewed_mappings"]
            if i["issue_type"] == "classification" and i["ignored"]
        ]
        assert len(ignores) == 2 and all(
            i["resolution"]["resolution"]["acknowledgment"] for i in ignores
        )


def test_confirmation_concurrent_receipt_and_new_preview_requires_review_again(imp):
    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    read["_mapping_revision"] = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "/mapping-summary")
        .json()["data"]["mapping_revision"]
    )
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: confirm(imp, ident, read, key), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()["data"] == responses[1].json()["data"]
    next_preview = previewed(imp, ident)
    assert (
        next_preview["review_confirmation"] is None
        and not next_preview["confirmation_usable"]
    )
    assert (
        next_preview["preview"]["summary"]["preview_id"]
        != read["preview"]["summary"]["preview_id"]
    )
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
            )
            == 1
        )
        assert fresh.scalar(select(func.count()).select_from(ImportPreview)) == 2


def test_staff_confirmation_checks_current_write_scope_and_retry_without_owner_approval(
    imp,
):
    from app.models.auth import MembershipGrant
    from tests.integration.test_auth_public import setup, login, ORIGIN

    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    revision = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "/mapping-summary")
        .json()["data"]["mapping_revision"]
    )
    staff = setup(imp[0], email="review-staff@example.test", store=False)
    mid = uuid4()
    with Session(imp[0][1]) as fresh:
        fresh.add(
            StoreMembership(
                id=mid,
                store_id=imp[1].store_id,
                user_id=staff.user_id,
                role="STAFF",
                active=True,
            )
        )
        fresh.flush()
        for permission in (
            "import.read",
            "import.commit",
            "mapping.read",
            "menu.read",
            "sales.read",
            "sales.record",
        ):
            fresh.add(MembershipGrant(membership_id=mid, permission=permission))
        fresh.commit()
    session = login(imp[0], email="review-staff@example.test").json()["data"]
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": session["session"]["csrf_token"],
        "Idempotency-Key": str(uuid4()),
        "If-Match": '"' + read["import_revision"] + '"',
    }
    body = dict(
        phase="confirm_review",
        preview_id=read["preview"]["summary"]["preview_id"],
        preview_digest=read["preview"]["summary"]["digest"],
        mapping_revision=revision,
        confirm=True,
        reason="Staff with full write scope reviewed",
    )
    client = imp[0][5]
    accepted = client.post(
        "/api/v1/imports/" + ident + "/process", json=body, headers=headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["confirmation"]["confirmed_by"] == str(staff.user_id)
    with Session(imp[0][1]) as fresh:
        grant = fresh.get(MembershipGrant, (mid, "sales.record"))
        fresh.delete(grant)
        fresh.commit()
    now = client.get("/api/v1/imports/" + ident + "?include_preview=true")
    assert now.status_code == 200 and not now.json()["data"]["confirmation_usable"]
    assert "confirm_review" not in now.json()["data"]["allowed_actions"]
    denied = client.post(
        "/api/v1/imports/" + ident + "/process", json=body, headers=headers
    )
    assert (
        denied.status_code == 403
        and denied.json()["error"]["code"] == "PERMISSION_DENIED"
    )
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
            )
            == 1
        )
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_review_persistence_failure_rolls_back_confirmation_and_audit(imp, monkeypatch):
    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    original = imp[2]._audit

    def fail_after_staging(session, actor, store, kind, record):
        result = original(session, actor, store, kind, record)
        if kind == "IMPORT_REVIEW_CONFIRMED":
            session.flush()
            raise ValueError("Synthetic persistence failure after flush")
        return result

    monkeypatch.setattr(imp[2], "_audit", fail_after_staging)
    failed = confirm(imp, ident, read)
    assert failed.status_code == 503 and failed.json()["data"] is None
    assert failed.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    with Session(imp[0][1]) as fresh:
        batch = fresh.get(ImportBatch, UUID(ident))
        assert "confirmation" not in batch.analysis_json
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_REVIEW_CONFIRMED")
            )
            == 0
        )
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_valid_qwen_proposal_requires_human_type_and_mapping_review(imp, monkeypatch):
    import json
    from pydantic import SecretStr

    imp[2].settings = imp[2].settings.model_copy(
        update={"openrouter_api_key": SecretStr("SYNTHETIC-ONLY"), "import_llm_suggestions_enabled": True}
    )
    called = []

    class Transport:
        def open(self, request, timeout):
            assert imp[0][1].pool.checkedout() == 0
            payload = json.loads(json.loads(request.data)["messages"][1]["content"])
            called.append(payload)
            fields = [
                "sales.product_id",
                "sales.sales_date",
                "sales.quantity",
                "sales.unit",
                "sales.business_report_key",
            ]
            suggestion = dict(
                version="sheet_suggestion/1",
                sheet_type="sales",
                confidence=1,
                warnings=[],
                columns=[
                    dict(source_column_index=i, target_field=key, confidence=1)
                    for i, key in enumerate(fields)
                ],
            )
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": json.dumps(suggestion)},
                            }
                        ]
                    }
                ).encode()
            )

    monkeypatch.setattr(import_suggestions, "build_opener", lambda *a: Transport())
    ident = analyzed(imp, sales_bytes(imp).replace(b"sales.quantity", b"alien header"))
    from tests.integration.import_semantic_helpers import request_semantics
    request_semantics(imp, ident)
    summary = (
        imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    )
    # The model fills only the unknown column; it cannot replace deterministic type evidence.
    assert len(called) == 1 and summary["sheets"][0]["classification_origin"] == "RULE"
    assert summary["sheets"][0]["confidence"] == 0.8 and not summary["can_preview"]
    assert all(c['source_column_index'] == 2 for row in called[0]['sample_rows'] for c in row['cells'])
    quantity = next(
        i for i in listing(imp, ident) if i["source_header"] == "alien header"
    )
    assert (
        quantity["target_field"] == "sales.quantity"
        and quantity["suggestion_origin"] == "QWEN"
    )
    assert quantity["status"] == "needs_confirmation"
    approved(imp, ident)
    assert previewed(imp, ident)["preview"]["rows"][0]["after"]["quantity"] == "105"


def test_direct_reused_column_edit_forks_proposal_and_preserves_approved_context(imp):
    first = analyzed(imp)
    old = approved(imp, first)
    ident = analyzed(imp)
    from tests.integration.test_import_rule_review import declare_context, summary as mapping_summary
    unselected = mapping_summary(imp, ident)
    assert not unselected["binding_refs"] and not unselected["can_preview"]
    declare_context(imp, ident, {"source_system_key": "POS-A", "report_type": "daily-sales"})
    read = previewed(imp, ident)
    assert confirm(imp, ident, read).status_code == 200
    quantity = next(
        i for i in listing(imp, ident) if i["target_field"] == "sales.quantity"
    )
    changed = mapping(
        imp,
        ident,
        quantity,
        {
            "resolution": {
                "kind": "ignored_optional_field",
                "evidence_reference": "Explicit temporary unmap for review",
            }
        },
    )
    assert changed.status_code == 200, changed.text
    summary = (
        imp[0][5]
        .get(
            "/api/v1/imports/" + ident + "/mapping-summary?include_profile_details=true"
        )
        .json()["data"]
    )
    proposal = summary["profile_proposals"][0]
    assert not summary["can_preview"] and "sales.quantity" in proposal["missing_fields"]
    assert "source_context" not in proposal["missing_fields"]
    assert (
        mapping(imp, ident, quantity, {"target_field": "sales.quantity"}).status_code
        == 200
    )
    summary = (
        imp[0][5]
        .get(
            "/api/v1/imports/" + ident + "/mapping-summary?include_profile_details=true"
        )
        .json()["data"]
    )
    proposal = summary["profile_proposals"][0]
    assert (
        proposal["missing_fields"] == []
        and proposal["spec"]["scope"]["source_system_key"] == "POS-A"
    )
    assert proposal["active_version"] is None and not summary["can_preview"]
    stale = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]
    )
    assert stale["preview"]["stale"] and not stale["confirmation_usable"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        original = fresh.get(
            ImportProfileVersion, (UUID(old["profile_id"]), old["approved_version"])
        )
        assert (
            next(
                f
                for f in original.spec_json["field_bindings"]
                if f["source_column_index"] == 2
            )["target_field"]
            == "sales.quantity"
        )


def test_approved_memory_does_not_cross_store_or_auto_accept_structure_drift(imp):
    from tests.integration.test_auth_public import provision

    ident = analyzed(imp)
    approved(imp, ident)
    other = provision(imp[0], existing=imp[1].user_id)
    product = uuid4()
    with Session(imp[0][1]) as fresh:
        fresh.add(
            Product(
                id=product,
                store_id=other.store_id,
                name="Other Store synthetic",
                selling_unit="cup",
                active=True,
            )
        )
        fresh.commit()
    other_fixture = (imp[0], other, imp[2], imp[3], product)
    other_import = analyzed(other_fixture)
    summary = (
        imp[0][5]
        .get(
            "/api/v1/imports/"
            + other_import
            + "/mapping-summary?include_clean_sheets=true"
        )
        .json()["data"]
    )
    assert summary["binding_refs"] == [] and not summary["can_preview"]
    assert all(i["suggestion_origin"] != "REUSED" for i in listing(imp, other_import))
    changed = (
        sales_bytes(imp)
        .replace(b"business_report_key\n", b"business_report_key,New column\n")
        .replace(b"REPORT-1\n", b"REPORT-1,extra\n")
    )
    drift = analyzed(imp, changed)
    summary = (
        imp[0][5]
        .get("/api/v1/imports/" + drift + "/mapping-summary?include_clean_sheets=true")
        .json()["data"]
    )
    assert summary["binding_refs"] == [] and not summary["can_preview"]
    assert any(
        i["source_header"] == "New column" and not i["ignored"]
        for i in listing(imp, drift)
    )
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
