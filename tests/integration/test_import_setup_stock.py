"""Fresh Store, explicit synthetic Owner facts, public intake and guarded PostgreSQL."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests.integration.test_auth_public import env, setup, login, ORIGIN
from tests.integration.test_import_staging import csv_source, previewed, post
from tests.integration.test_import_commit import analyzed_files, commit, finished, confirm
from tests.integration.test_import_field_value_bindings import summary
from tests.integration.test_import_classification import listing, mapping
from app.application.use_cases.import_staging import ImportStaging
from app.models import Product, Ingredient, InventoryLot, InventoryMovement
from app.models.operational_import import InventoryReceiptRecord


@pytest.fixture
def fresh_store(env):
    env[4][0] = datetime.now(timezone.utc)
    receipt = setup(env)
    wire = login(env).json()["data"]
    service = ImportStaging(env[2], env[0].model_copy(update={"import_llm_suggestions_enabled": False}))
    env[5].app.state.import_staging = service
    context = env, receipt, service, {"Origin": ORIGIN, "X-CSRF-Token": wire["session"]["csrf_token"]}, None
    with Session(env[1]) as session:
        for model in (Product, Ingredient, InventoryLot):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    return context


def review_batch(context, ident, creations=None, bindings=None):
    creations, bindings = creations or {}, bindings or {}
    for _ in range(100):
        items = [i for i in listing(context, ident) if i["status"] not in {"resolved", "auto_mapped"} and not i.get("ignored")]
        if not items:
            break
        item = items[0]
        if item["issue_type"] == "classification":
            sheet = next(sh for sh in summary(context, ident)["sheets"] if sh["sheet_id"] == item["sheet_id"])
            resolution = dict(kind="sheet_type", sheet_type=sheet["selected_type"], reason="Synthetic explicit type")
        elif item["issue_type"] == "source_context":
            resolution = dict(kind="source_context", source_system_key="SETUP", report_type="setup-" + item["sheet_id"][:8],
                evidence_reference="Synthetic Owner setup source", sales_semantics="daily_total", inventory_semantics="lot_stock_count")
        elif item["issue_type"] == "identity":
            token = item["source_header"]
            if token in creations:
                entity, metadata = creations[token]
                resolution = dict(kind="new_entity_proposal", entity=entity, source_business_key=token,
                    metadata=metadata, evidence_reference="Synthetic explicit Owner master facts")
                creations = {k:v for k,v in creations.items() if k != token}
            else:
                reserved = {e["source_business_key"]:e["reserved_canonical_id"] for p in summary(context, ident)["profile_proposals"]
                    for e in (p.get("spec") or {}).get("entity_proposals", ())}
                resolution = dict(kind="identity_binding", canonical_id=str(bindings.get(token) or reserved[token]))
        elif item["issue_type"] == "column" and item["target_field"]:
            response = mapping(context, ident, item, {"target_field":item["target_field"]})
            assert response.status_code == 200, response.text
            continue
        else:
            raise AssertionError(item)
        response = mapping(context, ident, item, {"resolution":resolution})
        assert response.status_code == 200, response.text
    else:
        raise AssertionError("Unresolved setup facts")
    for proposal in summary(context, ident)["profile_proposals"]:
        assert not proposal["missing_fields"], proposal
        response = post(context, f"/stores/{context[1].store_id}/mapping-profiles/{proposal['profile_id']}/decisions",
            dict(decision="approve_activate", proposal_revision=proposal["proposal_revision"],
                expected_active_version=proposal["active_version"], reason="Synthetic Owner full spec approval"),
            match=proposal["lifecycle_revision"])
        assert response.status_code == 200, response.text


def complete(context, ident):
    read = previewed(context, ident)
    assert not read["preview"]["summary"]["blockers"], read["preview"]
    confirmed = confirm(context, ident, read)
    assert confirmed.status_code == 200, confirmed.text
    return read, finished(context, ident, commit(context, ident, read, confirmed.json()["data"]["import_revision"]))


def opening(context, **changes):
    data = dict(source_record_id="MILK-LOT-1", ingredient_id="MILK", supplier_id=None,
        lot_code="LOT-1", quantity="12", unit="l", received_date=None, expiry_date=None,
        unit_cost=None, currency="VND", observed_at=context[0][4][0].isoformat(), reason="Synthetic opening observation")
    return {**data, **changes}


def test_fresh_opening_public_commit_reimport_and_count(fresh_store):
    context = fresh_store
    content = csv_source("opening_stock", [opening(context)])
    ident = analyzed_files(context, [("opening.csv", content)])
    review_batch(context, ident, creations={"MILK":("ingredient", dict(name="Milk", base_unit="l",
        sku="MILK", active=True, expiry_tracking=False))})
    read, done = complete(context, ident)
    with Session(context[0][1]) as session:
        lot = session.scalar(select(InventoryLot))
        ingredient_id, lot_id = lot.ingredient_id, lot.id
        assert lot.on_hand_quantity == 12 and lot.received_date is None
        movement = session.scalar(select(InventoryMovement))
        assert movement.quantity_delta == 12 and movement.movement_type == "COUNT_CORRECTION"
        assert movement.reference_type == "OPENING_STOCK"
        assert session.scalar(select(func.count()).select_from(InventoryReceiptRecord)) == 1
    # The same source identity is also protected across the existing N6 API.
    from app.application.use_cases.public_reads import PublicReads
    from app.application.use_cases.stock_writes import StockWrites
    reads = PublicReads(context[0][2])
    context[0][5].app.state.public_reads = reads
    context[0][5].app.state.stock_writes = StockWrites(context[0][2], reads)
    body = opening(context)
    body.pop("source_record_id")
    body["ingredient_id"] = str(ingredient_id)
    body.update(origin="OPENING_STOCK", receipt_identity=dict(source_system_key="SETUP", source_record_id="MILK-LOT-1"),
        expected_inventory_version="retained-replay-precedes-CAS")
    replay_n6 = context[0][5].post(f"/api/v1/stores/{context[1].store_id}/inventory/receipts",
        headers={**context[3], "Idempotency-Key":str(uuid4())}, json=body)
    assert replay_n6.status_code == 200, replay_n6.text
    assert replay_n6.json()["data"]["lot"]["lot_id"] == str(lot_id)
    # Identical content uses approved interpretation; opening quantity is not added again.
    ident2 = analyzed_files(context, [("opening.csv", content)])
    review_batch(context, ident2, bindings={"MILK":ingredient_id})
    _, replay = complete(context, ident2)
    assert replay["outcome"] == "no_changes"
    # Approved headers are reusable interpretation, not approval of a new row identity.
    changed = csv_source("opening_stock", [opening(context, ingredient_id="NEW-MILK",
        source_record_id="NEW-MILK-LOT")])
    unknown = analyzed_files(context, [("opening.csv", changed)])
    issues = listing(context, unknown)
    assert any(i["issue_type"] == "identity" and i["source_header"] == "NEW-MILK"
        and i["status"] not in {"resolved", "auto_mapped"} for i in issues)
    with Session(context[0][1]) as session:
        assert session.scalar(select(func.count()).select_from(Ingredient)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 1
    context[0][4][0] = datetime.now(timezone.utc)
    count = dict(ingredient_id="MILK", lot_id="LOT-1", on_hand="10", unit="l",
        observed_at=context[0][4][0].isoformat(), reason="Synthetic actual count")
    ident3 = analyzed_files(context, [("count.csv", csv_source("inventory_count", [count]))])
    review_batch(context, ident3, bindings={"MILK":ingredient_id, "LOT-1":lot_id})
    _, counted = complete(context, ident3)
    with Session(context[0][1]) as session:
        assert session.get(InventoryLot, lot_id).on_hand_quantity == 10
        assert sorted(m.quantity_delta for m in session.scalars(select(InventoryMovement))) == [-2, 12]
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_fresh_multifile_setup_readiness_custom_planning_and_retained_run(fresh_store, reverse, monkeypatch):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from app.application.use_cases.readiness import ReadinessReads
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.planning_worker import PlanningExecution
    from app.application.use_cases.planning_configuration import PlanningConfigurationWrites
    from tests.integration.test_readiness_context import configure_baseline
    from app.models import Supplier, SupplierTerm, RecipeLine, SalesDaily, PlanningRun

    c = fresh_store
    today = c[0][4][0].astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    cutoff = today - timedelta(days=1)
    metadata = dict(COFFEE=("product", dict(name="Coffee", selling_unit="cup", sku="C1", price=None, active=True)),
        MILK=("ingredient", dict(name="Milk", base_unit="l", sku="M1", active=True, expiry_tracking=False)),
        SUP=("supplier", dict(name="Synthetic supplier", active=True)))
    sources = [
        ("menu.csv", csv_source("products", [dict(source_business_key="COFFEE", **metadata["COFFEE"][1])])),
        ("ingredients.csv", csv_source("ingredients", [dict(source_business_key="MILK", **metadata["MILK"][1])])),
        ("suppliers.csv", csv_source("suppliers", [dict(source_supplier_key="SUP", **metadata["SUP"][1])])),
        ("recipe.csv", csv_source("recipes", [dict(product_id="COFFEE", ingredient_id="MILK", version=1,
            effective_from=cutoff.isoformat(), effective_to=None, quantity_basis="PER_SERVING", yield_quantity="1",
            yield_unit="cup", process_loss_rate="0", quantity="1", unit="l")])),
        ("sales.csv", csv_source("sales", [dict(product_id="COFFEE", sales_date=cutoff.isoformat(),
            quantity="2", unit="cup", business_report_key="DAY-1")])),
        ("terms.csv", csv_source("supplier_terms", [dict(source_term_key="T1", supplier_id="SUP", ingredient_id="MILK",
            effective_from=today.isoformat(), effective_to=None, unit="l", pack_size_base_quantity="4", pack_cost="10",
            currency="VND", price_basis="PER_PACK", price_quantity=None, price_unit=None,
            moq_basis="PACKS", minimum_order_quantity="1", moq_unit=None, lead_time_days=0, shelf_life_days=None,
            active=True, maximum_order_base_quantity="100")])),
        ("opening.csv", csv_source("opening_stock", [opening(c)])),
        ("fees.csv", csv_source("payable_fees", [dict(source_fee_key="F1", scope="STORE_PROCUREMENT",
            effective_from=today.isoformat(), effective_to=None, mode="NONE", coverage="COMPLETE", currency="VND",
            components=[], covered_source_term_keys=["T1"], covered_source_supplier_keys=["SUP"],
            evidence_reference="Synthetic explicit no fees", reason="Owner fixture fact")])),
    ]
    ident = analyzed_files(c, list(reversed(sources)) if reverse else sources)
    review_batch(c, ident, creations=metadata)
    read, done = complete(c, ident)
    assert all(r["dependencies"] for r in read["preview"]["rows"] if r["after"]["domain"] in {"recipes", "sales", "supplier_terms", "opening_stock"})
    with Session(c[0][1]) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 1
        assert session.scalar(select(func.count()).select_from(Ingredient)) == 1
        assert session.scalar(select(func.count()).select_from(Supplier)) == 1
        product = session.scalar(select(Product)).id
        ingredient = session.scalar(select(Ingredient)).id
        lot = session.scalar(select(InventoryLot)).id
        assert session.scalar(select(RecipeLine)).quantity == 1
        assert session.scalar(select(SalesDaily)).quantity == 2
        assert session.scalar(select(SupplierTerm)).pack_cost == 10
    client = c[0][5]
    client.app.state.readiness = ReadinessReads(c[0][2], client.app.state.forecast_serving, planning_available=lambda:True)
    client.app.state.planning_configuration = PlanningConfigurationWrites(c[0][2])
    client.app.state.planning_public = PublicPlanning(c[0][2], client.app.state.forecast_serving)
    base = f"/api/v1/stores/{c[1].store_id}"
    before = client.get(base + "/readiness", params=dict(actions="planning", forecast_start_date=today.isoformat()))
    assert before.status_code == 200, before.text
    assert "INVENTORY_SCOPE_UNKNOWN" in str(before.json()["data"])
    configure_baseline(c)
    budget = client.put(base + "/planning-budget", headers={**c[3], "Idempotency-Key":str(uuid4()), "If-None-Match":"*"}, json=dict(amount="100"))
    assert budget.status_code == 201, budget.text
    c[0][4][0] = datetime.now(timezone.utc)
    declarations = [
        dict(source_declaration_key="stock", declaration=dict(kind="INVENTORY", ingredient_id="MILK",
            state="COMPLETE_CURRENT_LOTS", observed_at=c[0][4][0].isoformat(), covered_lot_ids=["LOT-1"], evidence_reference="Synthetic complete physical scope")),
        dict(source_declaration_key="history", declaration=dict(kind="SALES_COVERAGE", product_ids=["COFFEE"],
            from_date=cutoff.isoformat(), to_date=cutoff.isoformat(), state="COMPLETE", evidence_reference="Synthetic one observed day")),
        dict(source_declaration_key="context", declaration=dict(kind="PROCUREMENT_CONTEXT", effective_from=today.isoformat(), effective_to=None,
            committed_inbound_state="CONFIRMED_NONE", no_additional_orders_state="CONFIRMED_NONE", capacity_state="EXPLICIT_NOT_CONFIGURED",
            capacities=[], supplier_limit_state="EXPLICIT_NOT_CONFIGURED", supplier_limits=[], evidence_reference="Synthetic Owner procurement facts")),
    ]
    decl = analyzed_files(c, [("declarations.csv", csv_source("scope_declarations", declarations))])
    review_batch(c, decl, bindings={"MILK":ingredient, "COFFEE":product, "LOT-1":lot})
    complete(c, decl)
    after = client.get(base + "/readiness", params=dict(actions="planning", forecast_start_date=today.isoformat()))
    assert after.status_code == 200, after.text
    assert "INVENTORY_SCOPE_UNKNOWN" not in str(after.json()["data"])
    assert "DEFAULT_CONFIGURATION_UNAVAILABLE" in str(after.json()["data"])  # No seeded default to claim READY.
    from app.application.use_cases import forecast_trained_execution
    monkeypatch.setattr(forecast_trained_execution, "_now", lambda:c[0][4][0])
    accepted = client.post(base + "/procurement-plans", headers={**c[3], "Idempotency-Key":str(uuid4())},
        json=dict(requirements_mode="custom", forecast_start_date=today.isoformat(),
            requirements=dict(paths=[dict(path="BASE", min_fill_rate_percent="95", product_overrides=[])], budget_limit=None)))
    assert accepted.status_code == 202, accepted.text
    worker = PlanningExecution(c[0][2], client.app.state.forecast_serving)
    record = worker.run_one()
    assert record.status == "completed" and record.outcome == "recommendation_available", (record.error_code, record.capture.problems)
    retained = client.get(accepted.headers["Location"])
    assert retained.status_code == 200, retained.text
    with Session(c[0][1]) as session:
        original = session.get(PlanningRun, record.run_id).record_json
        assert session.get(InventoryLot, lot).on_hand_quantity == 12  # Planning never consumes real stock.
    c[0][4][0] = datetime.now(timezone.utc)
    count = analyzed_files(c, [("count.csv", csv_source("inventory_count", [dict(ingredient_id="MILK", lot_id="LOT-1",
        on_hand="10", unit="l", observed_at=c[0][4][0].isoformat(), reason="Synthetic count after capture")]))])
    review_batch(c, count, bindings={"MILK":ingredient, "LOT-1":lot}); complete(c, count)
    with Session(c[0][1]) as session:
        assert session.get(PlanningRun, record.run_id).record_json == original
        assert session.get(InventoryLot, lot).on_hand_quantity == 10
    assert client.get(accepted.headers["Location"]).json()["data"] == retained.json()["data"]
    # Explicit zero observation may retain a zero lot; it is still known empty stock.
    c[0][4][0] = datetime.now(timezone.utc)
    zero = analyzed_files(c, [
        ("count.csv", csv_source("inventory_count", [dict(ingredient_id="MILK", lot_id="LOT-1", on_hand="0", unit="l",
            observed_at=c[0][4][0].isoformat(), reason="Synthetic zero observation")])),
        ("empty.csv", csv_source("scope_declarations", [dict(source_declaration_key="stock", declaration=dict(kind="INVENTORY",
            ingredient_id="MILK", state="CONFIRMED_EMPTY", observed_at=c[0][4][0].isoformat(), covered_lot_ids=[],
            evidence_reference="Synthetic Owner confirms no other physical stock"))])),
    ])
    review_batch(c, zero, bindings={"MILK":ingredient, "LOT-1":lot}); complete(c, zero)
    c[0][4][0] = datetime.now(timezone.utc)
    zero_readiness = client.get(base + "/readiness", params=dict(actions="planning", forecast_start_date=today.isoformat()))
    assert "INVENTORY_SCOPE_UNKNOWN" not in str(zero_readiness.json()["data"])
    zero_plan = client.post(base + "/procurement-plans", headers={**c[3], "Idempotency-Key":str(uuid4())},
        json=dict(requirements_mode="custom", forecast_start_date=today.isoformat(),
            requirements=dict(paths=[dict(path="BASE", min_fill_rate_percent="95", product_overrides=[])], budget_limit=None)))
    assert zero_plan.status_code == 202, zero_plan.text
    zero_record = worker.run_one()
    assert zero_record.outcome == "recommendation_available", (zero_record.error_code, zero_record.capture.problems)
    with Session(c[0][1]) as session:
        assert session.get(InventoryLot, lot).on_hand_quantity == 0
        assert session.get(PlanningRun, record.run_id).record_json == original


@pytest.mark.parametrize("permission", ["inventory.receive", "ingredient.create"])
def test_opening_worker_rechecks_domain_and_entity_rights_without_orphans(fresh_store, permission):
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.models.import_staging import ImportJob
    from app.domain.permissions import PERMISSIONS
    c = fresh_store
    ident = analyzed_files(c, [("opening.csv", csv_source("opening_stock", [opening(c)]))])
    review_batch(c, ident, creations={"MILK":("ingredient", dict(name="Milk", base_unit="l", sku=None, active=True, expiry_tracking=False))})
    read = previewed(c, ident)
    confirmed = confirm(c, ident, read); assert confirmed.status_code == 200, confirmed.text
    accepted = commit(c, ident, read, confirmed.json()["data"]["import_revision"])
    assert accepted.status_code == 202, accepted.text
    with Session(c[0][1]) as session:
        member = session.scalar(select(StoreMembership))
        member.role = "STAFF"
        session.add_all(MembershipGrant(membership_id=member.id, permission=p) for p in sorted(PERMISSIONS - {permission}))
        session.commit()
    c[2].run_one()
    with Session(c[0][1]) as session:
        job = session.get(ImportJob, UUID(accepted.json()["data"]["job_id"]))
        assert job.status == "failed" and job.error_json["code"] == "PERMISSION_DENIED"
        for model in (Ingredient, InventoryLot, InventoryMovement, InventoryReceiptRecord):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_opening_fault_rolls_back_master_lot_movement_and_receipt(fresh_store, monkeypatch):
    from app.application.use_cases.inventory import InventoryUseCases
    from app.application.contracts.auth import AuthError
    c = fresh_store
    ident = analyzed_files(c, [("opening.csv", csv_source("opening_stock", [opening(c)]))])
    review_batch(c, ident, creations={"MILK":("ingredient", dict(name="Milk", base_unit="l", sku=None, active=True, expiry_tracking=False))})
    read = previewed(c, ident)
    confirmed = confirm(c, ident, read); assert confirmed.status_code == 200, confirmed.text
    original = InventoryUseCases.receive_in_transaction
    def fail_after_mutation(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise AuthError("PREVIEW_BLOCKED", 409)
    monkeypatch.setattr(InventoryUseCases, "receive_in_transaction", fail_after_mutation)
    accepted = commit(c, ident, read, confirmed.json()["data"]["import_revision"])
    assert accepted.status_code == 202, accepted.text
    c[2].run_one()
    with Session(c[0][1]) as session:
        for model in (Ingredient, InventoryLot, InventoryMovement, InventoryReceiptRecord):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_xlsx_opening_reordered_header_row_and_stale_preview(fresh_store):
    from xml.sax.saxutils import escape
    from tests.unit.test_import_parser import workbook
    from app.application.use_cases.inventory import InventoryUseCases
    from app.application.contracts.inventory import AdjustInventoryInput
    from decimal import Decimal
    c = fresh_store
    data = dict(reversed(list(opening(c).items())))
    def cells(values, number):
        return f'<row r="{number}">' + ''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{escape(str(value) if value is not None else "")}</t></is></c>' for i,value in enumerate(values)) + '</row>'
    content = workbook(cells(["Synthetic opening source"], 1) + cells(["opening_stock." + k for k in data], 3) + cells(data.values(), 4))
    ident = analyzed_files(c, [("opening-source.xlsx", content)])
    review_batch(c, ident, creations={"MILK":("ingredient", dict(name="Milk", base_unit="l", sku=None, active=True, expiry_tracking=False))})
    read, _ = complete(c, ident)
    opening_row = next(r for r in read["preview"]["rows"] if r["after"]["domain"] == "opening_stock")
    assert opening_row["source_location"]["row_number"] == 4
    assert opening_row["inventory_effect"]["quantity_delta"] == "12"
    with Session(c[0][1]) as session:
        lot = session.scalar(select(InventoryLot)); ingredient_id, lot_id = lot.ingredient_id, lot.id
    c[0][4][0] = datetime.now(timezone.utc)
    count = analyzed_files(c, [("count.csv", csv_source("inventory_count", [dict(ingredient_id="MILK", lot_id="LOT-1",
        on_hand="10", unit="l", observed_at=c[0][4][0].isoformat(), reason="Synthetic count")]))])
    review_batch(c, count, bindings={"MILK":ingredient_id, "LOT-1":lot_id})
    preview = previewed(c, count)
    assert preview["preview"]["rows"][0]["inventory_effect"]["quantity_delta"] == "-2"
    # A separate legitimate stock event invalidates the frozen preview.
    with Session(c[0][1]) as session:
        InventoryUseCases(session).adjust(AdjustInventoryInput(store_id=c[1].store_id, lot_id=lot_id,
            quantity_delta=Decimal("-1"), unit="l", movement_type="MANUAL_ADJUSTMENT", occurred_at=datetime.now(timezone.utc),
            reference_type="SYNTHETIC_EXTERNAL_EVENT", reference_id="external-1", note="Synthetic intervening correction"))
    rejected = confirm(c, count, preview)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "PREVIEW_STALE", rejected.text
    with Session(c[0][1]) as session:
        assert session.get(InventoryLot, lot_id).on_hand_quantity == 11
