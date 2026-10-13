"""Hand-calculated supplier source semantics, independent of workbook layouts."""
from decimal import localcontext
from uuid import uuid4

import pytest
from tests.unit.test_import_preview import case
from app.application.contracts import import_mapping as dto


def term(**overrides):
    values = dict(source_term_key="T1", supplier_id=uuid4(), ingredient_id=uuid4(),
        effective_from="2026-01-01", effective_to=None, unit="g",
        pack_size_base_quantity="1000", pack_cost="100000", currency="VND",
        price_basis="PER_PACK", price_quantity=None, price_unit=None,
        moq_basis="PACKS", minimum_order_quantity="2", moq_unit=None,
        pack_label="thùng", lead_time_days=0, shelf_life_days=None, active=True,
        maximum_order_base_quantity=None)
    values.update(overrides)
    return values


def snapshot(value, unit="g"):
    return dict(suppliers=[dict(id=str(value["supplier_id"]))],
        ingredients=[dict(id=str(value["ingredient_id"]), base_unit=unit, expiry_tracking=False)])


def conversion(source="kg", target="g", factor="1000"):
    return dto.Conversion(kind="declared_conversion", from_unit=source, to_unit=target,
        factor=dto.Factor(numerator=factor, denominator="1"), evidence_reference="Owner physical scale")


@pytest.mark.parametrize("extra,unit,conversions,pack,cost,moq", [
    ({"unit":"kg", "pack_size_base_quantity":"1"}, "g", (conversion(),), "1000", "100000", 2),
    ({"price_basis":"PER_QUANTITY", "price_quantity":"1", "price_unit":"g", "pack_cost":"100"}, "g", (), "1000", "100000", 2),
    ({"unit":"l", "pack_size_base_quantity":"2", "price_basis":"PER_QUANTITY", "price_quantity":"1", "price_unit":"l", "pack_cost":"60000"}, "ml", (conversion("l","ml"),), "2000", "120000", 2),
    ({"moq_basis":"PHYSICAL_QUANTITY", "minimum_order_quantity":"2000", "moq_unit":"g"}, "g", (), "1000", "100000", 2),
    ({"moq_basis":"PHYSICAL_QUANTITY", "minimum_order_quantity":"1500", "moq_unit":"g"}, "g", (), "1000", "100000", 2),
    ({"price_basis":"PER_QUANTITY", "price_quantity":"2", "price_unit":"kg", "pack_cost":"200000"}, "g", (conversion(),), "1000", "100000", 2),
])
def test_exact_source_price_and_moq(extra, unit, conversions, pack, cost, moq):
    value = term(**extra)
    with localcontext() as ctx:
        ctx.prec = 2
        row = case("supplier_terms", [value], snapshot(value, unit), conversions=conversions)[0]
    assert not row.blockers
    assert (row.after.pack_size_base_quantity, row.after.pack_cost, row.after.minimum_order_packs) == (pack, cost, moq)
    assert row.after.unit == unit
    assert row.supplier_term_semantics.price_basis == value["price_basis"]
    assert row.supplier_term_semantics.moq_basis == value["moq_basis"]
    assert row.supplier_term_semantics.pack_label == "thùng"
    assert "price_basis" not in row.after.model_dump()
    assert "PAYABLE_FEES_NOT_ESTABLISHED" in {w.code for w in row.warnings}


@pytest.mark.parametrize("extra", [
    {"price_basis":None}, {"moq_basis":None}, {"unit":None},
    {"pack_size_base_quantity":None}, {"pack_size_base_quantity":"0"},
    {"price_basis":"PER_QUANTITY", "price_quantity":None, "price_unit":"g"},
    {"price_basis":"PER_QUANTITY", "price_quantity":"0", "price_unit":"g"},
    {"price_basis":"PER_QUANTITY", "price_quantity":"1", "price_unit":None},
    {"price_basis":"TIERED"}, {"minimum_order_quantity":"0"},
    {"minimum_order_quantity":"1.5"}, {"minimum_order_quantity":"-1"},
    {"minimum_order_quantity":"2147483648"},
    {"minimum_order_quantity":"NaN"}, {"pack_cost":"-1"}, {"pack_cost":"Infinity"},
    {"pack_size_base_quantity":"1e3"}, {"price_basis":"PER_PACK", "price_quantity":"1"},
    {"moq_basis":"PHYSICAL_QUANTITY", "moq_unit":None},
    {"moq_basis":"PHYSICAL_QUANTITY", "moq_unit":"l"},
    {"unit":"thùng"}, {"price_basis":"PER_QUANTITY", "price_quantity":"3", "price_unit":"g", "pack_cost":"1"},
])
def test_invalid_or_unsupported_source_blocks(extra):
    value = term(**extra)
    row = case("supplier_terms", [value], snapshot(value))[0]
    assert row.blockers and row.after is None


def test_zero_price_is_explicit_valid_and_currency_mismatch_blocks():
    value = term(pack_cost="0")
    row = case("supplier_terms", [value], snapshot(value))[0]
    assert row.after.pack_cost == "0" and not row.blockers
    value["currency"] = "USD"
    row = case("supplier_terms", [value], snapshot(value))[0]
    assert "CURRENCY_MISMATCH" in {b.code for b in row.blockers}


