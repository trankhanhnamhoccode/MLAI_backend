"""Hand-calculated import expectations, detached inputs; no canonical writer."""

from datetime import datetime, timezone
from decimal import localcontext
from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.application.contracts import import_mapping as dto
from app.application.import_preview import make_preview, exact_text
from app.application.import_analysis import discover, build_spec
from app.infrastructure.import_parser import parse_source

NOW = datetime(2026, 10, 10, 3, tzinfo=timezone.utc)


def case(
    schema,
    records,
    snapshot=None,
    semantics=None,
    entities=(),
    conversions=(),
    context_fields=None,
):
    import csv, io, json

    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    keys = list(records[0])
    writer.writerow([schema + "." + k for k in keys])
    writer.writerows(
        [
            [
                (
                    json.dumps(r[k])
                    if isinstance(r[k], (dict, list, tuple))
                    else (
                        str(r[k]).lower()
                        if isinstance(r[k], bool)
                        else str(r[k]) if r[k] is not None else ""
                    )
                )
                for k in keys
            ]
            for r in records
        ]
    )
    sheets, issues, sources = discover(
        uuid4(), parse_source(buf.getvalue().encode(), "csv")
    )
    context_values = dict(sales_semantics=semantics,
        inventory_semantics="lot_stock_count" if schema == "inventory_count" else None)
    context_values.update(context_fields or {})
    context = dto.SourceContext(
        kind="source_context",
        source_system_key="POS-A",
        report_type="report-1",
        evidence_reference="Synthetic explicit source",
        **context_values
    )
    issues = [
        i.model_copy(
            update={
                "status": "resolved",
                "resolution": (
                    dto.ResolveRequest(resolution=context)
                    if i.issue_type == "source_context"
                    else None
                ),
            }
        )
        for i in issues
    ]
    spec, missing = build_spec(
        sheets[0], issues, uuid4(), entities=entities, conversions=conversions
    )
    assert not missing, missing
    data = {
        name: []
        for name in (
            "products",
            "ingredients",
            "suppliers",
            "inventory_lots",
            "inventory_movements",
            "sales_daily",
            "recipes",
            "recipe_lines",
            "supplier_terms",
        )
    }
    data.update(snapshot or {})
    return make_preview(
        sources, {str(sheets[0].sheet_id): spec}, data, NOW, "Asia/Ho_Chi_Minh", "VND",
        stockout_policies={str(sheets[0].sheet_id): (context.missing_stockout, context.evidence_reference)} if context.missing_stockout else None,
    )


