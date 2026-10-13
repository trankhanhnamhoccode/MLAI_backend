"""Real guarded PostgreSQL and HTTP, synthetic sources only."""

import csv
import io
from uuid import uuid4, UUID
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.application.use_cases.import_staging import ImportStaging
from app.application.contracts import import_mapping as dto
from app.models import Product, SalesDaily, StoreMembership
from app.models.import_staging import (
    ImportBatch,
    ImportFile,
    ImportProfileVersion,
    ImportPreview,
    ImportJob,
    ImportReceipt,
    ImportAudit,
)
from tests.integration.test_auth_public import env, setup, login, ORIGIN, provision


@pytest.fixture
def imp(env):
    receipt = setup(env)
    wire = login(env).json()["data"]
    client = env[5]
    service = ImportStaging(env[2], env[0])
    client.app.state.import_staging = service
    headers = {"Origin": ORIGIN, "X-CSRF-Token": wire["session"]["csrf_token"]}
    pid = uuid4()
    with Session(env[1]) as s:
        s.add(
            Product(
                id=pid,
                store_id=receipt.store_id,
                name="Synthetic coffee",
                selling_unit="cup",
                active=True,
            )
        )
        s.commit()
    return env, receipt, service, headers, pid


def post(imp, path, body, *, match=None, key=None):
    headers = {**imp[3], "Idempotency-Key": key or str(uuid4())}
    if match:
        headers["If-Match"] = '"' + match + '"'
    return imp[0][5].post("/api/v1" + path, json=body, headers=headers)


def sales_bytes(imp, quantity="105"):
    return (
        "sales.product_id,sales.sales_date,sales.quantity,sales.unit,sales.business_report_key\n"
        + str(imp[4])
        + ",2026-10-09,"
        + quantity
        + ",cup,REPORT-1\n"
    ).encode()


def analyzed(imp, content=None):
    client = imp[0][5]
    r = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    )
    assert r.status_code == 201, r.text
    b = r.json()["data"]
    ident = b["import_id"]
    cid = str(uuid4())
    u = client.post(
        "/api/v1/imports/" + ident + "/files",
        headers={**imp[3], "Idempotency-Key": str(uuid4())},
        files=[("files[]", ("sales.csv", content or sales_bytes(imp), "text/csv"))],
        data={"client_file_ids[]": cid},
    )
    assert u.status_code == 200, u.text
    ud = u.json()["data"]
    a = post(
        imp,
        "/imports/" + ident + "/analyze",
        dict(
            file_set_version=ud["file_set_version"],
            accepted_file_ids=[x["file_id"] for x in ud["items"]],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=ud["import_revision"],
    )
    assert a.status_code == 202, a.text
    job = a.json()["data"]["job_id"]
    assert client.get("/api/v1/jobs/" + job).json()["data"]["status"] == "queued"
    assert imp[2].run_one() == UUID(job)
    j = client.get("/api/v1/jobs/" + job)
    assert j.status_code == 200 and j.json()["data"]["status"] == "completed", j.text
    return ident


def approved(
    imp, ident, *, source="POS-A", report="daily-sales", context=None, resolutions=None
):
    client = imp[0][5]
    base = "/api/v1/imports/" + ident
    listing = client.get(base + "/mappings?review_only=false&limit=100").json()["data"][
        "items"
    ]
    for item in sorted(listing, key=lambda i: i["issue_type"] != "source_context"):
        if item.get("ignored"):
            continue
        summary = client.get(
            base + "/mapping-summary?include_profile_details=true"
        ).json()["data"]
        current = next((i for i in client.get(base + "/mappings?review_only=false&limit=100").json()["data"]["items"]
            if i["mapping_id"] == item["mapping_id"]), None)
        if current is None or current["status"] == "auto_mapped":
            continue
        if item["issue_type"] == "classification":
            sheet = next(
                sh for sh in summary["sheets"] if sh["sheet_id"] == item["sheet_id"]
            )
            body = {
                "resolution": {
                    "kind": "sheet_type",
                    "sheet_type": sheet["selected_type"],
                    "reason": "Synthetic explicit sheet review",
                }
            }
        elif item["issue_type"] == "source_context":
            body = {
                "resolution": {
                    "kind": "source_context",
                    "source_system_key": source,
                    "report_type": report,
                    "evidence_reference": "Synthetic Owner declared source",
                    "sales_semantics": "daily_total",
                    **(context or {}),
                }
            }
        elif item["issue_type"] == "column" and item["target_field"]:
            body = {"target_field": item["target_field"]}
        elif resolutions and item["code"] in resolutions:
            body = {"resolution": resolutions[item["code"]]}
        else:
            raise AssertionError(item)
        r = client.patch(
            base + "/mappings/" + item["mapping_id"],
            json=body,
            headers={
                **imp[3],
                "Idempotency-Key": str(uuid4()),
                "If-Match": '"' + summary["mapping_revision"] + '"',
            },
        )
        assert r.status_code == 200, r.text
    summary = client.get(base + "/mapping-summary?include_profile_details=true").json()[
        "data"
    ]
    if summary["can_preview"] and not summary["profile_proposals"]:
        from app.models.import_staging import ImportProfile
        ref = summary["binding_refs"][0]
        with Session(imp[0][1]) as session:
            profile = session.get(ImportProfile, UUID(ref["profile_id"]))
            return dict(profile_id=ref["profile_id"], approved_version=ref["version"],
                active_version=profile.active_version, lifecycle_revision=profile.lifecycle_revision,
                content_digest=ref["content_digest"], proposal_revision=profile.proposal_revision)
    p = summary["profile_proposals"][0]
    assert (
        p["missing_fields"] == [] and p["spec"]["scope"]["source_system_key"] == source
    )
    assert not summary["can_preview"]
    r = post(
        imp,
        "/stores/"
        + str(imp[1].store_id)
        + "/mapping-profiles/"
        + p["profile_id"]
        + "/decisions",
        dict(
            decision="approve_activate",
            proposal_revision=p["proposal_revision"],
            expected_active_version=None,
            reason="Synthetic full spec review",
        ),
        match=p["lifecycle_revision"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def previewed(imp, ident):
    client = imp[0][5]
    base = "/api/v1/imports/" + ident
    b = client.get(base).json()["data"]
    m = client.get(base + "/mapping-summary").json()["data"]
    r = post(
        imp,
        "/imports/" + ident + "/process",
        dict(phase="preview", mapping_revision=m["mapping_revision"]),
        match=b["import_revision"],
    )
    assert r.status_code == 202, r.text
    assert imp[2].run_one() == UUID(r.json()["data"]["job_id"])
    response = client.get(base + "?include_preview=true")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["preview"] is not None
    return response.json()["data"]


def test_sales_staging_owner_approval_preview_and_fresh_sessions(imp):
    ident = analyzed(imp)
    decision = approved(imp, ident)
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert row["classification"] == "NEW" and row["after"]["quantity"] == "105"
    assert read["preview"]["summary"]["can_commit"] is False
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportFile)) == 1
        assert fresh.get(ImportBatch, UUID(ident)).status == "preview_ready"
        v = fresh.get(
            ImportProfileVersion,
            (UUID(decision["profile_id"]), decision["approved_version"]),
        )
        assert v.spec_json["scope"]["source_system_key"] == "POS-A"
        assert fresh.scalar(select(func.count()).select_from(ImportPreview)) == 1
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportJob)
                .where(ImportJob.status == "completed")
            )
            == 2
        )


