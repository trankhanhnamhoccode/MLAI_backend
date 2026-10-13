"""S4.6 synthetic HTTP/job/real PG acceptance; no live provider or development DB."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, csv_source
from tests.integration.test_import_commit import no_live_provider, ready, commit, finished
from app.models import Ingredient, InventoryLot, InventoryMovement
from app.application.use_cases.inventory import InventoryUseCases
from app.application.contracts.inventory import ReceiveInventoryInput
from tests.integration.test_import_staging import approved, previewed, post
from tests.integration.test_import_commit import analyzed_files, confirm
from app.models import Supplier, SupplierTerm, SalesDaily
from app.models.operational_import import SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord

def approve_all(imp,ident,**kwargs):
    approved(imp,ident,**kwargs)
    client=imp[0][5]
    while True:
        summary=client.get(f"/api/v1/imports/{ident}/mapping-summary?include_profile_details=true").json()["data"]
        remaining=[p for p in summary["profile_proposals"] if p["active_version"] is None]
        if not remaining:return summary
        p=remaining[0]
        response=post(imp,f"/stores/{imp[1].store_id}/mapping-profiles/{p['profile_id']}/decisions",
            dict(decision="approve_activate",proposal_revision=p["proposal_revision"],expected_active_version=None,reason="Review full supplier source"),match=p["lifecycle_revision"])
        assert response.status_code==200,response.text

def supplier_sources(imp):
    ingredient,lot=existing_lot(imp)
    supplier=uuid4()
    with Session(imp[0][1]) as s:
        s.add(Supplier(id=supplier,store_id=imp[1].store_id,name="Supplier synthetic",active=True));s.commit()
    sources=[("supplier.csv",csv_source("suppliers",[dict(source_supplier_key=str(supplier),name="Supplier synthetic",active=True)])),
        ("terms.csv",csv_source("supplier_terms",[dict(source_term_key="TERM-1",supplier_id=str(supplier),ingredient_id=str(ingredient),
            effective_from="2026-10-10",effective_to=None,unit="l",pack_size_base_quantity="6",pack_cost="100",currency="VND",
            minimum_order_quantity="1", price_basis="PER_PACK", price_quantity=None, price_unit=None, moq_basis="PACKS", moq_unit=None,lead_time_days=1,shelf_life_days=None,active=True,maximum_order_base_quantity=None)])),
        ("fees.csv",csv_source("payable_fees",[dict(source_fee_key="FEE-1",scope="STORE_PROCUREMENT",effective_from="2026-10-10",
            effective_to=None,mode="NONE",coverage="COMPLETE",currency="VND",components=[],covered_source_term_keys=["TERM-1"],
            covered_source_supplier_keys=[str(supplier)],evidence_reference="Supplier explicitly has no fees",reason="Reviewed full fee schedule")])),
        ("declaration.csv",csv_source("scope_declarations",[dict(source_declaration_key="COUNT-SCOPE",declaration=dict(kind="INVENTORY",
            ingredient_id=str(ingredient),state="COMPLETE_CURRENT_LOTS",observed_at=imp[0][4][0].isoformat(),covered_lot_ids=[str(lot)],evidence_reference="Whole lot count reviewed"))]))]
    return ingredient,lot,supplier,sources

def configuration_ready(imp,sources,context=None):
    ident=analyzed_files(imp,list(reversed(sources)))
    supplier=imp[0][5].get(f"/api/v1/imports/{ident}/mappings?review_only=false&limit=100").json()["data"]["items"]
    supplier=next((i["samples"][0] for i in supplier if i["code"]=="UNKNOWN_SUPPLIER"),None)
    approve_all(imp,ident,report="supplier-import",context={"inventory_semantics":"lot_stock_count",**(context or {})},
        resolutions={"UNKNOWN_SUPPLIER":dict(kind="identity_binding",canonical_id=supplier)} if supplier else None)
    read=previewed(imp,ident)
    response=confirm(imp,ident,read)
    assert response.status_code==200,response.text
    return ident,read,response.json()["data"]["import_revision"]

def test_multi_schema_supplier_terms_explicit_none_fee_and_declaration_atomic_commit(imp):
    ingredient,lot,supplier,sources=supplier_sources(imp)
    ident,read,revision=configuration_ready(imp,sources)
    assert read["preview"]["summary"]["blockers"]==[],read["preview"]
    result=finished(imp,ident,commit(imp,ident,read,revision))
    assert result["updated_resources"]["terms"]["created_count"]==1
    assert result["updated_resources"]["fees"]["created_count"]==1
    assert result["updated_resources"]["declarations"]["created_count"]==1
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SupplierSourceRecord))==1
        term=s.scalar(select(SupplierTerm));assert term.pack_size_base_quantity==6 and term.pack_cost==100
        assert s.get(TermSourceRecord,term.id).payload["source_term_key"]=="TERM-1"
        fee=s.scalar(select(PayableFeeRecord));assert fee.payload["mode"]=="NONE" and fee.payload["components"]==[]
        assert str(term.id) in fee.resolved_references["terms"]
        assert s.scalar(select(ScopeDeclarationRecord)).payload["declaration"]["state"]=="COMPLETE_CURRENT_LOTS"
    configuration=imp[0][5].get(f"/api/v1/imports/{ident}?include=configurations").json()["data"]["configurations"]
    assert all(row["state"]=="committed" for name in ("terms","fees","declarations") for row in configuration[name])

def mixed_ready(imp):
    ingredient,lot,supplier,sources=supplier_sources(imp)
    sources += [("count.csv",csv_source("inventory_count",[dict(ingredient_id=str(ingredient),lot_id=str(lot),on_hand="10",unit="l",
        observed_at=imp[0][4][0].isoformat(),reason="All lots physically counted")])),
        ("sales.csv",csv_source("sales",[dict(product_id=str(imp[4]),sales_date="2026-10-09",quantity="12",unit="cup",business_report_key="SOURCE-MIXED")]))]
    return (ingredient,lot,supplier),configuration_ready(imp,sources)

def test_all_domains_rollback_if_last_declaration_writer_fails(imp,monkeypatch):
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    from app.models.import_staging import ImportAudit,ImportJob
    identities,(ident,read,revision)=mixed_ready(imp)
    response=commit(imp,ident,read,revision);assert response.status_code==202,response.text
    from app.application.contracts.auth import AuthError
    def fail(*args,**kwargs):raise AuthError("PREVIEW_STALE",409)
    monkeypatch.setattr(OperationalConfiguration,"declaration",fail)
    imp[2].run_one()
    with Session(imp[0][1]) as s:
        assert s.get(InventoryLot,identities[1]).on_hand_quantity==12
        assert s.scalar(select(func.count()).select_from(InventoryMovement))==1
        for model in (SupplierSourceRecord,SupplierTerm,TermSourceRecord,PayableFeeRecord,ScopeDeclarationRecord,SalesDaily):
            assert s.scalar(select(func.count()).select_from(model))==0
        assert s.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind=="IMPORT_CANONICAL_COMMITTED"))==0
        assert s.get(ImportJob,UUID(response.json()["data"]["job_id"])).status=="failed"

def test_mixed_commit_lost_ack_is_reconciled_and_public_count_scope_invalidates_on_new_lot(imp,monkeypatch):
    from app.models.import_staging import ImportAudit
    from app.application.use_cases.public_reads import PublicReads
    from app.application.use_cases.stock_writes import StockWrites
    from app.application.contracts.stock_writes import StockReceiptRequest
    identities,(ident,read,revision)=mixed_ready(imp)
    original=Session.commit;lost=[]
    def commit_lost(session):
        success=any(isinstance(r,ImportAudit) and r.kind=="IMPORT_CANONICAL_COMMITTED" for r in session.new)
        original(session)
        if success and not lost:lost.append(True);raise RuntimeError("Synthetic committed response loss")
    monkeypatch.setattr(Session,"commit",commit_lost)
    key=str(uuid4())
    accepted=commit(imp,ident,read,revision,key=key)
    result=finished(imp,ident,accepted)
    replay=commit(imp,ident,read,revision,key=key)
    assert replay.status_code==202 and replay.json()["data"]==accepted.json()["data"]
    assert imp[2].run_one() is None
    assert imp[0][5].get("/api/v1/imports/"+ident+"/completion").json()["data"]==result
    assert lost and result["updated_resources"]["inventory"]["updated"]
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(InventoryMovement))==2
        assert s.scalar(select(func.count()).select_from(InventoryLot))==1
        from app.repositories.import_staging import read_set_in_session
        from app.application.operational_import_facts import inventory_dependency
        snapshot,_=read_set_in_session(s,imp[1].store_id,("scope_declarations.INVENTORY",))
        declaration=s.scalar(select(ScopeDeclarationRecord))
        assert declaration.dependency_digest==inventory_dependency(snapshot,identities[0]), (declaration.dependency_digest,inventory_dependency(snapshot,identities[0]),snapshot["inventory_lots"])
        from sqlalchemy import literal_column
        from app.repositories.import_staging import json_value
        projected={}
        for model in (Ingredient,InventoryLot):
            records=s.execute(select(*[c for c in model.__table__.columns if c.name != "unit_cost"],literal_column("xmin::text").label("_row_version")).where(model.store_id==imp[1].store_id).order_by(model.id)).mappings().all()
            projected[model.__tablename__]=[{key:json_value(value) for key,value in r.items()} for r in records]
        differences=[(table,key,str(row.get(key)),str(other.get(key))) for table,records in projected.items()
            for row,other in zip(records,snapshot[table]) for key in set(row)|set(other)
            if key!="unit_cost" and row.get(key)!=other.get(key)]
        assert not differences,differences
    reads=PublicReads(imp[0][2]);imp[0][5].app.state.public_reads=reads
    imp[0][5].app.state.stock_writes=StockWrites(imp[0][2],reads)
    path=f"/api/v1/stores/{imp[1].store_id}/inventory/{identities[0]}"
    current=imp[0][5].get(path).json()
    assert current["data"]["on_hand_quantity"]=="10" and current["data"]["stock_completeness"]=="CONFIRMED"
    response=imp[0][5].post(f"/api/v1/stores/{imp[1].store_id}/inventory/receipts",headers={**imp[3],"Idempotency-Key":str(uuid4())},
        json=dict(origin="ACTUAL_RECEIPT",receipt_identity=dict(source_system_key="new-actual",source_record_id="new-lot"),
            ingredient_id=str(identities[0]),supplier_id=None,lot_code=None,quantity="1",unit="l",received_date=None,expiry_date=None,
            unit_cost=None,currency="VND",observed_at=imp[0][4][0].isoformat(),reason="New received lot",expected_inventory_version=current["meta"]["data_version"]))
    assert response.status_code==201,response.text
    assert imp[0][5].get(path).json()["data"]["stock_completeness"]=="UNKNOWN"
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SupplierTerm))==1
        assert s.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind=="IMPORT_CANONICAL_COMMITTED"))==1

@pytest.mark.parametrize("permission",["inventory.count.correct","supplier.fees.manage","supplier.terms.create","sales.record"])
def test_mixed_commit_rechecks_all_domain_rights_before_execution(imp,permission):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.models.import_staging import ImportJob
    from app.domain.permissions import PERMISSIONS
    identities,(ident,read,revision)=mixed_ready(imp)
    response=commit(imp,ident,read,revision);assert response.status_code==202,response.text
    with Session(imp[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==imp[1].store_id));member.role="STAFF"
        s.add_all(MembershipGrant(membership_id=member.id,permission=p) for p in sorted(PERMISSIONS-{permission}));s.commit()
    imp[2].run_one()
    with Session(imp[0][1]) as s:
        job=s.get(ImportJob,UUID(response.json()["data"]["job_id"]))
        assert job.status=="failed" and job.error_json["code"]=="PERMISSION_DENIED"
        assert s.get(InventoryLot,identities[1]).on_hand_quantity==12
        assert s.scalar(select(func.count()).select_from(SupplierTerm))==0

def test_future_terms_and_fee_changes_require_exact_owner_amendments_and_executor_confirmation(imp):
    from sqlalchemy import text
    import csv,io,json
    ingredient,lot,supplier,sources=supplier_sources(imp)
    ident,read,revision=configuration_ready(imp,sources)
    finished(imp,ident,commit(imp,ident,read,revision))
    with Session(imp[0][1]) as s:
        term,xmin=s.execute(select(SupplierTerm,text("xmin::text"))).one()
        fee,fxmin=s.execute(select(PayableFeeRecord,text("xmin::text"))).one()
        policy=dict(term_period_amendments=[dict(supplier_term_id=str(term.id),expected_version=xmin,effective_to="2026-10-10",reason="New future price")],
            fee_period_amendments=[dict(fee_id=str(fee.id),expected_version=fxmin,effective_to="2026-10-10",reason="New future fee schedule")])
        old_term_id,old_fee_id=term.id,fee.id
        new_term=s.get(TermSourceRecord,term.id).payload.copy();new_term.pop("domain");new_term.update(minimum_order_quantity=str(new_term.pop("minimum_order_packs")), price_basis="PER_PACK", price_quantity=None, price_unit=None, moq_basis="PACKS", moq_unit=None, effective_from="2026-10-11",pack_cost="105")
        new_fee=fee.payload.copy();new_fee.pop("domain");new_fee.update(effective_from="2026-10-11",mode="PER_OFFER",components=[dict(component_key="DELIVERY",label="Delivery",basis="PER_OFFER",source_term_key="TERM-1",source_supplier_key=None,amount="5",condition="WHEN_ORDERED")])
    sources=[("new-terms.csv",csv_source("supplier_terms",[dict(reversed(list(new_term.items())))])),
        ("new-fees.csv",csv_source("payable_fees",[dict(reversed(list(new_fee.items())))]))]
    ident,read,revision=configuration_ready(imp,sources,policy)
    rows=read["preview"]["rows"]
    assert {r["proposed_action"] for r in rows}=={"AMEND_TERM_PERIOD","CREATE_SUPPLIER_TERM","AMEND_FEE_PERIOD","CREATE_FEE_DECLARATION"},rows
    assert commit(imp,ident,read,revision).status_code==422
    confirmation=[dict(action_id=r["row_id"],reason="Executor confirms pinned future change") for r in rows if r["confirmation_required"]]
    response=post(imp,f"/imports/{ident}/process",dict(phase="commit",preview_id=read["preview"]["summary"]["preview_id"],preview_digest=read["preview"]["summary"]["digest"],confirm=True,reason="Future price/fee periods reviewed",resolutions=[],supplier_changes=confirmation),match=revision)
    result=finished(imp,ident,response)
    with Session(imp[0][1]) as s:
        old=s.get(SupplierTerm,old_term_id);assert str(old.effective_to)=="2026-10-10" and old.pack_cost==100
        new=s.scalar(select(SupplierTerm).where(SupplierTerm.version==2));assert new.pack_cost==105 and str(new.effective_from)=="2026-10-11"
        assert s.get(PayableFeeRecord,old_fee_id).payload["effective_to"] is None
        fees=s.scalars(select(PayableFeeRecord).order_by(PayableFeeRecord.version)).all()
        assert len(fees)==3 and fees[1].payload["effective_to"]=="2026-10-10" and fees[2].payload["components"][0]["amount"]=="5"
    configuration=imp[0][5].get(f"/api/v1/imports/{ident}?include=configurations").json()["data"]["configurations"]
    assert sorted(row["internal_term_version"] for row in configuration["terms"])==[1,2]
    assert all(row["state"]=="committed" for row in configuration["fees"])

def test_sales_coverage_and_procurement_nested_declarations_are_stored_without_readiness_execution(imp):
    ingredient,lot,supplier,sources=supplier_sources(imp)
    proc=dict(kind="PROCUREMENT_CONTEXT",effective_from="2026-10-10",effective_to=None,committed_inbound_state="CONFIRMED_NONE",
        no_additional_orders_state="CONFIRMED_NONE",capacity_state="DECLARED",capacities=[dict(ingredient_id=str(ingredient),unit="l",maximum_quantity="20",checkpoint="POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION")],
        supplier_limit_state="DECLARED",supplier_limits=[dict(supplier_id=str(supplier),ingredient_id=str(ingredient),unit="l",maximum_quantity="18",scope="ONE_ORDER_SUPPLIER_INGREDIENT")],evidence_reference="Owner reviewed capacity and order limits")
    sales_scope=dict(kind="SALES_COVERAGE",product_ids=[str(imp[4])],from_date="2026-10-09",to_date="2026-10-10",state="COMPLETE",evidence_reference="Daily counts include explicit zero day")
    sources += [("sales-declarations.csv",csv_source("scope_declarations",[dict(source_declaration_key="SALES-COMPLETE",declaration=sales_scope),dict(source_declaration_key="PROC-CONTEXT",declaration=proc)])),
        ("sales.csv",csv_source("sales",[dict(product_id=str(imp[4]),sales_date=d,quantity=q,unit="cup",business_report_key="EXPLICIT-"+d) for d,q in (("2026-10-09","12"),("2026-10-10","0"))]))]
    ident,read,revision=configuration_ready(imp,sources)
    result=finished(imp,ident,commit(imp,ident,read,revision))
    reference=next(ref for ref in result["canonical_references"] if ref["canonical_domain"]=="scope_declarations" and ref["nested_provenance"])
    assert {p["path"] for p in reference["nested_provenance"]}=={"declaration.capacities[0]","declaration.supplier_limits[0]"}
    assert {ref["path"] for ref in reference["nested_references"]}=={"declaration.capacities[0].ingredient_id","declaration.supplier_limits[0].ingredient_id","declaration.supplier_limits[0].supplier_id"}
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SalesDaily))==2
        declarations=s.scalars(select(ScopeDeclarationRecord)).all()
        assert {d.payload["declaration"]["kind"] for d in declarations}=={"INVENTORY","SALES_COVERAGE","PROCUREMENT_CONTEXT"}
        assert all(d.dependency_digest.startswith("sha256:") for d in declarations)
    assert all(action["result_assessment"]=="NOT_ASSESSED" and action["can_execute"] is True for action in result["readiness"]["actions"])

def test_concurrent_mixed_imports_with_same_read_set_have_one_success_and_one_stale(imp):
    from concurrent.futures import ThreadPoolExecutor
    from app.models.import_staging import ImportJob,ImportAudit
    ingredient,lot,supplier,sources=supplier_sources(imp)
    first,read,revision=configuration_ready(imp,sources)
    second=analyzed_files(imp,list(reversed(sources)))
    other=previewed(imp,second)
    review=confirm(imp,second,other);assert review.status_code==200,review.text
    accepted=[commit(imp,first,read,revision),commit(imp,second,other,review.json()["data"]["import_revision"])]
    assert all(r.status_code==202 for r in accepted)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=list(pool.map(lambda _:imp[2].run_one(),range(2)))
    # The retained local worker contract permits a caller to observe single-flight
    # busy and return None. Drain the remaining queued job after that claim finishes.
    jobs=[j for j in jobs if j is not None]
    if len(jobs)==1:jobs.append(imp[2].run_one())
    assert set(jobs)=={UUID(r.json()["data"]["job_id"]) for r in accepted}
    with Session(imp[0][1]) as s:
        rows=[s.get(ImportJob,j) for j in jobs]
        assert sorted(j.status for j in rows)==["completed","failed"]
        assert next(j for j in rows if j.status=="failed").error_json["code"]=="PREVIEW_STALE"
        assert s.scalar(select(func.count()).select_from(SupplierTerm))==1
        assert s.scalar(select(func.count()).select_from(PayableFeeRecord))==1
        assert s.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind=="IMPORT_CANONICAL_COMMITTED"))==1

def test_same_declared_scope_gets_new_revision_after_same_batch_count_and_zero_threshold_projects_empty(imp):
    from datetime import timedelta
    from app.application.use_cases.public_reads import PublicReads
    from app.application.use_cases.stock_writes import StockWrites
    imp[0][4][0]=datetime.now(timezone.utc)+timedelta(minutes=2)
    from tests.integration.test_auth_public import login
    wire=login(imp[0]).json()["data"]
    imp[3]["X-CSRF-Token"]=wire["session"]["csrf_token"]
    ingredient,lot,supplier,sources=supplier_sources(imp)
    observation=imp[0][4][0].isoformat()
    def count(quantity):return ("count.csv",csv_source("inventory_count",[dict(ingredient_id=str(ingredient),lot_id=str(lot),on_hand=quantity,unit="l",observed_at=observation,reason="Physical count reviewed")]))
    sources.append(count("10"))
    ident,read,revision=configuration_ready(imp,sources)
    finished(imp,ident,commit(imp,ident,read,revision))
    other=analyzed_files(imp,[count("0"),sources[3]])
    read=previewed(imp,other);review=confirm(imp,other,read)
    assert review.status_code==200,review.text
    result=finished(imp,other,commit(imp,other,read,review.json()["data"]["import_revision"]))
    assert result["updated_resources"]["declarations"]["changed_count"]==1
    with Session(imp[0][1]) as s:
        assert len(s.scalars(select(ScopeDeclarationRecord)).all())==2
        assert s.get(InventoryLot,lot).on_hand_quantity==0
    reads=PublicReads(imp[0][2]);imp[0][5].app.state.public_reads=reads;imp[0][5].app.state.stock_writes=StockWrites(imp[0][2],reads)
    path=f"/api/v1/stores/{imp[1].store_id}/inventory/{ingredient}"
    detail=imp[0][5].get(path).json()
    assert detail["data"]["stock_completeness"]=="CONFIRMED" and detail["data"]["status"]=="empty"
    response=imp[0][5].put(path+"/threshold",json=dict(minimum_usable_quantity="0",unit="l",reason="Owner zero threshold"),
        headers={**imp[3],"Idempotency-Key":str(uuid4()),"If-Match":'"'+detail["data"]["threshold_version"]+'"'})
    assert response.status_code==200,response.text
    listing=imp[0][5].get(f"/api/v1/stores/{imp[1].store_id}/inventory?status=empty&limit=1")
    assert listing.status_code==200,listing.text
    data=listing.json()["data"]
    assert data["summary"]["low_stock_ingredient_count"]==1 and data["summary"]["unknown_assessment_ingredient_count"]==0
    assert data["items"][0]["low_stock_assessment"]["status"]=="low" and data["items"][0]["status"]=="empty"

def test_confirmed_empty_declaration_uses_explicit_same_batch_zero_count_not_before_balance(imp):
    ingredient,lot=existing_lot(imp)
    sources=[("count.csv",csv_source("inventory_count",[dict(ingredient_id=str(ingredient),lot_id=str(lot),on_hand="0",unit="l",observed_at=imp[0][4][0].isoformat(),reason="Confirmed no physical stock")])),
        ("empty.csv",csv_source("scope_declarations",[dict(source_declaration_key="EMPTY",declaration=dict(kind="INVENTORY",ingredient_id=str(ingredient),state="CONFIRMED_EMPTY",observed_at=imp[0][4][0].isoformat(),covered_lot_ids=[],evidence_reference="Owner confirms no additional unrecorded stock"))]))]
    ident,read,revision=configuration_ready(imp,sources)
    assert not read["preview"]["summary"]["blockers"],read["preview"]
    finished(imp,ident,commit(imp,ident,read,revision))
    with Session(imp[0][1]) as s:
        assert s.get(InventoryLot,lot).on_hand_quantity==0
        assert s.scalar(select(ScopeDeclarationRecord)).payload["declaration"]["state"]=="CONFIRMED_EMPTY"


def existing_lot(imp):
    ingredient = uuid4()
    observed = datetime(2026, 10, 9, tzinfo=timezone.utc)
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=ingredient, store_id=imp[1].store_id, name="Milk", base_unit="l", expiry_tracking=False, active=True));s.commit()
        result = InventoryUseCases(s).receive(ReceiveInventoryInput(store_id=imp[1].store_id,
            ingredient_id=ingredient, quantity=Decimal(12),unit="l",occurred_at=observed,
            note="Synthetic physical stock"))
        lot = s.get(InventoryLot,result.lot.id);lot.updated_at=observed
        # Synthetic fixed-time receipt precedes the count in occurred and recorded time.
        s.get(InventoryMovement,result.movement.id).created_at=observed
        s.commit()
        return ingredient,result.lot.id


def test_inventory_count_zero_commits_delta_not_receipt_and_retains_provenance(imp):
    ingredient,lot=existing_lot(imp)
    source=dict(ingredient_id=str(ingredient),lot_id=str(lot),on_hand="0",unit="l",
        observed_at=imp[0][4][0].isoformat(),reason="Physical lot count")
    ident,read,revision=ready(imp,csv_source("inventory_count",[source]),report="count",
        context={"inventory_semantics":"lot_stock_count"})
    result=finished(imp,ident,commit(imp,ident,read,revision))
    assert result["updated_resources"]["inventory"]["updated"] is True
    assert result["updated_resources"]["inventory"]["affected_ingredient_count"] == 1
    with Session(imp[0][1]) as fresh:
        assert fresh.get(InventoryLot,lot).on_hand_quantity == 0
        movements=fresh.scalars(select(InventoryMovement).order_by(InventoryMovement.created_at)).all()
        assert len(movements)==2 and movements[-1].movement_type=="COUNT_CORRECTION"
        assert movements[-1].quantity_delta == -12
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==1
    ref=next(r for r in result["canonical_references"] if r["canonical_domain"]=="inventory_count")
    assert ref["canonical_id"]==str(lot) and ref["provenance"]["on_hand"]["source_column_index"] is not None

def test_owner_approved_new_supplier_is_created_once_with_store_source_identity(imp):
    source=dict(source_supplier_key="NEW-SUPPLIER",name="New synthetic supplier",active=False)
    ident,read,revision=ready(imp,csv_source("suppliers",[source]),report="supplier-create",resolutions={
        "UNKNOWN_SUPPLIER":dict(kind="new_entity_proposal",entity="supplier",source_business_key="NEW-SUPPLIER",
            metadata=dict(name=source["name"],active=False),evidence_reference="Owner verified new supplier identity")})
    response=commit(imp,ident,read,revision);result=finished(imp,ident,response)
    assert result["updated_resources"]["suppliers"]["created_count"]==1
    with Session(imp[0][1]) as s:
        supplier=s.scalar(select(Supplier));assert supplier.name==source["name"] and supplier.active is False
        binding=s.scalar(select(SupplierSourceRecord).where(SupplierSourceRecord.store_id==imp[1].store_id,
            SupplierSourceRecord.source_system_key=="POS-A",SupplierSourceRecord.source_record_key=="NEW-SUPPLIER"))
        assert binding.supplier_id==supplier.id and binding.provenance["row"]["source_location"]["source_column_index"] is None