def test_future_term_requires_explicit_pinned_amendment_and_no_retroactive_rewrite():
    supplier, ingredient, term = uuid4(), uuid4(), uuid4()
    old = dict(
        id=str(term),
        supplier_id=str(supplier),
        ingredient_id=str(ingredient),
        version=1,
        effective_from="2026-10-01",
        effective_to=None,
        unit="l",
        pack_size_base_quantity="6",
        pack_cost="180000",
        minimum_order_packs=1,
        lead_time_days=1,
        shelf_life_days=14,
        active=True,
        _row_version="77",
    )
    snapshot = dict(
        suppliers=[dict(id=str(supplier))],
        ingredients=[dict(id=str(ingredient), base_unit="l", expiry_tracking=True)],
        supplier_terms=[old],
    )
    source = {
        k: v for k, v in old.items() if k not in {"id", "version", "_row_version"}
    }
    source.update(
        source_term_key="new-terms",
        price_basis="PER_PACK", price_quantity=None, price_unit=None,
        moq_basis="PACKS", minimum_order_quantity=str(source.pop("minimum_order_packs")), moq_unit=None,
        effective_from="2026-10-11",
        currency="VND",
        maximum_order_base_quantity=None,
        pack_cost="190000",
    )
    blocked = case("supplier_terms", [source], snapshot)[0]
    assert "TERM_PERIOD_OVERLAP" in {b.code for b in blocked.blockers}
    policy = dict(
        term_period_amendments=[
            dict(
                supplier_term_id=term,
                expected_version="77",
                effective_to="2026-10-10",
                reason="Explicit supplier contract change",
            )
        ],
        planned_arrival_expiry_rule=dict(
            basis="ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS",
            evidence_reference="14 calendar days inclusive",
        ),
    )
    rows = case("supplier_terms", [source], snapshot, context_fields=policy)
    assert len(rows) == 2
    amendment = next(r for r in rows if r.proposed_action == "AMEND_TERM_PERIOD")
    assert (
        amendment.before.effective_to is None
        and amendment.after.effective_to.isoformat() == "2026-10-10"
    )
    assert (
        amendment.before.source_term_key is None and amendment.expected_version == "77"
    )
    assert amendment.confirmation_required and amendment.required_permissions == (
        "supplier.terms.correct",
    )
    assert not any(r.blockers for r in rows)
    assert old["effective_to"] is None  # captured facts never changed
    stale_policy = {
        **policy,
        "term_period_amendments": [
            dict(
                supplier_term_id=term,
                expected_version="78",
                effective_to="2026-10-10",
                reason="stale",
            )
        ],
    }
    assert "TERM_AMENDMENT_CONFLICT" in {
        b.code
        for r in case("supplier_terms", [source], snapshot, context_fields=stale_policy)
        for b in r.blockers
    }
    assert "HISTORICAL_TERM_CORRECTION" in {
        b.code
        for r in case(
            "supplier_terms",
            [{**source, "effective_from": "2026-10-09"}],
            snapshot,
            context_fields=policy,
        )
        for b in r.blockers
    }


def test_explicit_metadata_conflicts_never_infer_verified_source():
    from app.application.import_analysis import source_context_conflicts

    sheets, issues, sources = discover(
        uuid4(),
        parse_source(
            b"source_context.source_system_key,sales.quantity\nPOS-B,10\n", "csv"
        ),
    )
    scope = dto.ProfileScope(source_system_key="POS-A", report_type="sales")
    assert (
        source_context_conflicts(sheets[0], sources[0], scope)[0].code
        == "SOURCE_CONTEXT_CONFLICT"
    )
    assert not source_context_conflicts(
        sheets[0], sources[0], scope.model_copy(update={"source_system_key": "POS-B"})
    )


def test_count_exact_signed_delta_zero_and_stale():
    pid, lot = uuid4(), uuid4()
    source = dict(
        ingredient_id=pid,
        lot_id=lot,
        on_hand="10",
        unit="l",
        observed_at="2026-10-10T02:00:00Z",
        reason="Synthetic count",
    )
    snapshot = dict(
        ingredients=[dict(id=str(pid), base_unit="l")],
        inventory_lots=[
            dict(
                id=str(lot),
                ingredient_id=str(pid),
                unit="l",
                on_hand_quantity="12",
                updated_at="2026-10-10T01:00:00+00:00",
            )
        ],
    )
    row = case("inventory_count", [source], snapshot)[0]
    assert row.proposed_action == "COUNT_CORRECTION" and row.changes[0].delta == "-2"
    assert row.before.on_hand == "12" and row.after.on_hand == "10"
    no_op = case("inventory_count", [{**source, "on_hand": "12.0"}], snapshot)[0]
    assert no_op.proposed_action == "NO_OP" and no_op.changes == ()
    stale = case(
        "inventory_count", [{**source, "observed_at": "2026-10-10T00:00:00Z"}], snapshot
    )[0]
    assert [b.code for b in stale.blockers] == ["STALE_STOCK_OBSERVATION"]