def test_approved_structure_reuse_without_reapproval(imp, monkeypatch):
    ident = analyzed(imp)
    approved(imp, ident)
    from app.infrastructure import import_suggestions

    monkeypatch.setattr(
        import_suggestions,
        "suggest_sheet",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("approved reuse must not call provider")
        ),
    )
    second = analyzed(imp)
    # Source must be declared for this upload before compatible profile reuse.
    from tests.integration.test_import_rule_review import declare_context
    declare_context(imp, second, {'source_system_key': 'POS-A', 'report_type': 'daily-sales'})
    summary = (
        imp[0][5]
        .get(
            "/api/v1/imports/"
            + second
            + "/mapping-summary?include_profile_details=true"
        )
        .json()["data"]
    )
    assert summary["can_preview"] and summary["profile_proposals"] == []
    assert summary["progress"]["unresolved"] == 0
    read = previewed(imp, second)
    assert read["preview"]["rows"][0]["after"]["quantity"] == "105"


def csv_source(schema, records):
    import json

    out = io.StringIO(newline="")
    writer = csv.writer(out)
    fields = tuple(records[0])
    writer.writerow([schema + "." + key for key in fields])
    writer.writerows(
        [
            [
                (
                    json.dumps(row[key])
                    if isinstance(row[key], (dict, list))
                    else (
                        str(row[key]).lower()
                        if isinstance(row[key], bool)
                        else str(row[key]) if row[key] is not None else ""
                    )
                )
                for key in fields
            ]
            for row in records
        ]
    )
    return out.getvalue().encode()


def test_recipe_count_term_fee_and_declarations_are_retained_not_canonical(imp):
    from decimal import Decimal
    from datetime import datetime, timezone
    from app.models import (
        Ingredient,
        InventoryLot,
        InventoryMovement,
        Recipe,
        RecipeLine,
        Supplier,
        SupplierTerm,
    )

    ingredient, lot, supplier = uuid4(), uuid4(), uuid4()
    with Session(imp[0][1]) as s:
        s.add(
            Ingredient(
                id=ingredient,
                store_id=imp[1].store_id,
                name="Synthetic milk",
                base_unit="ml",
                expiry_tracking=True,
                active=True,
            )
        )
        s.add(
            Supplier(
                id=supplier,
                store_id=imp[1].store_id,
                name="Synthetic supplier",
                active=True,
            )
        )
        s.flush()
        s.add(
            InventoryLot(
                id=lot,
                store_id=imp[1].store_id,
                ingredient_id=ingredient,
                unit="ml",
                on_hand_quantity=Decimal("12"),
                updated_at=datetime(2026, 10, 10, 1, tzinfo=timezone.utc),
            )
        )
        s.commit()
    sources = [
        (
            "recipes",
            dict(
                product_id=imp[4],
                version=1,
                effective_from="2026-10-11",
                effective_to=None,
                quantity_basis="WHOLE_BATCH", yield_quantity="10",
                yield_unit="cup",
                process_loss_rate="0.2",
                ingredient_id=ingredient,
                quantity="1000",
                unit="ml",
            ),
            {},
        ),
        (
            "inventory_count",
            dict(
                ingredient_id=ingredient,
                lot_id=lot,
                on_hand="10",
                unit="ml",
                observed_at="2026-10-10T02:00:00Z",
                reason="Synthetic count",
            ),
            {"inventory_semantics": "lot_stock_count"},
        ),
        (
            "supplier_terms",
            dict(
                source_term_key="TERM-1",
                supplier_id=supplier,
                ingredient_id=ingredient,
                effective_from="2026-10-11",
                effective_to=None,
                unit="ml",
                pack_size_base_quantity="1000",
                pack_cost="28000",
                currency="VND",
                minimum_order_quantity="1", price_basis="PER_PACK", price_quantity=None, price_unit=None, moq_basis="PACKS", moq_unit=None,
                lead_time_days=1,
                shelf_life_days=14,
                active=True,
                maximum_order_base_quantity=None,
            ),
            {
                "planned_arrival_expiry_rule": {
                    "basis": "ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS",
                    "evidence_reference": "Explicit 14 calendar days",
                }
            },
        ),
        (
            "payable_fees",
            dict(
                source_fee_key="FEES-1",
                scope="STORE_PROCUREMENT",
                effective_from="2026-10-11",
                effective_to=None,
                mode="NONE",
                coverage="COMPLETE",
                currency="VND",
                components=[],
                covered_source_term_keys=[],
                covered_source_supplier_keys=[str(supplier)],
                evidence_reference="Reviewed no additional payable fees",
                reason="Synthetic supplier agreement",
            ),
            {},
        ),
        (
            "scope_declarations",
            dict(
                source_declaration_key="INVENTORY-1",
                declaration=dict(
                    kind="INVENTORY",
                    ingredient_id=str(ingredient),
                    state="COMPLETE_CURRENT_LOTS",
                    observed_at="2026-10-10T02:00:00Z",
                    covered_lot_ids=[str(lot)],
                    evidence_reference="Physical inspection complete",
                ),
            ),
            {},
        ),
    ]
    outputs = {}
    for schema, source, context in sources:
        ident = analyzed(imp, csv_source(schema, [source]))
        approved(imp, ident, report=schema, context=context)
        analysis = imp[0][5].get(
            "/api/v1/imports/" + ident + "?include=configurations&rows_limit=1"
        )
        assert analysis.status_code == 200, analysis.text
        if schema in {"supplier_terms", "payable_fees", "scope_declarations"}:
            configs = analysis.json()["data"]["configurations"]
            assert (
                configs["basis"] == "analysis"
                and configs["analysis_rows"][0]["normalization_status"]
                == "NOT_PREVIEWED"
            )
        outputs[schema] = previewed(imp, ident)["preview"]
        if schema == "payable_fees":
            # A canonical Supplier UUID spelled as a source key is not an approved
            # Store/source binding. Preview retains the evidence but cannot certify it.
            assert "UNKNOWN_SUPPLIER_SOURCE" in {n["code"] for n in outputs[schema]["summary"]["blockers"]}
        else:
            assert not outputs[schema]["summary"]["blockers"], outputs[schema]
        response = imp[0][5].get(
            "/api/v1/imports/" + ident + "?include=configurations,preview&rows_limit=1"
        )
        assert response.status_code == 200, response.text
        projected = response.json()["data"]
        assert (
            projected["configurations"]["preview_digest"]
            == projected["preview"]["summary"]["digest"]
        )
        assert (
            projected["configurations"]["rows_page"]
            == projected["preview"]["rows_page"]
        )
    assert outputs["recipes"]["rows"][0]["after"]["lines"][0]["quantity"] == "1000"
    assert outputs["inventory_count"]["rows"][0]["changes"][0]["delta"] == "-2"
    assert outputs["supplier_terms"]["rows"][0]["after"]["shelf_life_days"] == 14
    assert "REQUIRED_ARRIVAL_EXPIRY_UNKNOWN" not in {
        w["code"] for w in outputs["supplier_terms"]["summary"]["warnings"]
    }
    with Session(imp[0][1]) as fresh:
        assert fresh.get(InventoryLot, lot).on_hand_quantity == Decimal("12")
        for model in (InventoryMovement, Recipe, RecipeLine, SupplierTerm, SalesDaily):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
        assert fresh.scalar(select(func.count()).select_from(ImportPreview)) == 5