@pytest.mark.parametrize("rule,code", [
    (conversion("g", "ml", "1"), "INCOMPATIBLE_SUPPLIER_UNIT_CONVERSION"),
    (conversion("kg", "g", "999"), "INVALID_SUPPLIER_UNIT_FACTOR"),
])
def test_reviewed_conversion_cannot_override_physics(rule, code):
    value = term(unit=rule.from_unit)
    row = case("supplier_terms", [value], snapshot(value, rule.to_unit), conversions=(rule,))[0]
    assert [b.code for b in row.blockers] == [code]


@pytest.mark.parametrize("budget,expected", [("199999", None), ("200000", 2)])
def test_normalized_offer_small_exact_procurement_oracle(budget, expected):
    from fractions import Fraction
    from scripts.procurement_demo_cases import envelope, snapshot as demand_snapshot
    from app.application.contracts.procurement import ProcurementInput
    from app.application.use_cases.procurement import evaluate_procurement_basket, rational
    value = term(price_basis="PER_QUANTITY", price_quantity="1", price_unit="g", pack_cost="100",
        moq_basis="PHYSICAL_QUANTITY", minimum_order_quantity="1500", moq_unit="g")
    canonical = case("supplier_terms", [value], snapshot(value))[0].after
    request = ProcurementInput.model_validate(envelope(
        demand_snapshot([[1500,0,0,0,0,0,0]], [{0:1}]), [dict(ingredient=0,
            pack=canonical.pack_size_base_quantity, cost=canonical.pack_cost,
            minimum=canonical.minimum_order_packs, upper=3)], budget=budget))
    results = {n: evaluate_procurement_basket(request, (n,)) for n in range(4)}
    assert results[0] is not None and results[1] is None
    assert evaluate_procurement_basket(request, (1.5,)) is None
    # Independent one-ingredient oracle: positive count >=2, quantity >=1500,
    # goods=100000*count, no stock, explicitly NONE fees, budget as declared.
    oracle = [n for n in range(4) if n >= 2 and 1000*n >= 1500 and 100000*n <= int(budget)]
    assert (min(oracle) if oracle else None) == expected
    if expected is None:
        assert results[2] is None
    else:
        candidate = results[2]
        assert rational(candidate.outlay) == Fraction(200000)
        assert all(rational(s.served) == 1500 for s in candidate.services)


def test_nonrepresentable_canonical_money_blocks_without_rounding():
    value = term(price_basis="PER_QUANTITY", price_quantity="10000000000000000000",
        price_unit="g", pack_size_base_quantity="1", pack_cost="1")
    row = case("supplier_terms", [value], snapshot(value))[0]
    assert [b.code for b in row.blockers] == ["INVALID_SOURCE_VALUE"]


def test_locale_chain_and_physical_moq_evidence():
    value = term(unit="kg", pack_size_base_quantity="1", minimum_order_quantity="1,5",
        moq_basis="PHYSICAL_QUANTITY", moq_unit="kg", price_basis="PER_QUANTITY",
        price_quantity="2", price_unit="kg", pack_cost="200000")
    row = case("supplier_terms", [value], snapshot(value), conversions=(conversion(),),
        context_fields={"decimal_locale":"comma"})[0]
    assert not row.blockers and row.after.minimum_order_packs == 2 and row.after.pack_cost == "100000"
    p = next(p for p in row.provenance if p.field == "minimum_order_packs")
    assert p.source_value == "1,5" and p.source_column_index is not None
    assert p.applied_rule_ids == ("declared_decimal_locale", "conversion:Owner physical scale", "supplier:physical_moq_ceil_packs")
    maximum = next(p for p in row.provenance if p.field == "maximum_order_base_quantity")
    assert maximum.source_value == "" and maximum.origin == "SOURCE_EXPLICIT"
    assert row.after.maximum_order_base_quantity is None


def test_new_review_replaces_implicit_one_rule_without_mutating_retained_profile():
    from app.application.import_analysis import discover, build_spec
    from app.infrastructure.import_parser import parse_source
    from app.application.contracts.import_domains import TermSource, TermValue
    import csv, io
    value = term()
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(["supplier_terms." + k for k in value])
    writer.writerow([str(v).lower() if isinstance(v, bool) else str(v) if v is not None else "" for v in value.values()])
    sheets, issues, _ = discover(uuid4(), parse_source(content.getvalue().encode(), "csv"))
    context = dto.SourceContext(kind="source_context", source_system_key="SUP", report_type="PRICE", evidence_reference="Review")
    issues = [i.model_copy(update={"status":"resolved", "resolution":dto.ResolveRequest(resolution=context)
        if i.issue_type == "source_context" else None}) for i in issues]
    old_rule = dto.Normalization(rule_id="declared_pack_pricing_basis", kind="exact_scale",
        fields=("pack_cost", "pack_size_base_quantity"), parameter="PACK_COST_FROM_SOURCE_UNIT_PRICE", evidence_reference="Historical")
    reviewed, missing = build_spec(sheets[0], issues, uuid4(), prior_normalizations=(old_rule,))
    assert not missing and reviewed.supports_supplier_basis() and not reviewed.normalizations
    historical = reviewed.model_copy(update={"normalizations":(old_rule,)})
    assert not historical.supports_supplier_basis() and historical.normalizations == (old_rule,)
    # Retained canonical schemas continue to accept canonical whole-pack terms.
    canonical = {k:v for k,v in value.items() if k in TermSource.model_fields}
    canonical["minimum_order_packs"] = 2
    assert TermValue.model_validate(canonical).pack_cost == "100000"
