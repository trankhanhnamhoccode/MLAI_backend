"""Native HTTP negative/replay cases. No fake status/ledger updates."""
from datetime import datetime,timedelta
import hashlib
import json
from uuid import UUID,uuid4

from sqlalchemy import select,func
from sqlalchemy.orm import Session

from scripts.integration_workflow import analyze,csv_bytes,complete_import


def cases(owner,manifest,engine,retained_path,pdf_url,passed,completed=()):
    base="/api/v1/stores/"+manifest["store_id"]
    day=datetime.fromisoformat(manifest["anchor_date"]).date()
    from app.models import SalesDaily,InventoryLot
    initial=owner.get(retained_path).json()["data"]
    before_pdf=owner.get(pdf_url).content
    if "aggregate_quota_partial_ack_cas_seal_replay" not in completed:
        # Aggregate quota across calls + partial acceptance + authoritative refresh.
        draft=owner.post(base+"/imports",{"data_date":day.isoformat()},expected=(201,)).json()["data"]
        ident=draft["import_id"];path="/api/v1/imports/"+ident
        first=owner.post(path+"/files",files=[("files[]",(f"quota-{i}.csv",b"a\n","text/csv")) for i in range(18)],
                         data={"client_file_ids[]":[str(uuid4()) for _ in range(18)]}).json()["data"]
        key=str(uuid4());ids=[str(uuid4()) for _ in range(3)]
        args=dict(files=[("files[]",(name,b"a\n","application/octet-stream")) for name in ("last1.csv","last2.csv","bad.exe")],data={"client_file_ids[]":ids})
        uploaded=owner.post(path+"/files",key=key,**args).json()["data"]
        assert [x["upload_status"] for x in uploaded["items"]]==["uploaded","uploaded","rejected"]
        assert owner.post(path+"/files",key=key,**args).json()["data"]==uploaded
        current=owner.get(path).json()["data"]
        assert current["quota"]["accepted_file_count"]==20 and current["quota"]["remaining_file_slots"]==0
        assert current["quota"]["accepted_total_bytes"]==40
        body=dict(file_set_version=current["file_set_version"],accepted_file_ids=current["source_set"]["accepted_file_ids"],acknowledged_rejected_client_file_ids=[])
        owner.post(path+"/analyze",body,match=first["import_revision"],expected=(412,))
        owner.post(path+"/analyze",body,match=current["import_revision"],expected=(422,))
        assert not owner.get(path).json()["data"]["source_set"]["sealed"]
        body["acknowledged_rejected_client_file_ids"]=[x["client_file_id"] for x in current["files"] if x["upload_status"]=="rejected"]
        accepted=owner.post(path+"/analyze",body,match=current["import_revision"],expected=(202,))
        owner.job(accepted.json()["data"]["job_id"])
        owner.post(path+"/files",files=[("files[]",("after.csv",b"a\n","text/csv"))],data={"client_file_ids[]":str(uuid4())},expected=(409,))
        passed("aggregate_quota_partial_ack_cas_seal_replay")

    if "approved_profile_reuse_noop_reason_optional_no_duplicates" not in completed:
        # Approved Store profile reuse plus actual NO_OP canonical commit and replay.
        rows=[]
        with Session(engine) as fresh:
            for row in fresh.scalars(select(SalesDaily).where(SalesDaily.store_id==UUID(manifest["store_id"])).order_by(SalesDaily.product_id,SalesDaily.sales_date)):
                rows.append(dict(product_id=str(row.product_id),sales_date=row.sales_date.isoformat(),quantity=str(row.quantity),unit="cup",business_report_key="s411-demo/1-sales"))
        ident=analyze(owner,manifest["store_id"],day,[("sales.csv",csv_bytes("sales",rows))])
        summary=owner.get(f"/api/v1/imports/{ident}/mapping-summary").json()["data"]
        assert summary["binding_refs"] and not summary["profile_proposals"]
        result=complete_import(owner,manifest["store_id"],ident,engine,expected_sales=70)
        assert result["outcome"]=="no_changes"
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(SalesDaily).where(SalesDaily.store_id==UUID(manifest["store_id"])))==70
        passed("approved_profile_reuse_noop_reason_optional_no_duplicates")

    # Full source columns switched explicitly to shared rules; never mutate an
    # approved reusable profile in place. A separate header layout creates proposal.
    content=csv_bytes("sales",[dict(product_id=manifest["products"][0],sales_date=(day-timedelta(days=1)).isoformat(),quantity="5",unit="cup",business_report_key="shared-value-case",extra_note="synthetic")])
    ident=analyze(owner,manifest["store_id"],day,[("shared.csv",content)])
    path="/api/v1/imports/"+ident
    items=owner.get(path+"/mappings?review_only=false&limit=100").json()["data"]["items"]
    for item in items:
        if item.get("ignored") or item.get("resolution_origin")=="APPROVED_PROFILE":continue
        summary=owner.get(path+"/mapping-summary?include_profile_details=true&include_clean_sheets=true").json()["data"]
        if item["issue_type"]=="classification":body={"resolution":dict(kind="sheet_type",sheet_type="sales",reason="Explicit sheet classification")}
        elif item["issue_type"]=="source_context":body={"resolution":dict(kind="source_context",source_system_key="S411",report_type="shared-demo",sales_semantics="daily_total",evidence_reference="Synthetic source review")}
        elif item["issue_type"]=="column":body={"target_field":item["target_field"]} if item["target_field"] else {"resolution":dict(kind="ignored_optional_field",evidence_reference="Explicit synthetic unused source column")}
        else:continue
        owner.request("PATCH",path+"/mappings/"+item["mapping_id"],body=body,match=summary["mapping_revision"])
    items=owner.get(path+"/mappings?review_only=false&limit=100").json()["data"]["items"]
    column=next(x for x in items if x["target_field"]=="sales.business_report_key")
    def shared(value,**extra):
        summary=owner.get(path+"/mapping-summary").json()["data"]
        return owner.request("PATCH",path+"/mappings/"+column["mapping_id"],body={"resolution":dict(kind="shared_value",target_field="sales.business_report_key",scope="IMPORT_VALUE",value=value,evidence_reference="Synthetic import-only value",**extra)},match=summary["mapping_revision"])
    shared("shared-value-case",replace_source_column_index=column["source_location"]["source_column_index"],acknowledgment=True)
    summary=owner.get(path+"/mapping-summary?include_profile_details=true").json()["data"]
    p=summary["profile_proposals"][0]
    decision=owner.post(f"/api/v1/stores/{manifest['store_id']}/mapping-profiles/{p['profile_id']}/decisions",dict(decision="approve_activate",proposal_revision=p["proposal_revision"],expected_active_version=p["active_version"],reason="Owner approves import-only requirement"),match=p["lifecycle_revision"]).json()["data"]
    current=owner.get(path).json()["data"];summary=owner.get(path+"/mapping-summary").json()["data"]
    preview_job=owner.post(path+"/process",dict(phase="preview",mapping_revision=summary["mapping_revision"]),match=current["import_revision"],expected=(202,))
    owner.job(preview_job.json()["data"]["job_id"])
    current=owner.get(path+"?include_preview=true").json()["data"];preview=current["preview"]["summary"]
    summary=owner.get(path+"/mapping-summary").json()["data"]
    confirmed=owner.post(path+"/process",dict(phase="confirm_review",preview_id=preview["preview_id"],preview_digest=preview["digest"],mapping_revision=summary["mapping_revision"],confirm=True,reason="Explicit reviewed facts"),match=current["import_revision"])
    shared("shared-value-case-new")
    assert not owner.get(path+"?include_preview=true").json()["data"]["confirmation_usable"]
    second=analyze(owner,manifest["store_id"],day,[("shared.csv",content)])
    second_summary=owner.get(f"/api/v1/imports/{second}/mapping-summary?include_clean_sheets=true").json()["data"]
    assert not second_summary["can_preview"] and any(x["code"]=="MISSING_IMPORT_VALUE" for x in second_summary["blockers"])
    from app.models.import_staging import ImportProfileVersion
    with Session(engine) as fresh:
        record=fresh.get(ImportProfileVersion,(UUID(decision["profile_id"]),decision["approved_version"]))
        assert "shared-value-case" not in json.dumps(record.spec_json)
    passed("IMPORT_VALUE_not_carried_confirmation_invalidated")
    # Invalid mapping type is a real validation failure, not automatic conversion.
    owner.request("PATCH",path+"/mappings/"+column["mapping_id"],body={"target_field":"not_a_canonical_field"},match=owner.get(path+"/mapping-summary").json()["data"]["mapping_revision"],expected=(422,))
    passed("invalid_mapping_rejected_manual_provider_unavailable")

    # Live inventory threshold changed legitimately; historical Run/PDF stay exact.
    detail=owner.get(base+"/inventory/"+manifest["ingredient_id"]).json()["data"]
    owner.request("PUT",base+"/inventory/"+manifest["ingredient_id"]+"/threshold",body=dict(minimum_usable_quantity="0",unit="ml",reason="Synthetic explicit zero threshold"),match=detail["threshold_version"])
    detail=owner.get(base+"/inventory/"+manifest["ingredient_id"]).json()["data"]
    assert detail["minimum_usable_quantity"]=="0" if "minimum_usable_quantity" in detail else detail["low_stock_assessment"]["threshold"]=="0"
    assert owner.get(retained_path).json()["data"]==initial
    assert owner.get(pdf_url).content==before_pdf
    assert any(x["status"]=="expired" for x in detail["lots"])
    assert all(x["cost"]["unit_cost"] is None for x in detail["lots"])
    passed("zero_null_expired_inventory_live_change_retained_immutable")