def test_multiple_approved_profiles_require_explicit_context_selection(imp):
    first = analyzed(imp)
    approved(imp, first)
    # Change scope on the second captured report without modifying old version.
    second = analyzed(imp)
    client = imp[0][5]
    base = "/api/v1/imports/" + second
    item = next(
        i
        for i in client.get(base + "/mappings?review_only=false").json()["data"][
            "items"
        ]
        if i["issue_type"] == "source_context"
    )
    m = client.get(base + "/mapping-summary").json()["data"]
    r = client.patch(
        base + "/mappings/" + item["mapping_id"],
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json={
            "resolution": {
                "kind": "source_context",
                "source_system_key": "POS-B",
                "report_type": "daily-sales",
                "evidence_reference": "Second explicit source",
                "sales_semantics": "daily_total",
            }
        },
    )
    assert r.status_code == 200, r.text
    m = client.get(base + "/mapping-summary?include_profile_details=true").json()[
        "data"
    ]
    p = m["profile_proposals"][0]
    r = post(
        imp,
        "/stores/"
        + str(imp[1].store_id)
        + "/mapping-profiles/"
        + p["profile_id"]
        + "/decisions",
        dict(
            decision="approve_activate",
            proposal_revision=p["proposal_revision"],
            expected_active_version=None,
            reason="Owner source review",
        ),
        match=p["lifecycle_revision"],
    )
    assert r.status_code == 200, r.text
    third = analyzed(imp)
    base = "/api/v1/imports/" + third
    m = client.get(base + "/mapping-summary").json()["data"]
    assert not m["can_preview"] and len(m["approved_contexts"]) == 2
    item = next(
        i
        for i in client.get(base + "/mappings?review_only=false").json()["data"][
            "items"
        ]
        if i["issue_type"] == "source_context"
    )
    assert item["code"] == "PROFILE_MATCH_AMBIGUOUS"
    r = client.patch(
        base + "/mappings/" + item["mapping_id"],
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json={
            "resolution": {
                "kind": "source_context",
                "source_system_key": "POS-A",
                "report_type": "daily-sales",
                "evidence_reference": "Selected approved context",
            }
        },
    )
    assert (
        r.status_code == 200 and r.json()["data"]["approval_required"] is False
    ), r.text
    assert client.get(base + "/mapping-summary").json()["data"]["can_preview"]


def test_all_rejected_upload_has_actionable_error_and_receipt(imp):
    client = imp[0][5]
    b = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    ).json()["data"]
    key = str(uuid4())
    cid = str(uuid4())

    def upload():
        return client.post(
            "/api/v1/imports/" + b["import_id"] + "/files",
            headers={**imp[3], "Idempotency-Key": key},
            files=[
                (
                    "files[]",
                    ("../bad.exe", b"not a spreadsheet", "application/octet-stream"),
                )
            ],
            data={"client_file_ids[]": cid},
        )

    r = upload()
    again = upload()
    assert r.status_code == again.status_code == 422
    assert r.json()["error"] == again.json()["error"]
    assert r.json()["data"] is None and r.json()["error"]["code"] == "UPLOAD_REJECTED"
    item = r.json()["error"]["details"]["items"][0]
    assert (
        item["filename"] == "bad.exe"
        and item["file_id"] is None
        and item["error"]["code"] == "INVALID_FILE_TYPE"
    )
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportFile)) == 1
        assert fresh.scalar(select(func.count()).select_from(ImportReceipt)) == 2