def test_whole_recipe_group_yield_units_duplicate_and_overlap():
    pid, i1, i2 = uuid4(), uuid4(), uuid4()
    base = dict(
        product_id=pid,
        version=1,
        effective_from="2026-10-11",
        effective_to=None,
        quantity_basis="WHOLE_BATCH", yield_quantity="10",
        yield_unit="cup",
        process_loss_rate="0.2",
        ingredient_id=i1,
        quantity="1000",
        unit="ml",
    )
    snapshot = dict(
        products=[dict(id=str(pid), selling_unit="cup")],
        ingredients=[
            dict(id=str(i1), base_unit="ml"),
            dict(id=str(i2), base_unit="ml"),
        ],
    )
    rows = case(
        "recipes", [base, {**base, "ingredient_id": i2, "quantity": "500"}], snapshot
    )
    assert (
        len(rows) == 1
        and len(rows[0].after.lines) == 2
        and len(rows[0].source_locations) == 2
    )
    assert (
        rows[0].after.yield_quantity == "10"
        and rows[0].after.process_loss_rate == "0.2"
    )
    dup = case("recipes", [base, base], snapshot)[0]
    assert "DUPLICATE_RECIPE_INGREDIENT" in {b.code for b in dup.blockers}
    wrong = case("recipes", [{**base, "unit": "g"}], snapshot)[0]
    assert "UNIT_MISMATCH" in {b.code for b in wrong.blockers}


def test_exact_conversion_and_decimal_context_do_not_change_values():
    pid = uuid4()
    source = dict(
        product_id=pid,
        sales_date="2026-10-09",
        quantity="1.25",
        unit="source-cup",
        business_report_key="R1",
    )
    snapshot = dict(products=[dict(id=str(pid), selling_unit="cup")])
    conversion = dto.Conversion(
        kind="declared_conversion",
        from_unit="source-cup",
        to_unit="cup",
        factor=dto.Factor(numerator="2", denominator="1"),
        evidence_reference="Owner established conversion",
    )
    with localcontext() as ctx:
        ctx.prec = 2
        row = case(
            "sales",
            [source],
            snapshot,
            semantics="daily_total",
            conversions=(conversion,),
        )[0]
    assert row.after.quantity == "2.5" and not row.blockers
    assert any(p.origin == "DETERMINISTIC_DERIVED" for p in row.provenance)
    assert exact_text("0.000000000000000000001") == "0.000000000000000000001"


def test_approved_reserved_product_emits_catalog_dependency_without_lot_stock():
    reserved = uuid4()
    ent = dto.EntityReservation(
        proposal_id=uuid4(),
        entity="product",
        source_business_key="COFFEE-A",
        reserved_canonical_id=reserved,
        metadata=dto.ProductMetadata(
            name="Coffee", selling_unit="cup", sku="COFFEE-A", price=None, active=True
        ),
        evidence_reference="Synthetic catalog",
        approval_revision="proposal-1",
    )
    rows = case(
        "sales",
        [
            dict(
                product_id="COFFEE-A",
                sales_date="2026-10-09",
                quantity="0",
                unit="cup",
                business_report_key="R1",
            )
        ],
        semantics="daily_total",
        entities=(ent,),
    )
    assert len(rows) == 2 and rows[0].proposed_action == "CREATE_PRODUCT"
    assert (
        rows[1].dependencies == (rows[0].row_id,)
        and rows[1].after.product_id == reserved
    )
    assert rows[1].after.quantity == "0" and not rows[1].blockers


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-1", "1e3", "true"])
def test_noncanonical_quantities_are_blocked_not_fabricated_zero(quantity):
    pid = uuid4()
    rows = case(
        "sales",
        [
            dict(
                product_id=pid,
                sales_date="2026-10-09",
                quantity=quantity,
                unit="cup",
                business_report_key="R1",
            )
        ],
        dict(products=[dict(id=str(pid), selling_unit="cup")]),
        semantics="daily_total",
    )
    assert rows[0].classification == "INVALID" and rows[0].after is None


