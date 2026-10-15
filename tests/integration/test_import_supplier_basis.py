"""Owner source review -> canonical PG -> exact procurement and retained capture."""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_import_commit import env, imp, ready, commit, finished
from tests.integration.test_import_staging import analyzed, approved, previewed, csv_source
from tests.integration.test_import_classification import confirm, listing, mapping
from tests.integration.test_import_field_value_bindings import review, shared, activate, summary
from tests.integration.test_planning_public import flow, config, submit, base
from tests.unit.test_import_supplier_basis import term
from app.models import Ingredient, Supplier, SupplierTerm
from app.models.operational_import import TermSourceRecord
from app.application.contracts.import_domains import TermSource
from app.application.contracts.planning_source_evidence import TermEvidence
from app.domain.decision.procurement import Offer, outlay, basket_violations


@pytest.fixture(autouse=True)
def provider_off(env):
    assert not env[0].import_llm_suggestions_enabled


def identities(imp, unit="g"):
    ingredient, supplier = uuid4(), uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=ingredient, store_id=imp[1].store_id, name="Synthetic input",
            base_unit=unit, expiry_tracking=False, active=True))
        s.add(Supplier(id=supplier, store_id=imp[1].store_id, name="Synthetic supplier", active=True))
        s.commit()
    return ingredient, supplier