def queued_analysis(imp, content=None):
    client = imp[0][5]
    b = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    ).json()["data"]
    u = client.post(
        "/api/v1/imports/" + b["import_id"] + "/files",
        headers={**imp[3], "Idempotency-Key": str(uuid4())},
        files=[("files[]", ("sales.csv", content or sales_bytes(imp), "text/csv"))],
        data={"client_file_ids[]": str(uuid4())},
    ).json()["data"]
    r = post(
        imp,
        "/imports/" + b["import_id"] + "/analyze",
        dict(
            file_set_version=u["file_set_version"],
            accepted_file_ids=[u["items"][0]["file_id"]],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=u["import_revision"],
    )
    assert r.status_code == 202, r.text
    return UUID(b["import_id"]), UUID(r.json()["data"]["job_id"])


def test_parser_failure_retains_location_and_retry_is_explicit(imp, monkeypatch):
    from app.application.use_cases import import_staging as module
    from app.application.contracts.import_source import SourceParseError

    bid, jid = queued_analysis(imp)

    def failure(*args):
        raise SourceParseError(
            "MALFORMED_WORKBOOK", sheet="Synthetic sheet", row=7, column=2
        )

    monkeypatch.setattr(module, "parse_source", failure)
    assert imp[2].run_one() == jid
    result = imp[0][5].get("/api/v1/jobs/" + str(jid)).json()["data"]
    assert result["status"] == "failed" and result["result"] is None
    location = result["error"]["details"]["source_locations"][0]
    assert (
        location["sheet_name"] == "Synthetic sheet"
        and location["row_number"] == 7
        and location["source_column_index"] == 2
    )
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportBatch, bid).analysis_json is None
        assert fresh.scalar(select(ImportFile.parse_status)) == "failed"
    assert imp[2].run_one() is None
    b = imp[0][5].get("/api/v1/imports/" + str(bid)).json()["data"]
    retry = post(
        imp,
        "/imports/" + str(bid) + "/analyze",
        dict(
            file_set_version=b["file_set_version"],
            accepted_file_ids=b["source_set"]["accepted_file_ids"],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=b["import_revision"],
    )
    assert retry.status_code == 202 and retry.json()["data"]["job_id"] != str(jid)


def test_completed_job_programming_error_is_not_success_or_failed(imp, monkeypatch):
    bid, jid = queued_analysis(imp)
    original = Session.commit
    fired = []

    def commit(session):
        completed = any(
            isinstance(row, ImportJob) and row.id == jid and row.status == "completed"
            for row in session.identity_map.values()
        )
        original(session)
        if completed and not fired:
            fired.append(True)
            raise ValueError("synthetic post-commit bug")

    monkeypatch.setattr(Session, "commit", commit)
    with pytest.raises(ValueError, match="synthetic post-commit bug"):
        imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.get(ImportJob, jid).status == "completed"
            and fresh.get(ImportJob, jid).error_json is None
        )
        assert fresh.get(ImportBatch, bid).analysis_json is not None
    assert imp[2].run_one() is None


def test_failure_recording_error_does_not_replace_primary(imp, monkeypatch):
    from app.application.use_cases import import_staging as module

    bid, jid = queued_analysis(imp)
    original = Session.commit
    monkeypatch.setattr(
        module,
        "parse_source",
        lambda *a: (_ for _ in ()).throw(ValueError("primary parse bug")),
    )

    def commit(session):
        if any(
            isinstance(row, ImportJob) and row.id == jid and row.status == "failed"
            for row in session.identity_map.values()
        ):
            raise OSError("synthetic recording failure")
        original(session)

    monkeypatch.setattr(Session, "commit", commit)
    with pytest.raises(ValueError, match="primary parse bug") as caught:
        imp[2].run_one()
    assert any(
        "failure recording failed: OSError" in note for note in caught.value.__notes__
    )
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.get(ImportJob, jid).status == "running"
            and fresh.get(ImportJob, jid).error_json is None
        )
        assert fresh.get(ImportBatch, bid).analysis_json is None


def test_real_dead_process_recovery_and_live_process_not_recovered(imp):
    import json, subprocess, sys
    from app.infrastructure.planning_process import current_process, liveness
    from app.application.contracts.planning_run import ProcessIdentity

    bid, jid = queued_analysis(imp)
    process = current_process().model_dump(mode="json")
    with Session(imp[0][1]) as s:
        j = s.get(ImportJob, jid)
        j.status = "running"
        j.claim = uuid4()
        j.input_json = {**j.input_json, "process": process}
        s.commit()
    assert imp[2].recover() == ()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.infrastructure.planning_process import current_process; print(current_process().model_dump_json())",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    departed = json.loads(result.stdout)
    assert liveness(ProcessIdentity.model_validate(departed)) == "DEAD"
    with Session(imp[0][1]) as s:
        j = s.get(ImportJob, jid)
        j.input_json = {**j.input_json, "process": departed}
        s.commit()
    assert imp[2].recover() == (jid,) and imp[2].recover() == ()
    with Session(imp[0][1]) as fresh:
        assert (
            fresh.get(ImportJob, jid).error_json["code"]
            == "IMPORT_EXECUTOR_INTERRUPTED"
        )
        assert fresh.get(ImportBatch, bid).analysis_json is None