def test_disjoint_intent_requires_confirmation_and_keeps_100_plus_105():
    pid = uuid4()
    rows = case(
        "sales",
        [
            dict(
                product_id=pid,
                sales_date="2026-10-09",
                quantity="105",
                unit="cup",
                business_report_key="R2",
            )
        ],
        dict(
            products=[dict(id=str(pid), selling_unit="cup")],
            sales_daily=[
                dict(product_id=str(pid), sales_date="2026-10-09", quantity="100")
            ],
        ),
        semantics="disjoint_contribution",
        context_fields={'missing_stockout': 'not_provided'},
    )
    row = rows[0]
    assert row.after.quantity == "205" and row.confirmation_required
    assert "SALES_DISJOINTNESS_REQUIRES_CONFIRMATION" in {w.code for w in row.warnings}


def test_supplier_term_pack_pricing_and_declared_unit_conversion_are_exact():
    supplier, ingredient = uuid4(), uuid4()
    source = dict(
        source_term_key="MILK-15",
        supplier_id=supplier,
        ingredient_id=ingredient,
        effective_from="2026-10-11",
        effective_to=None,
        unit="kg",
        pack_size_base_quantity="15",
        pack_cost="28000",
        currency="VND",
        minimum_order_quantity="1", price_basis="PER_QUANTITY", price_quantity="1", price_unit="kg",
        moq_basis="PACKS", moq_unit=None,
        lead_time_days=0,
        shelf_life_days=None,
        active=True,
        maximum_order_base_quantity=None,
    )
    snapshot = dict(
        suppliers=[dict(id=str(supplier))],
        ingredients=[dict(id=str(ingredient), base_unit="g", expiry_tracking=False)],
    )
    conversion = dto.Conversion(
        kind="declared_conversion",
        from_unit="kg",
        to_unit="g",
        factor=dto.Factor(numerator="1000", denominator="1"),
        evidence_reference="Synthetic established kg/g",
    )
    row = case(
        "supplier_terms",
        [source],
        snapshot,
        conversions=(conversion,),
    )[0]
    assert (
        not row.blockers
        and row.after.pack_cost == "420000"
        and row.after.pack_size_base_quantity == "15000"
    )
    assert row.after.unit == "g" and row.after.lead_time_days == 0
    assert {p.origin for p in row.provenance} >= {
        "SOURCE_EXPLICIT",
        "DETERMINISTIC_DERIVED",
    }


def test_none_fee_needs_explicit_complete_evidence_and_unsupported_rule_blocks():
    source = dict(
        source_fee_key="F1",
        scope="STORE_PROCUREMENT",
        effective_from="2026-10-11",
        effective_to=None,
        mode="NONE",
        coverage="COMPLETE",
        currency="VND",
        components=[],
        covered_source_term_keys=[],
        covered_source_supplier_keys=[],
        evidence_reference="Synthetic reviewed no additional fees",
        reason="Explicit declaration",
    )
    row = case("payable_fees", [source])[0]
    assert not row.blockers and row.proposed_action == "CREATE_FEE_DECLARATION"
    bad = case("payable_fees", [{**source, "coverage": "UNKNOWN"}])[0]
    assert bad.classification == "INVALID" and bad.after is None
    component = dict(
        component_key="VAT",
        label="VAT",
        basis="PER_OFFER",
        source_term_key="T1",
        source_supplier_key=None,
        amount="5",
        condition="PERCENT_TAX",
    )
    unsupported = case(
        "payable_fees", [{**source, "mode": "PER_OFFER", "components": [component]}]
    )[0]
    assert unsupported.classification == "INVALID"


