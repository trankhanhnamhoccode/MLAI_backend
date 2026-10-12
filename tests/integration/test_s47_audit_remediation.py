"""Approved audit boundaries; real shelfcash_test transactions, no provider."""
from datetime import timedelta
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_stock_writes import stock, request, receive, detail
from tests.integration.test_import_staging import imp, post, analyzed, approved, previewed
from tests.integration.test_import_commit import ready, finished
from tests.integration.test_import_classification import mapping, listing, confirm
from app.models import Ingredient, InventoryMovement, InventoryLot, StoreMembership
from app.models.auth import MembershipGrant
from app.models.import_staging import ImportProfileVersion, ImportBatch


def test_late_receipt_with_newer_event_is_allowed_but_old_opening_fresh_cas_is_not(stock):
    assert receive(stock, request(stock, "ACTUAL_RECEIPT")).status_code == 201
    # Current MAC is fresh, but observation predates the canonical event's recorded_at.
    old = request(stock, identity="new-physical-source")
    response = receive(stock, old, {**stock[3], "Idempotency-Key": str(uuid4())})
    assert response.status_code == 409 and response.json()["error"]["code"] == "STALE_STOCK_OBSERVATION"
    late = request(stock, "ACTUAL_RECEIPT", "late-event")
    late["observed_at"] = (stock[0][4][0] - timedelta(days=2)).isoformat()
    late["received_date"] = "2026-10-08"
    response = receive(stock, late, {**stock[3], "Idempotency-Key": str(uuid4())})
    assert response.status_code == 201, response.text
    value = response.json()["data"]
    assert "LATE_RECEIPT_RECORDED" in {w["code"] for w in value["warnings"]}
    assert value["movement"]["occurred_at"] < value["movement"]["recorded_at"]
    assert receive(stock, late, {**stock[3], "Idempotency-Key": str(uuid4())}).json()["data"] == value
    with Session(stock[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 2


def test_other_ingredient_event_does_not_invalidate_opening_and_existing_lot_is_not_added_again(stock):
    other = uuid4()
    with Session(stock[0][1]) as s:
        s.add(Ingredient(id=other, store_id=stock[1].store_id, name="Other", base_unit="l")); s.commit()
    body = request(stock, "ACTUAL_RECEIPT", "other")
    body["ingredient_id"] = str(other)
    assert receive(stock, body).status_code == 201
    response = receive(stock, request(stock), {**stock[3], "Idempotency-Key": str(uuid4())})
    assert response.status_code == 201, response.text
    # Simulate a new physical observation after all server-recorded timestamps.
    with Session(stock[0][1]) as s:
        later = s.scalar(select(func.max(InventoryLot.updated_at))) + timedelta(seconds=1)
    stock[0][4][0] = later
    from tests.integration.test_auth_public import login
    wire = login(stock[0]).json()["data"]
    headers = {**stock[3], "X-CSRF-Token": wire["session"]["csrf_token"], "Idempotency-Key": str(uuid4())}
    repeated = request(stock, identity="invented-new-key"); repeated["observed_at"] = later.isoformat()
    response = receive(stock, repeated, headers)
    assert response.status_code == 409 and response.json()["error"]["code"] == "OPENING_STOCK_ALREADY_RECORDED"


def test_concurrent_receipt_and_opening_cannot_use_same_stale_current_balance(stock):
    svc = stock[0][5].app.state.stock_writes
    token = stock[0][5].cookies.get("__Host-shelfcash_session")
    from app.application.contracts.stock_writes import StockReceiptRequest
    opening = request(stock, identity="opening")
    actual = {**opening, "origin": "ACTUAL_RECEIPT", "receipt_identity": dict(source_system_key="receipt", source_record_id="event")}
    def write(body):
        from app.application.contracts.auth import AuthError
        try:
            return svc.receive(token, stock[1].store_id, StockReceiptRequest(**body), str(uuid4()), stock[3]["X-CSRF-Token"])
        except AuthError as e:
            return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (opening, actual)))
    assert sum(isinstance(r, tuple) for r in results) == 1
    assert "INVENTORY_VERSION_CONFLICT" in results
    with Session(stock[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(InventoryLot)) == 1


def test_pure_insert_commit_does_not_require_user_reason(imp):
    ident, read, revision = ready(imp)
    response = post(imp, "/imports/" + ident + "/process", dict(phase="commit",
        preview_id=read["preview"]["summary"]["preview_id"], preview_digest=read["preview"]["summary"]["digest"],
        confirm=True, resolutions=[]), match=revision)
    assert finished(imp, ident, response)["outcome"] == "committed"


def test_money_and_long_quantity_persist_exact_without_scale_rounding(stock):
    from decimal import Decimal
    from app.application.use_cases.catalog import ProductUseCases
    from app.application.contracts.catalog import CreateProductInput
    from app.models import Product
    money = "999999999999999999.123456789012345678"
    quantity = "0." + "0" * 190 + "12345"
    with Session(stock[0][1]) as s:
        product = ProductUseCases(s).create(CreateProductInput(store_id=stock[1].store_id,
            name="Exact monetary product", selling_unit="cup", price=money))
    body = request(stock, quantity=quantity); body["unit_cost"] = money
    response = receive(stock, body)
    assert response.status_code == 201, response.text
    with Session(stock[0][1]) as s:
        assert s.get(Product, product.id).price == Decimal(money)
        lot = s.scalar(select(InventoryLot))
        assert lot.unit_cost == Decimal(money) and lot.on_hand_quantity == Decimal(quantity)


def test_staff_ignore_own_sheet_without_owner_does_not_change_profile_and_invalidates_review(imp):
    ident = analyzed(imp); approved(imp, ident)
    read = previewed(imp, ident); assert confirm(imp, ident, read).status_code == 200
    with Session(imp[0][1]) as s:
        before = [r.spec_json for r in s.scalars(select(ImportProfileVersion))]
        member = s.scalar(select(StoreMembership).where(StoreMembership.user_id == imp[1].user_id))
        member.role = "STAFF"
        from app.domain.permissions import PERMISSIONS
        s.add_all(MembershipGrant(membership_id=member.id, permission=p) for p in PERMISSIONS)
        s.commit()
    issue = next(i for i in listing(imp, ident) if i["issue_type"] == "classification")
    response = mapping(imp, ident, issue, dict(resolution=dict(kind="sheet_type", sheet_type=None,
        ignored=True, acknowledgment=True, reason="Staff explicitly excludes this source sheet")))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["approval_required"] is False
    with Session(imp[0][1]) as s:
        assert [r.spec_json for r in s.scalars(select(ImportProfileVersion))] == before
        batch = s.get(ImportBatch, UUID(ident))
        assert not batch.analysis_json.get("confirmation")
        assert batch.mapping_revision != read["_mapping_revision"]
    summary = imp[0][5].get("/api/v1/imports/" + ident + "/mapping-summary")
    assert summary.status_code == 200, summary.text
    assert not any(b["code"] == "MAPPING_APPROVAL_REQUIRED" for b in summary.json()["data"]["blockers"])


def test_ignore_cannot_change_completed_batch_and_does_not_release_source_quota(imp):
    from tests.integration.test_import_commit import commit
    ident, read, revision = ready(imp)
    before=imp[0][5].get("/api/v1/imports/"+ident).json()["data"]["quota"]
    finished(imp,ident,commit(imp,ident,read,revision))
    issue=next(i for i in listing(imp,ident) if i["issue_type"]=="classification")
    response=mapping(imp,ident,issue,dict(resolution=dict(kind="sheet_type",sheet_type=None,ignored=True,
        acknowledgment=True,reason="Attempt to change completed scope")))
    assert response.status_code==409 and response.json()["error"]["code"]=="IMPORT_STATE_CONFLICT"
    assert imp[0][5].get("/api/v1/imports/"+ident).json()["data"]["quota"]==before


def test_staff_cannot_ignore_another_actors_batch_even_with_grants(imp):
    ident=analyzed(imp);approved(imp,ident)
    from tests.integration.test_auth_public import setup,login
    other=setup(imp[0],"other-staff@example.test",store=False)
    from app.domain.permissions import PERMISSIONS
    with Session(imp[0][1]) as s:
        member=StoreMembership(user_id=other.user_id,store_id=imp[1].store_id,role="STAFF")
        s.add(member);s.flush()
        s.add_all(MembershipGrant(membership_id=member.id,permission=p) for p in PERMISSIONS);s.commit()
    wire=login(imp[0],"other-staff@example.test").json()["data"]
    imp[3]["X-CSRF-Token"]=wire["session"]["csrf_token"]
    issue=next(i for i in listing(imp,ident) if i["issue_type"]=="classification")
    response=mapping(imp,ident,issue,dict(resolution=dict(kind="sheet_type",sheet_type=None,ignored=True,
        acknowledgment=True,reason="Not my batch")))
    assert response.status_code==403,response.text


def test_sales_correction_http_requires_effective_action_reason_before_acceptance(imp):
    from datetime import date
    from app.models import SalesDaily
    with Session(imp[0][1]) as s:
        s.add(SalesDaily(store_id=imp[1].store_id,product_id=imp[4],sales_date=date(2026,10,9),quantity=100));s.commit()
    ident,read,revision=ready(imp)
    row=read["preview"]["rows"][0];assert row["proposed_action"]=="REPLACE_DAILY_TOTAL"
    body=dict(phase="commit",preview_id=read["preview"]["summary"]["preview_id"],preview_digest=read["preview"]["summary"]["digest"],
        confirm=True,resolutions=[dict(row_id=row["row_id"],action="replace_daily_total",
            report_business_key=row["after"]["business_report_key"],evidence_reference="Checked full-day report",
            reason="Correct source total",disjoint_assertion=None)])
    response=post(imp,"/imports/"+ident+"/process",body,match=revision)
    assert response.status_code==422 and response.json()["error"]["code"]=="COMMIT_REASON_REQUIRED"
    with Session(imp[0][1]) as s:assert s.scalar(select(SalesDaily.quantity))==100
    response=post(imp,"/imports/"+ident+"/process",{**body,"reason":"Correct reviewed daily total"},match=revision)
    assert finished(imp,ident,response)["updated_resources"]["sales"]["changed_record_count"]==1