def test_staff_proposes_context_owner_only_approval_and_current_revoke(imp):
    from app.models.auth import MembershipGrant
    from app.domain.permissions import PERMISSIONS
    from tests.integration.test_auth_public import PASSWORD

    ident = analyzed(imp)
    client = imp[0][5]
    target = setup(imp[0], email="staff-import@example.test", store=False)
    mid = uuid4()
    with Session(imp[0][1]) as s:
        s.add(
            StoreMembership(
                id=mid,
                store_id=imp[1].store_id,
                user_id=target.user_id,
                role="STAFF",
                active=True,
            )
        )
        s.flush()
        for key in (
            "import.read",
            "mapping.read",
            "mapping.propose",
            "menu.read",
            "sales.read",
        ):
            s.add(MembershipGrant(membership_id=mid, permission=key))
        s.commit()
    wire = login(imp[0], email="staff-import@example.test").json()["data"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": wire["session"]["csrf_token"]}
    base = "/api/v1/imports/" + ident
    m = client.get(base + "/mapping-summary").json()["data"]
    issue = next(
        i
        for i in client.get(base + "/mappings?review_only=false").json()["data"][
            "items"
        ]
        if i["issue_type"] == "source_context"
    )
    body = {
        "resolution": {
            "kind": "source_context",
            "source_system_key": "POS-A",
            "report_type": "daily-sales",
            "sales_semantics": "daily_total",
            "evidence_reference": "Staff source declaration",
        }
    }
    r = client.patch(
        base + "/mappings/" + issue["mapping_id"],
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json=body,
    )
    assert r.status_code == 200, r.text
    m = client.get(base + "/mapping-summary?include_profile_details=true").json()[
        "data"
    ]
    p = m["profile_proposals"][0]
    r = client.post(
        "/api/v1/stores/"
        + str(imp[1].store_id)
        + "/mapping-profiles/"
        + p["profile_id"]
        + "/decisions",
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + p["lifecycle_revision"] + '"',
        },
        json={
            "decision": "approve_activate",
            "proposal_revision": p["proposal_revision"],
            "expected_active_version": None,
            "reason": "cannot self approve",
        },
    )
    assert r.status_code == 403
    with Session(imp[0][1]) as s:
        s.delete(s.get(MembershipGrant, (mid, "mapping.read")))
        s.commit()
    assert client.get(base + "/mapping-summary").status_code == 403
    with Session(imp[0][1]) as s:
        s.get(StoreMembership, mid).active = False
        s.commit()
    assert (
        client.get(base + "/mapping-summary").status_code == 404
    )  # owning Store no longer accessible


def test_read_set_is_repeatable_read_readonly_and_detached(imp):
    from sqlalchemy import event
    from decimal import Decimal
    from datetime import date
    from app.repositories.import_staging import capture_read_set

    fired = []

    def mutate(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT products.") and not fired:
            fired.append(True)
            assert (
                connection.scalar(text("show transaction_isolation"))
                == "repeatable read"
            )
            assert connection.scalar(text("show transaction_read_only")) == "on"
            with Session(imp[0][1]) as other:
                other.add(
                    SalesDaily(
                        store_id=imp[1].store_id,
                        product_id=imp[4],
                        sales_date=date(2026, 10, 9),
                        quantity=Decimal("77"),
                    )
                )
                other.commit()

    event.listen(imp[0][1], "after_cursor_execute", mutate)
    try:
        snapshot, _ = capture_read_set(imp[0][1], imp[1].store_id, {"sales"})
    finally:
        event.remove(imp[0][1], "after_cursor_execute", mutate)
    assert fired and snapshot["sales_daily"] == [] and imp[0][1].pool.checkedout() == 0
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(SalesDaily.quantity)) == 77
    assert snapshot["sales_daily"] == [] and snapshot["supplier_terms"] == []


def test_owner_reserved_product_dependency_and_no_bootstrap_writes(imp):
    content = sales_bytes(imp).replace(str(imp[4]).encode(), b"COFFEE-NEW")
    ident = analyzed(imp, content)
    approved(
        imp,
        ident,
        resolutions={
            "UNKNOWN_PRODUCT": dict(
                kind="new_entity_proposal",
                entity="product",
                source_business_key="COFFEE-NEW",
                metadata=dict(
                    name="New synthetic menu item",
                    selling_unit="cup",
                    sku="COFFEE-NEW",
                    price=None,
                    active=True,
                ),
                evidence_reference="Explicit Owner product review",
            )
        },
    )
    preview = previewed(imp, ident)["preview"]
    rows = preview["rows"]
    assert not preview["summary"]["blockers"] and len(rows) == 2
    creation = next(r for r in rows if r["proposed_action"] == "CREATE_PRODUCT")
    sale = next(r for r in rows if r["after"]["domain"] == "sales")
    assert sale["dependencies"] == [creation["row_id"]]
    assert creation["entity_refs"]["product_id"] == sale["entity_refs"]["product_id"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(Product)) == 1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_migration_roundtrip_preserves_canonical_rows(imp):
    from alembic import command
    from scripts.dev import migration_config
    from sqlalchemy import inspect
    from app.infrastructure.database.base import Base

    cfg = migration_config()
    command.downgrade(cfg, "0012_public_read_revisions")
    with Session(imp[0][1]) as fresh:
        assert fresh.get(Product, imp[4]).name == "Synthetic coffee"
    assert "import_batches" not in inspect(imp[0][1]).get_table_names()
    command.upgrade(cfg, "head")
    assert set(inspect(imp[0][1]).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    with Session(imp[0][1]) as fresh:
        assert fresh.get(Product, imp[4]).name == "Synthetic coffee"


def test_uncertain_acceptance_is_error_then_retry_reads_durable_receipt(
    imp, monkeypatch
):
    from sqlalchemy.exc import OperationalError
    import psycopg
    from app.application.contracts.auth import AuthError

    token = imp[0][5].cookies.get("__Host-shelfcash_session")
    key = str(uuid4())
    body = dto.DraftRequest(data_date="2026-10-09")
    original = Session.commit
    fired = []

    def commit(session):
        accepting = any(isinstance(row, ImportReceipt) for row in session.new)
        original(session)
        if accepting and not fired:
            fired.append(True)
            raise OperationalError(
                None,
                None,
                psycopg.OperationalError("synthetic connection acknowledgment loss"),
                connection_invalidated=True,
            )

    monkeypatch.setattr(Session, "commit", commit)
    with pytest.raises(OperationalError):
        imp[2].create(token, imp[1].store_id, body, key, imp[3]["X-CSRF-Token"])
    with Session(imp[0][1]) as fresh:
        retained = fresh.scalar(select(ImportBatch.id))
        assert retained is not None
        assert fresh.scalar(select(func.count()).select_from(ImportReceipt)) == 1
    result = imp[2].create(token, imp[1].store_id, body, key, imp[3]["X-CSRF-Token"])
    assert result.import_id == retained
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportBatch)) == 1