def test_inventory_declaration_does_not_invent_empty_or_accept_foreign_lot():
    ingredient, lot = uuid4(), uuid4()
    declaration = dict(
        kind="INVENTORY",
        ingredient_id=str(ingredient),
        state="CONFIRMED_EMPTY",
        observed_at="2026-10-10T02:00:00Z",
        covered_lot_ids=[],
        evidence_reference="Synthetic reviewed empty",
    )
    source = dict(source_declaration_key="INV-1", declaration=declaration)
    snapshot = dict(
        ingredients=[dict(id=str(ingredient), base_unit="l")],
        inventory_lots=[
            dict(
                id=str(lot),
                ingredient_id=str(ingredient),
                on_hand_quantity="1",
                updated_at="2026-10-10T01:00:00+00:00",
            )
        ],
    )
    row = case("scope_declarations", [source], snapshot)[0]
    assert "INVENTORY_NOT_EMPTY" in {b.code for b in row.blockers}
    unknown = {**declaration, "state": "UNKNOWN", "covered_lot_ids": [str(uuid4())]}
    row = case("scope_declarations", [{**source, "declaration": unknown}], snapshot)[0]
    assert "UNKNOWN_LOT" in {b.code for b in row.blockers}


def test_missing_sales_coverage_stays_missing_not_synthesized_zero():
    product = uuid4()
    source = dict(
        source_declaration_key="SALES-1",
        declaration=dict(
            kind="SALES_COVERAGE",
            product_ids=[str(product)],
            from_date="2026-10-08",
            to_date="2026-10-09",
            state="COMPLETE",
            evidence_reference="Synthetic complete claim",
        ),
    )
    snapshot = dict(
        products=[dict(id=str(product), selling_unit="cup")],
        sales_daily=[
            dict(product_id=str(product), sales_date="2026-10-09", quantity="0")
        ],
    )
    row = case("scope_declarations", [source], snapshot)[0]
    assert "SALES_COVERAGE_INCOMPLETE" in {b.code for b in row.blockers}


def test_declared_date_and_decimal_formats_keep_raw_meaning():
    product = uuid4()
    source = dict(
        product_id=product,
        sales_date="09/10/2026",
        quantity="1,25",
        unit="cup",
        business_report_key="R1",
    )
    rows = case(
        "sales",
        [source],
        dict(products=[dict(id=str(product), selling_unit="cup")]),
        semantics="daily_total",
        context_fields={"decimal_locale": "comma", "date_format": "DMY_SLASH"},
    )
    assert (
        rows[0].after.quantity == "1.25"
        and rows[0].after.sales_date.isoformat() == "2026-10-09"
    )
    assert not rows[0].blockers


def test_two_new_terms_cannot_overlap_inside_same_batch():
    supplier, ingredient = uuid4(), uuid4()
    source = dict(
        source_term_key="T1",
        supplier_id=supplier,
        ingredient_id=ingredient,
        effective_from="2026-10-11",
        effective_to=None,
        unit="l",
        pack_size_base_quantity="6",
        pack_cost="180000",
        currency="VND",
        minimum_order_quantity="1", price_basis="PER_PACK", price_quantity=None, price_unit=None,
        moq_basis="PACKS", moq_unit=None,
        lead_time_days=1,
        shelf_life_days=14,
        active=True,
        maximum_order_base_quantity=None,
    )
    snapshot = dict(
        suppliers=[dict(id=str(supplier))],
        ingredients=[dict(id=str(ingredient), base_unit="l")],
    )
    rows = case(
        "supplier_terms",
        [source, {**source, "source_term_key": "T2", "effective_from": "2026-11-01"}],
        snapshot,
    )
    assert len(rows) == 2 and all(
        "TERM_PERIOD_OVERLAP" in {b.code for b in r.blockers} for r in rows
    )
    valid = case(
        "supplier_terms",
        [
            {**source, "effective_to": "2026-10-31"},
            {**source, "source_term_key": "T2", "effective_from": "2026-11-01"},
        ],
        snapshot,
    )
    assert not any(r.blockers for r in valid)