@pytest.mark.parametrize("extra,unit,pack,cost,minimum", [
    ({"unit":"kg", "pack_size_base_quantity":"1"}, "g", "1000", "100000", 2),
    ({"price_basis":"PER_QUANTITY", "price_quantity":"1", "price_unit":"g", "pack_cost":"100"}, "g", "1000", "100000", 2),
    ({"unit":"l", "pack_size_base_quantity":"2", "price_basis":"PER_QUANTITY", "price_quantity":"1", "price_unit":"l", "pack_cost":"60000"}, "ml", "2000", "120000", 2),
    ({"moq_basis":"PHYSICAL_QUANTITY", "minimum_order_quantity":"2000", "moq_unit":"g"}, "g", "1000", "100000", 2),
    ({"moq_basis":"PHYSICAL_QUANTITY", "minimum_order_quantity":"1500", "moq_unit":"g"}, "g", "1000", "100000", 2),
    ({"price_basis":"PER_QUANTITY", "price_quantity":"2", "price_unit":"kg", "pack_cost":"200000", "moq_basis":"PHYSICAL_QUANTITY", "minimum_order_quantity":"1.5", "moq_unit":"kg"}, "g", "1000", "100000", 2),
])
def test_review_persistence_exact_basket_and_retry(imp, extra, unit, pack, cost, minimum):
    ingredient, supplier = identities(imp, unit)
    data = term(**extra, ingredient_id=ingredient, supplier_id=supplier)
    foreign_unit = next((data[f] for f in ("unit", "price_unit", "moq_unit") if data[f] and data[f] != unit), None)
    resolutions = {"UNIT_CONVERSION_REQUIRED": dict(kind="declared_conversion", from_unit=foreign_unit,
        to_unit=unit, factor=dict(numerator="1000", denominator="1"), evidence_reference="Owner reviewed physical scale")} if foreign_unit else {}
    ident, read, revision = ready(imp, csv_source("supplier_terms", [data]), report="supplier-basis", resolutions=resolutions)
    row = read["preview"]["rows"][0]
    assert row["after"]["pack_cost"] == cost and row["after"]["minimum_order_packs"] == minimum
    assert row["supplier_term_semantics"]["source_moq_quantity"] == data["minimum_order_quantity"]
    key = str(uuid4())
    accepted = commit(imp, ident, read, revision, key=key)
    result = finished(imp, ident, accepted)
    ref = result["canonical_references"][0]
    assert ref["supplier_term_semantics"] == row["supplier_term_semantics"]
    with Session(imp[0][1]) as fresh:
        saved = fresh.scalar(select(SupplierTerm))
        assert (saved.unit, saved.pack_size_base_quantity, saved.pack_cost, saved.minimum_order_packs) == (unit, Decimal(pack), Decimal(cost), minimum)
        source = fresh.get(TermSourceRecord, saved.id)
        canonical = TermSource.model_validate(source.payload)
        evidence = TermEvidence(term_id=saved.id, version=saved.version, source_system_key=source.source_system_key,
            source_record_key=source.source_record_key, payload=canonical)
        assert evidence.payload.pack_cost == cost and "price_basis" not in source.payload
        assert source.provenance["row"]["supplier_term_semantics"] == row["supplier_term_semantics"]
        offer = Offer(saved.id, ingredient, supplier, unit, saved.pack_size_base_quantity,
            saved.pack_cost, saved.minimum_order_packs, 3, saved.lead_time_days, saved.shelf_life_days, uuid4(), None)
    assert outlay((offer,), (2,), "NONE", ()) == Decimal(cost) * 2
    assert not basket_violations((offer,), (0,), outlay((offer,), (0,), "NONE", ()), Decimal(0), ())
    assert basket_violations((offer,), (1,), outlay((offer,), (1,), "NONE", ()), Decimal(cost), ()) == ("PACK_MOQ_BOUNDS",)
    assert not basket_violations((offer,), (2,), outlay((offer,), (2,), "NONE", ()), Decimal(cost) * 2, ())
    replay = commit(imp, ident, read, revision, key=key)
    assert replay.status_code == 202 and replay.json()["data"] == accepted.json()["data"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 1


@pytest.mark.parametrize("invalid", [dict(pack_size_base_quantity="0"), dict(minimum_order_quantity="1.5"),
    dict(price_basis="PER_QUANTITY", price_quantity="0", price_unit="g"), dict(currency="USD")])
def test_invalid_row_blocks_whole_batch(imp, invalid):
    ingredient, supplier = identities(imp)
    data = term(ingredient_id=ingredient, supplier_id=supplier)
    ident = analyzed(imp, csv_source("supplier_terms", [data, {**data, **invalid, "source_term_key":"bad"}]))
    approved(imp, ident)
    read = previewed(imp, ident)
    assert read["preview"]["summary"]["blockers"]
    assert confirm(imp, ident, read).status_code == 409
    assert commit(imp, ident, read, read["import_revision"]).status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 0


def test_shared_basis_reuse_never_reuses_commercial_values(imp, monkeypatch):
    ingredient, supplier = identities(imp)
    content = csv_source("supplier_terms", [dict(source_term_key="T1", ingredient_id=ingredient,
        supplier_id=supplier, unit="g")])
    ident = analyzed(imp, content)
    review(imp, ident, schema="supplier_terms")
    constants = dict(price_basis="PER_QUANTITY", price_quantity="1", price_unit="g",
        moq_basis="PHYSICAL_QUANTITY", moq_unit="g", currency="VND", active=True)
    facts = dict(effective_from="2026-01-01", effective_to=None, pack_size_base_quantity="1000",
        pack_cost="100", minimum_order_quantity="1500", lead_time_days=0, shelf_life_days=None,
        maximum_order_base_quantity=None)
    for f, v in constants.items():
        r = shared(imp, ident, "supplier_terms." + f, v, "PROFILE_CONSTANT")
        assert r.status_code == 200, r.text
    for f, v in facts.items():
        r = shared(imp, ident, "supplier_terms." + f, v)
        assert r.status_code == 200, r.text
    rejected = shared(imp, ident, "supplier_terms.pack_cost", "100", "PROFILE_CONSTANT")
    assert rejected.status_code == 422
    activate(imp, ident)
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert row["after"]["pack_cost"] == "100000" and row["after"]["minimum_order_packs"] == 2
    assert row["provenance"]["pack_cost"]["declaration_id"]
    from app.infrastructure import import_suggestions
    second = analyzed(imp, content)
    assert not summary(imp, second)["binding_refs"]
    monkeypatch.setattr(import_suggestions, "suggest_sheet", lambda *a, **k: pytest.fail("reuse called model"))
    review(imp, second, schema="supplier_terms")
    assert not summary(imp, second)["can_preview"]
    for f, v in {**facts, "pack_cost":"200", "minimum_order_quantity":"2500"}.items():
        r = shared(imp, second, "supplier_terms." + f, v)
        assert r.status_code == 200, r.text
    row = previewed(imp, second)["preview"]["rows"][0]
    assert row["after"]["pack_cost"] == "200000" and row["after"]["minimum_order_packs"] == 3


def test_old_profile_basis_is_readable_but_requires_review(imp):
    from app.models.import_staging import ImportProfileVersion, ImportProfile
    from app.application.import_identity import content_digest
    ingredient, supplier = identities(imp)
    data = term(ingredient_id=ingredient, supplier_id=supplier)
    content = csv_source("supplier_terms", [data])
    ident = analyzed(imp, content); approved(imp, ident)
    with Session(imp[0][1]) as s:
        version = s.scalar(select(ImportProfileVersion))
        payload = dict(version.spec_json)
        payload["field_bindings"] = [b for b in payload["field_bindings"] if b["target_field"] != "supplier_terms.price_basis"]
        historical = ImportProfileVersion(**{c.name: getattr(version, c.name) for c in ImportProfileVersion.__table__.columns
            if c.name not in {"version", "spec_json", "content_digest"}}, version=str(uuid4()),
            spec_json=payload, content_digest=content_digest(payload))
        s.add(historical); s.flush()
        s.get(ImportProfile, version.profile_id).active_version = historical.version; s.commit()
    second = analyzed(imp, content)
    assert not summary(imp, second)["can_preview"]
    assert summary(imp, second)["sheets"][0]["classification_origin"] != "REUSED"


@pytest.mark.parametrize("foreign", [False, True])
def test_unknown_or_cross_store_supplier_requires_authorized_identity(imp, foreign):
    from tests.integration.test_auth_public import provision
    ingredient, _ = identities(imp)
    supplier = uuid4()
    if foreign:
        owner = provision(imp[0], email="foreign-supplier@example.test")
        with Session(imp[0][1]) as s:
            s.add(Supplier(id=supplier, store_id=owner.store_id, name="Foreign supplier", active=True)); s.commit()
    ident = analyzed(imp, csv_source("supplier_terms", [term(ingredient_id=ingredient, supplier_id=supplier)]))
    issue = next(i for i in listing(imp, ident) if i["code"] == "UNKNOWN_SUPPLIER")
    response = mapping(imp, ident, issue, {"resolution":dict(kind="identity_binding", canonical_id=str(supplier))})
    assert response.status_code == 404, response.text
    assert not summary(imp, ident)["can_preview"]
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 0


def test_new_header_layout_requires_review_and_preserves_physical_row(imp):
    from xml.sax.saxutils import escape
    from tests.unit.test_import_parser import workbook
    from tests.integration.test_import_commit import analyzed_files
    ingredient, supplier = identities(imp)
    data = term(ingredient_id=ingredient, supplier_id=supplier)
    initial = analyzed(imp, csv_source("supplier_terms", [data])); approved(imp, initial)
    fields = list(reversed(list(data)))
    headers = {f: "supplier_terms." + f for f in fields}
    headers["pack_cost"] = "Quoted amount"
    headers["unit"] = "Base UOM"
    def cells(values, row):
        return '<row r="'+str(row)+'">'+''.join('<c r="'+chr(65+i)+str(row)+'" t="inlineStr"><is><t>'+escape(str(v).lower() if isinstance(v, bool) else str(v) if v is not None else '')+'</t></is></c>' for i,v in enumerate(values))+'</row>'
    content = workbook(cells(["Synthetic source"],1) + cells([headers[f] for f in fields],3) + cells([data[f] for f in fields],4))
    ident = analyzed_files(imp, [("new-source-layout.xlsx", content)])
    assert not summary(imp, ident)["can_preview"]
    for item in listing(imp, ident):
        if item["issue_type"] == "column" and item["source_header"] == "Quoted amount":
            r = mapping(imp, ident, item, {"target_field":"supplier_terms.pack_cost"})
            assert r.status_code == 200, r.text
    review(imp, ident, schema="supplier_terms"); activate(imp, ident)
    read = previewed(imp, ident)
    row = read["preview"]["rows"][0]
    assert row["source_location"]["row_number"] == 4 and row["after"]["pack_cost"] == "100000"
    confirmed = confirm(imp, ident, read); assert confirmed.status_code == 200, confirmed.text
    finished(imp, ident, commit(imp, ident, read, confirmed.json()["data"]["import_revision"]))


def test_fee_dependency_change_invalidates_preview(imp):
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    from app.application.contracts.import_domains import FeeSource
    ingredient, supplier = identities(imp)
    ident, read, revision = ready(imp, csv_source("supplier_terms", [term(ingredient_id=ingredient, supplier_id=supplier)]))
    with Session(imp[0][1]) as s:
        OperationalConfiguration(s, imp[1].store_id).fee(FeeSource(source_fee_key="none", scope="STORE_PROCUREMENT",
            effective_from=date(2026,1,1), effective_to=None, mode="NONE", coverage="COMPLETE", currency="VND",
            components=(), covered_source_term_keys=(), covered_source_supplier_keys=(), evidence_reference="Explicit no fee",
            reason="New reviewed fee coverage"), uuid4(), "POS-A", {}, {}); s.commit()
    assert commit(imp, ident, read, revision).status_code == 409
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 0


@pytest.mark.parametrize("unknown_fees", [False, True])
def test_public_import_to_planning_capture_and_retained_price(flow, unknown_fees):
    from app.application.use_cases.import_staging import ImportStaging
    from app.application.use_cases.readiness import ReadinessReads
    from tests.integration.test_readiness_context import declaration
    from app.application.contracts import import_domains as d
    from app.models import SalesDaily, PlanningRun
    c, ingredient, _, worker = flow
    service = ImportStaging(c[0][2], c[0][0])
    c[0][5].app.state.import_staging = service
    imp = c[0], c[1], service, c[3], c[2]
    supplier = uuid4()
    with Session(c[0][1]) as s:
        s.add(Supplier(id=supplier, store_id=c[1].store_id, name="Synthetic import supplier", active=True)); s.flush()
        s.scalar(select(SalesDaily)).quantity = 5
        declaration(s, c[1].store_id, d.ProcurementDeclaration(kind="PROCUREMENT_CONTEXT",
            effective_from=date(2026,10,10), effective_to=None, committed_inbound_state="CONFIRMED_NONE",
            no_additional_orders_state="CONFIRMED_NONE", capacity_state="EXPLICIT_NOT_CONFIGURED", capacities=(),
            supplier_limit_state="EXPLICIT_NOT_CONFIGURED", supplier_limits=(), evidence_reference="Fresh supplier context"), "context")
        if unknown_fees:
            from app.application.use_cases.operational_configuration import OperationalConfiguration
            OperationalConfiguration(s, c[1].store_id).fee(d.FeeSource(source_fee_key="none",
                scope="STORE_PROCUREMENT", effective_from=date(2026,10,10), effective_to=None,
                mode="PER_OFFER", coverage="UNKNOWN", currency="VND", components=(),
                covered_source_term_keys=(), covered_source_supplier_keys=(), evidence_reference="No verified fee schedule",
                reason="Unknown is not free"), uuid4(), "synthetic", {}, {})
        s.commit()
    data = term(ingredient_id=ingredient, supplier_id=supplier, unit="ml", pack_size_base_quantity="5",
        pack_cost="400", price_basis="PER_QUANTITY", price_quantity="1", price_unit="l",
        minimum_order_quantity="1", effective_from="2026-10-10")
    ident, read, revision = ready(imp, csv_source("supplier_terms", [data]), resolutions={
        "UNIT_CONVERSION_REQUIRED": dict(kind="declared_conversion", from_unit="l", to_unit="ml",
            factor=dict(numerator="1000", denominator="1"), evidence_reference="Explicit denominator litre")})
    assert read["preview"]["rows"][0]["after"]["pack_cost"] == "2"
    assert read["preview"]["rows"][0]["supplier_term_semantics"]["fee_coverage"] == ("UNKNOWN" if unknown_fees else "COMPLETE")
    done = finished(imp, ident, commit(imp, ident, read, revision))
    c[0][5].app.state.readiness = ReadinessReads(c[0][2], c[0][5].app.state.forecast_serving,
        planning_available=lambda: True)  # This test owns and runs the real Planning worker.
    readiness = c[0][5].get(base(c) + "/readiness", params={"actions":"planning", "forecast_start_date":"2026-10-10"})
    assert readiness.status_code == 200, readiness.text
    if unknown_fees:
        assert "PAYABLE_FEE_COVERAGE_UNKNOWN" in {b["code"] for b in readiness.json()["data"]["actions"][0]["blockers"]}
        response = submit(c); assert response.status_code == 202, response.text
        record = worker.run_one()
        assert record.outcome == "computation_blocked"
        assert any(p.code == "PAYABLE_FEE_COVERAGE_UNKNOWN" for p in record.capture.problems)
        return
    assert readiness.json()["data"]["actions"][0]["availability"] == "ready", readiness.text
    response = submit(c); assert response.status_code == 202, response.text
    record = worker.run_one()
    assert record.outcome == "recommendation_available", record.error_code
    retained = c[0][5].get(response.headers["Location"]).json()["data"]
    captured = record.public_capture.operational_evidence.terms[0]
    proof=next(p for p in record.public_capture.operational_evidence.confirmations
        if p.entity=='supplier_term' and p.entity_id==captured.term_id)
    assert proof.actor_id==c[1].user_id and proof.audit_id is not None and proof.confirmed_at is not None
    assert captured.payload.pack_cost == "2" and captured.payload.unit == "ml"
    term_id = UUID(done["canonical_references"][0]["canonical_id"])
    # Existing reviewed future-only amendment contract; retained Run must stay fixed.
    from sqlalchemy import text
    with Session(c[0][1]) as s:
        old, version = s.execute(select(SupplierTerm, text("xmin::text")).where(SupplierTerm.id == term_id)).one()
        run_json = s.get(PlanningRun, record.run_id).record_json
    ident2 = analyzed(imp, csv_source("supplier_terms", [dict(reversed(list(
        {**data, "pack_cost":"600", "effective_from":"2026-10-11"}.items())))]))
    approved(imp, ident2, report="new-supplier-price", context=dict(term_period_amendments=[dict(
        supplier_term_id=str(term_id), expected_version=version, effective_to="2026-10-10", reason="Future source price")]),
        resolutions={"UNIT_CONVERSION_REQUIRED":dict(kind="declared_conversion",from_unit="l",to_unit="ml",
            factor=dict(numerator="1000",denominator="1"),evidence_reference="Same physical denominator")})
    read2 = previewed(imp, ident2)
    confirmed = confirm(imp, ident2, read2); assert confirmed.status_code == 200, confirmed.text
    from tests.integration.test_import_staging import post
    rows = read2["preview"]["rows"]
    accepted = post(imp, f"/imports/{ident2}/process", dict(phase="commit", preview_id=read2["preview"]["summary"]["preview_id"],
        preview_digest=read2["preview"]["summary"]["digest"], confirm=True, reason="Future exact price", resolutions=[],
        supplier_changes=[dict(action_id=r["row_id"], reason="Reviewed future version") for r in rows if r["confirmation_required"]]),
        match=confirmed.json()["data"]["import_revision"])
    finished(imp, ident2, accepted)
    with Session(c[0][1]) as fresh:
        assert fresh.get(PlanningRun, record.run_id).record_json == run_json
        assert fresh.scalar(select(SupplierTerm).where(SupplierTerm.version == 2)).pack_cost == 3
    assert c[0][5].get(response.headers["Location"]).json()["data"] == retained