def test_context_semantics_edit_is_proposal_and_keeps_active_version(imp):
    ident = analyzed(imp)
    decision = approved(imp, ident)
    client = imp[0][5]
    base = "/api/v1/imports/" + ident
    item = next(
        i
        for i in client.get(base + "/mappings?review_only=false").json()["data"][
            "items"
        ]
        if i["issue_type"] == "source_context"
    )
    m = client.get(base + "/mapping-summary").json()["data"]
    r = client.patch(
        base + "/mappings/" + item["mapping_id"],
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json={
            "resolution": {
                "kind": "source_context",
                "source_system_key": "POS-A",
                "report_type": "daily-sales",
                "evidence_reference": "Explicit changed sales meaning",
                "sales_semantics": "disjoint_contribution",
            }
        },
    )
    assert r.status_code == 200 and r.json()["data"]["approval_required"], r.text
    m = client.get(base + "/mapping-summary?include_profile_details=true").json()[
        "data"
    ]
    assert (
        not m["can_preview"]
        and m["profile_proposals"][0]["spec"]["sales_semantics"]
        == "disjoint_contribution"
    )
    with Session(imp[0][1]) as fresh:
        active = fresh.get(
            ImportProfileVersion,
            (UUID(decision["profile_id"]), decision["approved_version"]),
        )
        assert active.spec_json["sales_semantics"] == "daily_total"


def test_upload_retry_content_dedup_and_source_set_seal(imp):
    from app.models.import_staging import ImportBlob

    client = imp[0][5]
    r = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    ).json()["data"]
    ident = r["import_id"]
    key = str(uuid4())
    cid = str(uuid4())

    def upload(cid, key, content):
        return client.post(
            "/api/v1/imports/" + ident + "/files",
            headers={**imp[3], "Idempotency-Key": key},
            files=[("files[]", ("sales.csv", content, "text/csv"))],
            data={"client_file_ids[]": cid},
        )

    first = upload(cid, key, sales_bytes(imp))
    again = upload(cid, key, sales_bytes(imp))
    assert first.json()["data"] == again.json()["data"]
    assert upload(cid, str(uuid4()), sales_bytes(imp, "99")).status_code == 409
    second = upload(str(uuid4()), str(uuid4()), sales_bytes(imp))
    assert (
        second.status_code == 200
        and second.json()["meta"]["warnings"][0]["code"] == "DUPLICATE_CONTENT"
    )
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ImportBlob)) == 1
        assert s.scalar(select(func.count()).select_from(ImportFile)) == 2
    ud = second.json()["data"]
    read = client.get("/api/v1/imports/" + ident).json()["data"]
    bad = post(
        imp,
        "/imports/" + ident + "/analyze",
        dict(
            file_set_version=ud["file_set_version"],
            accepted_file_ids=[read["files"][0]["file_id"]],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=read["import_revision"],
    )
    assert bad.status_code == 422
    ok = post(
        imp,
        "/imports/" + ident + "/analyze",
        dict(
            file_set_version=ud["file_set_version"],
            accepted_file_ids=read["source_set"]["accepted_file_ids"],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=read["import_revision"],
    )
    assert ok.status_code == 202
    assert upload(str(uuid4()), str(uuid4()), sales_bytes(imp)).status_code == 409


def test_retired_version_blocks_new_preview_but_retained_result_is_readable(imp):
    ident = analyzed(imp)
    decision = approved(imp, ident)
    read = previewed(imp, ident)
    result = post(
        imp,
        "/stores/"
        + str(imp[1].store_id)
        + "/mapping-profiles/"
        + decision["profile_id"]
        + "/decisions",
        dict(
            decision="retire",
            active_version=decision["active_version"],
            reason="Synthetic retire",
        ),
        match=decision["lifecycle_revision"],
    )
    assert result.status_code == 200
    retained = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]["preview"]
    )
    assert (
        retained["stale"]
        and retained["summary"]["digest"] == read["preview"]["summary"]["digest"]
    )
    b = imp[0][5].get("/api/v1/imports/" + ident).json()["data"]
    m = imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    rejected = post(
        imp,
        "/imports/" + ident + "/process",
        dict(phase="preview", mapping_revision=m["mapping_revision"]),
        match=b["import_revision"],
    )
    assert rejected.status_code == 409


def test_source_context_change_invalidates_usage_without_mutating_evidence(imp):
    from app.models.import_staging import ImportProfile

    ident = analyzed(imp)
    decision = approved(imp, ident)
    read = previewed(imp, ident)
    old_digest = read["preview"]["summary"]["digest"]
    client = imp[0][5]
    base = "/api/v1/imports/" + ident
    item = next(
        i
        for i in client.get(base + "/mappings?review_only=false&limit=100").json()[
            "data"
        ]["items"]
        if i["issue_type"] == "source_context"
    )
    m = client.get(base + "/mapping-summary").json()["data"]
    r = client.patch(
        base + "/mappings/" + item["mapping_id"],
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json={
            "resolution": {
                "kind": "source_context",
                "source_system_key": "POS-B",
                "report_type": "daily-sales",
                "evidence_reference": "New source explicitly declared",
                "sales_semantics": "daily_total",
            }
        },
    )
    assert r.status_code == 200, r.text
    current = client.get(base + "?include_preview=true").json()["data"]["preview"]
    assert current["stale"] and current["summary"]["digest"] == old_digest
    m = client.get(base + "/mapping-summary?include_profile_details=true").json()[
        "data"
    ]
    assert m["profile_proposals"][0]["spec"]["scope"]["source_system_key"] == "POS-B"
    assert not m["can_preview"]
    with Session(imp[0][1]) as s:
        assert (
            s.get(
                ImportProfileVersion,
                (UUID(decision["profile_id"]), decision["approved_version"]),
            ).spec_json["scope"]["source_system_key"]
            == "POS-A"
        )
        assert s.scalar(select(ImportPreview.digest)) == old_digest