def test_recipe_numeric_equivalence_is_not_header_conflict():
    product, i1, i2 = uuid4(), uuid4(), uuid4()
    source = dict(
        product_id=product,
        version=1,
        effective_from="2026-10-11",
        effective_to=None,
        quantity_basis="WHOLE_BATCH", yield_quantity="10",
        yield_unit="cup",
        process_loss_rate="0.2",
        ingredient_id=i1,
        quantity="1000",
        unit="ml",
    )
    snapshot = dict(
        products=[dict(id=str(product), selling_unit="cup")],
        ingredients=[
            dict(id=str(i1), base_unit="ml"),
            dict(id=str(i2), base_unit="ml"),
        ],
    )
    row = case(
        "recipes",
        [
            source,
            {
                **source,
                "yield_quantity": "10.0",
                "process_loss_rate": "0.20",
                "ingredient_id": i2,
            },
        ],
        snapshot,
    )[0]
    assert not row.blockers and len(row.after.lines) == 2


def test_existing_catalog_numeric_equivalence_is_no_op_not_metadata_conflict():
    product = uuid4()
    metadata = dto.ProductMetadata(
        name="Coffee", selling_unit="cup", sku="COFFEE", price="1.00", active=True
    )
    reservation = dto.EntityReservation(
        proposal_id=uuid4(),
        entity="product",
        source_business_key="COFFEE",
        reserved_canonical_id=product,
        metadata=metadata,
        evidence_reference="Owner reviewed identity",
        approval_revision="rev-1",
    )
    source = dict(
        source_business_key="COFFEE",
        name="Coffee",
        selling_unit="cup",
        sku="COFFEE",
        price="1.0",
        active=True,
    )
    row = case(
        "products",
        [source],
        dict(products=[dict(id=str(product), **metadata.model_dump(mode="json"))]),
        entities=(reservation,),
    )[0]
    assert (
        row.classification == "UNCHANGED"
        and row.proposed_action == "NO_OP"
        and not row.blockers
    )


def test_incomplete_proposal_rebuild_retains_approved_optional_rules():
    records = b"supplier_terms.source_term_key,supplier_terms.supplier_id,supplier_terms.ingredient_id,supplier_terms.effective_from,supplier_terms.effective_to,supplier_terms.unit,supplier_terms.pack_size_base_quantity,supplier_terms.pack_cost,supplier_terms.currency,supplier_terms.minimum_order_quantity,supplier_terms.price_basis,supplier_terms.price_quantity,supplier_terms.price_unit,supplier_terms.moq_basis,supplier_terms.moq_unit,supplier_terms.lead_time_days,supplier_terms.shelf_life_days,supplier_terms.active,supplier_terms.maximum_order_base_quantity\nT1,source-supplier,source-ingredient,2026-10-11,,l,6,100,VND,1,PER_PACK,,,PACKS,,1,14,true,\n"
    sheets, issues, _ = discover(uuid4(), parse_source(records, "csv"))
    context = dto.SourceContext(
        kind="source_context",
        source_system_key="SUP-A",
        report_type="terms",
        evidence_reference="reviewed scope",
        planned_arrival_expiry_rule=dto.PlannedArrivalExpiryRule(
            basis="ARRIVAL_PLUS_DECLARED_SHELF_LIFE_DAYS",
            evidence_reference="14 calendar days",
        ),
    )
    ready = [
        i.model_copy(
            update={
                "status": "resolved",
                "resolution": (
                    dto.ResolveRequest(resolution=context)
                    if i.issue_type == "source_context"
                    else None
                ),
            }
        )
        for i in issues
    ]
    original, missing = build_spec(sheets[0], ready, uuid4())
    assert not missing
    omitted = context.model_copy(update={"planned_arrival_expiry_rule": None})
    edited = [
        (
            i.model_copy(update={"resolution": dto.ResolveRequest(resolution=omitted)})
            if i.issue_type == "source_context"
            else i
        )
        for i in ready
    ]
    changed, missing = build_spec(sheets[0], edited, uuid4(), prior_spec=original)
    assert (
        not missing
        and changed.planned_arrival_expiry_rule == original.planned_arrival_expiry_rule
    )