def test_operational_change_sets_stale_and_does_not_recompute_preview(imp):
    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    with Session(imp[0][1]) as s:
        p = s.get(Product, imp[4])
        p.name = "Changed after capture"
        s.commit()
    latest = (
        imp[0][5]
        .get("/api/v1/imports/" + ident + "?include_preview=true")
        .json()["data"]["preview"]
    )
    assert latest["stale"] and latest["rows"] == read["preview"]["rows"]
    assert latest["summary"] == read["preview"]["summary"]


def test_db_prevents_evidence_update_delete(imp):
    from sqlalchemy.exc import DBAPIError

    ident = analyzed(imp)
    approved(imp, ident)
    previewed(imp, ident)
    for statement in (
        "UPDATE import_blobs SET content=content",
        "DELETE FROM import_files",
        "UPDATE import_previews SET digest=digest",
        "UPDATE import_profile_versions SET spec_json=spec_json || jsonb_build_object('tampered',true)",
        "DELETE FROM import_audit",
    ):
        with Session(imp[0][1]) as s:
            with pytest.raises(DBAPIError):
                s.execute(text(statement))
                s.flush()
            s.rollback()


def test_concurrent_acceptance_and_two_executors_claim_once(imp):
    token = imp[0][5].cookies.get("__Host-shelfcash_session")
    body = dto.DraftRequest(data_date="2026-10-09")
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                imp[2].create, token, imp[1].store_id, body, key, imp[3]["X-CSRF-Token"]
            )
            for _ in range(2)
        ]
        results = [f.result(timeout=10) for f in futures]
    assert results[0] == results[1]
    client = imp[0][5]
    ident = str(results[0].import_id)
    u = client.post(
        "/api/v1/imports/" + ident + "/files",
        headers={**imp[3], "Idempotency-Key": str(uuid4())},
        files=[("files[]", ("sales.csv", sales_bytes(imp), "text/csv"))],
        data={"client_file_ids[]": str(uuid4())},
    ).json()["data"]
    a = post(
        imp,
        "/imports/" + ident + "/analyze",
        dict(
            file_set_version=u["file_set_version"],
            accepted_file_ids=[u["items"][0]["file_id"]],
            acknowledged_rejected_client_file_ids=[],
        ),
        match=u["import_revision"],
    ).json()["data"]
    other = ImportStaging(imp[0][2], imp[0][0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(s.run_one) for s in (imp[2], other)]
        executed = [f.result(timeout=15) for f in futures]
    assert sum(v == UUID(a["job_id"]) for v in executed) == 1
    with Session(imp[0][1]) as s:
        assert s.get(ImportJob, UUID(a["job_id"])).status == "completed"
        assert (
            s.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "IMPORT_JOB_COMPLETED")
            )
            == 1
        )


def test_parse_and_compute_release_connections_and_revoke_is_rechecked(
    imp, monkeypatch
):
    import app.application.use_cases.import_staging as module

    original = module.parse_source

    def revoked_parser(*args):
        assert imp[0][1].pool.checkedout() == 0
        with Session(imp[0][1]) as s:
            member = s.scalar(
                select(StoreMembership).where(
                    StoreMembership.store_id == imp[1].store_id
                )
            )
            member.active = False
            s.commit()
        return original(*args)

    monkeypatch.setattr(module, "parse_source", revoked_parser)
    with pytest.raises(AssertionError):
        analyzed(imp)
    with Session(imp[0][1]) as s:
        job = s.scalar(select(ImportJob))
        assert job.status == "failed" and job.error_json["code"] == "PERMISSION_DENIED"
        assert s.get(ImportBatch, job.import_id).analysis_json is None


def test_request_limits_extra_fields_and_unsupported_target(imp):
    assert (
        post(
            imp,
            "/stores/" + str(imp[1].store_id) + "/imports",
            {"data_date": "2026-10-09", "actor_id": str(uuid4())},
        ).status_code
        == 422
    )
    assert (
        post(
            imp,
            "/stores/" + str(imp[1].store_id) + "/imports",
            {"data_date": "2026-10-09T00:00:00"},
        ).status_code
        == 422
    )
    r = imp[0][5].post(
        "/api/v1/stores/" + str(imp[1].store_id) + "/imports",
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "Content-Type": "application/json",
        },
        content=b" " * 65537,
    )
    assert r.status_code == 413


def test_exact_daily_total_replacement_not_addition(imp):
    from datetime import date
    from decimal import Decimal

    with Session(imp[0][1]) as s:
        s.add(
            SalesDaily(
                store_id=imp[1].store_id,
                product_id=imp[4],
                sales_date=date(2026, 10, 9),
                quantity=Decimal("100"),
            )
        )
        s.commit()
    ident = analyzed(imp)
    approved(imp, ident, context={"missing_stockout": "not_provided"})
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert row["before"]["quantity"] == "100" and row["after"]["quantity"] == "105"
    assert (
        row["proposed_action"] == "REPLACE_DAILY_TOTAL" and row["confirmation_required"]
    )
    assert row["changes"][0]["delta"] == "5"
    with Session(imp[0][1]) as s:
        assert s.scalar(select(SalesDaily.quantity)) == 100


def test_missing_zero_duplicates_and_future_rows_are_blockers(imp):
    content = (
        sales_bytes(imp, "0")
        + f"{imp[4]},2026-10-09,,cup,R2\n{imp[4]},2026-10-09,2,cup,R3\n{imp[4]},2026-10-11,2,cup,R4\n".encode()
    )
    ident = analyzed(imp, content)
    approved(imp, ident)
    read = previewed(imp, ident)
    assert read["status"] == "blocked"
    rows = read["preview"]["rows"]
    codes = {b["code"] for r in rows for b in r["blockers"]}
    assert {
        "MISSING_REQUIRED_VALUE",
        "SALES_OVERLAP_UNRESOLVED",
        "FUTURE_SALES_NOT_OBSERVED",
    } <= codes
    # A1 projects one logical Product/day effect, retaining each raw contribution.
    assert any(c["quantity"] == "0" for r in rows for c in r["sales_contributions"])


def test_cas_idempotency_and_commit_requires_import_review(imp):
    key = str(uuid4())
    path = "/stores/" + str(imp[1].store_id) + "/imports"
    body = {"data_date": "2026-10-09"}
    first = post(imp, path, body, key=key)
    again = post(imp, path, body, key=key)
    assert first.json()["data"] == again.json()["data"]
    assert post(imp, path, {"data_date": "2026-10-08"}, key=key).status_code == 409
    ident = analyzed(imp)
    approved(imp, ident)
    read = previewed(imp, ident)
    r = post(
        imp,
        "/imports/" + ident + "/process",
        dict(
            phase="commit",
            preview_id=read["preview"]["summary"]["preview_id"],
            preview_digest=read["preview"]["summary"]["digest"],
            confirm=True,
            reason="Missing per-import review",
            resolutions=[],
        ),
        match=read["import_revision"],
    )
    assert (
        r.status_code == 409
        and r.json()["error"]["code"] == "PREVIEW_BLOCKED"
    )


def test_capability_hints_use_current_permissions_and_actual_state(imp):
    from app.models.auth import MembershipGrant

    client = imp[0][5]
    empty = post(
        imp, "/stores/" + str(imp[1].store_id) + "/imports", {"data_date": "2026-10-09"}
    ).json()["data"]
    assert client.get("/api/v1/imports/" + empty["import_id"]).json()["data"][
        "allowed_actions"
    ] == ["upload"]
    ident = analyzed(imp)
    approved(imp, ident)
    previewed(imp, ident)
    reader = setup(imp[0], email="reader-import@example.test", store=False)
    mid = uuid4()
    with Session(imp[0][1]) as s:
        s.add(
            StoreMembership(
                id=mid,
                store_id=imp[1].store_id,
                user_id=reader.user_id,
                role="STAFF",
                active=True,
            )
        )
        s.flush()
        for key in ("import.read", "mapping.read", "menu.read", "sales.read"):
            s.add(MembershipGrant(membership_id=mid, permission=key))
        s.commit()
    login(imp[0], email="reader-import@example.test")
    result = client.get("/api/v1/imports/" + ident + "?include_preview=true")
    assert result.status_code == 200, result.text
    assert (
        result.json()["data"]["allowed_actions"] == []
        and result.json()["data"]["completion_available"] is False
    )
    summary = client.get("/api/v1/imports/" + ident + "/mapping-summary").json()["data"]
    assert not summary["can_preview"] and summary["allowed_actions"] == []


def test_owner_decision_compare_and_swap_race_is_atomic(imp):
    from app.application.contracts.auth import AuthError

    ident = analyzed(imp)
    first = approved(imp, ident)
    client = imp[0][5]
    base = "/api/v1/imports/" + ident
    item = next(
        i
        for i in client.get(base + "/mappings?review_only=false").json()["data"][
            "items"
        ]
        if i["issue_type"] == "source_context"
    )
    m = client.get(base + "/mapping-summary").json()["data"]
    changed = client.patch(
        base + "/mappings/" + item["mapping_id"],
        headers={
            **imp[3],
            "Idempotency-Key": str(uuid4()),
            "If-Match": '"' + m["mapping_revision"] + '"',
        },
        json={
            "resolution": {
                "kind": "source_context",
                "source_system_key": "POS-A",
                "report_type": "daily-sales",
                "evidence_reference": "Reviewed source semantics change",
                "sales_semantics": "disjoint_contribution",
            }
        },
    )
    assert changed.status_code == 200
    proposal = client.get(
        base + "/mapping-summary?include_profile_details=true"
    ).json()["data"]["profile_proposals"][0]
    body = dto.Approve(
        decision="approve_activate",
        proposal_revision=proposal["proposal_revision"],
        expected_active_version=first["active_version"],
        reason="Whole version review",
    )
    token = client.cookies.get("__Host-shelfcash_session")

    def decide():
        try:
            return imp[2].decision(
                token,
                imp[1].store_id,
                UUID(proposal["profile_id"]),
                body,
                str(uuid4()),
                '"' + proposal["lifecycle_revision"] + '"',
                imp[3]["X-CSRF-Token"],
            )
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert sum(isinstance(r, dto.DecisionResult) for r in results) == 1
    assert "PROFILE_REVISION_CONFLICT" in results
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 2
        assert (
            fresh.scalar(
                select(func.count())
                .select_from(ImportAudit)
                .where(ImportAudit.kind == "PROFILE_APPROVE_ACTIVATE")
            )
            == 2
        )


def test_bounded_worker_drains_durable_job_and_get_only_reads(imp, monkeypatch):
    import time
    from threading import Event
    from app.infrastructure.import_worker import ImportWorker
    from app.application.use_cases import import_staging as module

    bid, jid = queued_analysis(imp)
    original = module.parse_source
    calls = []
    parsed = Event()

    def parse(*args):
        try:
            assert imp[0][1].pool.checkedout() == 0
            calls.append(True)
            return original(*args)
        finally:
            parsed.set()

    monkeypatch.setattr(module, "parse_source", parse)
    assert (
        imp[0][5].get("/api/v1/jobs/" + str(jid)).json()["data"]["status"] == "queued"
    )
    assert not calls
    worker = ImportWorker(imp[2])
    worker.start()
    try:
        # No competing test read while asserting executor-owned pool release.
        assert parsed.wait(10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with Session(imp[0][1]) as fresh:
                if fresh.get(ImportJob, jid).status in {"completed", "failed"}:
                    break
            time.sleep(0.05)
    finally:
        worker.stop()
    assert len(calls) == 1
    result = imp[0][5].get("/api/v1/jobs/" + str(jid)).json()["data"]
    assert result["status"] == "completed" and result["result"]["resource_id"] == str(
        bid
    )
    assert len(calls) == 1 and not worker.thread.is_alive()


def test_cross_store_and_current_revocation(imp):
    ident = analyzed(imp)
    other = setup(imp[0], "other@example.test")
    login(imp[0], "other@example.test")
    assert imp[0][5].get("/api/v1/imports/" + ident).status_code == 404
    login(imp[0])
    with Session(imp[0][1]) as s:
        member = s.scalar(
            select(StoreMembership).where(StoreMembership.store_id == imp[1].store_id)
        )
        member.active = False
        s.commit()
    assert imp[0][5].get("/api/v1/imports/" + ident).status_code == 404
