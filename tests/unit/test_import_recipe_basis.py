"""Exact source semantics; synthetic inputs independent of demo workbook layouts."""
from decimal import Decimal, localcontext
from datetime import date
from uuid import uuid4

import pytest
from tests.unit.test_import_preview import case
from app.application.contracts import import_mapping as dto
from app.application.import_preview import normalize, RowBlocked
from app.domain.demand.bom import DatedRecipe, DemandPoint, RecipeLine, expand_dated_bom


def recipe(**extra):
    return dict(product_id=uuid4(), ingredient_id=uuid4(), version=1,
        effective_from="2026-01-01", effective_to=None, quantity_basis="WHOLE_BATCH",
        yield_quantity="10", yield_unit="cup", quantity="1000", unit="g",
        process_loss_rate="0", **extra)


def snapshot(value):
    return dict(products=[dict(id=str(value["product_id"]), selling_unit="cup")],
        ingredients=[dict(id=str(value["ingredient_id"]), base_unit=value["unit"])])


@pytest.mark.parametrize("basis,quantity,loss,unit,expected", [
    ("PER_SERVING", "100", "0", "g", "4000"),
    ("WHOLE_BATCH", "1000", "0", "g", "4000"),
    ("WHOLE_BATCH", "1000", "0.2", "ml", "5000"),
    ("PER_SERVING", "100", "0.2", "ml", "5000"),
])
def test_basis_to_canonical_to_dated_bom(basis, quantity, loss, unit, expected):
    value = recipe(); value.update(quantity_basis=basis, quantity=quantity,
        process_loss_rate=loss, unit=unit)
    with localcontext() as ctx:
        ctx.prec = 2  # Normalization must not depend on ambient Decimal precision.
        rows = case("recipes", [value], snapshot(value))
    row = rows[0]
    assert not row.blockers
    after = row.after
    assert after.lines[0].quantity == "1000"
    evidence = row.line_provenance[0]
    assert evidence.quantity_basis == basis
    assert evidence.provenance["quantity"].source_value == quantity
    assert evidence.provenance["process_loss_rate"].source_value == loss
    converted = DatedRecipe(uuid4(), after.product_id, after.effective_from,
        after.effective_to, Decimal(after.yield_quantity), Decimal(after.process_loss_rate),
        tuple(RecipeLine(l.ingredient_id, l.unit, Decimal(l.quantity)) for l in after.lines))
    result = expand_dated_bom((DemandPoint("BASE", after.product_id, date(2026,1,2), Decimal(40)),), (converted,))
    assert not result.gaps and result.totals[0].quantity == Decimal(expected)


@pytest.mark.parametrize("field,bad", [
    ("quantity_basis", None), ("quantity_basis", "1sp"), ("quantity_basis", ""),
    ("yield_quantity", None), ("yield_quantity", "0"), ("yield_quantity", "-1"),
    ("process_loss_rate", "1"),
    ("process_loss_rate", "-0.2"), ("process_loss_rate", "20%"),
    ("process_loss_rate", "NaN"), ("unit", None), ("yield_unit", None),
])
def test_invalid_facts_block_without_defaults(field, bad):
    value = recipe(); value[field] = bad
    rows = case("recipes", [value], snapshot(recipe()) if field == "unit" else snapshot(value))
    assert rows[0].blockers and rows[0].after is None


def test_output_unit_must_be_selling_unit():
    value = recipe(); value["yield_unit"] = "batch"
    rows = case("recipes", [value], snapshot(value))
    assert "UNIT_MISMATCH" in [b.code for b in rows[0].blockers]


def test_exact_conversion_and_basis_both_apply_once():
    value = recipe(); value.update(quantity_basis="PER_SERVING", quantity="0.1", unit="kg")
    data = snapshot(value); data["ingredients"][0]["base_unit"] = "g"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="kg", to_unit="g",
        factor=dto.Factor(numerator="1000", denominator="1"), evidence_reference="Explicit mass units")
    rows = case("recipes", [value], data, conversions=(conversion,))
    assert not rows[0].blockers and rows[0].after.lines[0].quantity == "1000"
    p = rows[0].line_provenance[0].provenance["quantity"]
    assert p.applied_rule_ids == ("conversion:Explicit mass units", "recipe:per_serving_times_yield")
    assert p.source_value == "0.1"


def test_locale_conversion_basis_preserve_entire_rule_chain():
    value = recipe(); value.update(quantity_basis="PER_SERVING", quantity="0,1", unit="kg",
        yield_quantity="10", process_loss_rate="0")
    data = snapshot(value); data["ingredients"][0]["base_unit"] = "g"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="kg", to_unit="g",
        factor=dto.Factor(numerator="1000", denominator="1"), evidence_reference="Mass")
    rows = case("recipes", [value], data, conversions=(conversion,), context_fields={"decimal_locale":"comma"})
    assert rows[0].after.lines[0].quantity == "1000"
    p = rows[0].line_provenance[0].provenance["quantity"]
    assert p.applied_rule_ids == ("declared_decimal_locale", "conversion:Mass", "recipe:per_serving_times_yield")
    assert p.source_value == "0,1"


def test_declared_mass_to_volume_is_unsupported():
    value = recipe()
    data = snapshot(value); data["ingredients"][0]["base_unit"] = "ml"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="g", to_unit="ml",
        factor=dto.Factor(numerator="1", denominator="1"), evidence_reference="No density authority")
    rows = case("recipes", [value], data, conversions=(conversion,))
    assert [b.code for b in rows[0].blockers] == ["INCOMPATIBLE_RECIPE_UNIT_CONVERSION"]


def test_conversion_cannot_accept_exponent_or_percentage_representation():
    value = recipe(); value.update(unit="kg", quantity="1e3")
    data = snapshot(value); data["ingredients"][0]["base_unit"] = "g"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="kg", to_unit="g",
        factor=dto.Factor(numerator="1000", denominator="1"), evidence_reference="Mass")
    rows = case("recipes", [value], data, conversions=(conversion,))
    assert [b.code for b in rows[0].blockers] == ["INVALID_SOURCE_VALUE"]


@pytest.mark.parametrize("from_unit,to_unit,factor,code", [
    ("g", "L", "1", "INCOMPATIBLE_RECIPE_UNIT_CONVERSION"),
    ("kg", "g", "1", "INVALID_RECIPE_UNIT_FACTOR"),
    ("bag", "g", "100", "UNSUPPORTED_RECIPE_UNIT_CONVERSION"),
])
def test_conversion_requires_supported_compatible_exact_rule(from_unit, to_unit, factor, code):
    value = recipe(); value["unit"] = from_unit
    data = snapshot(value); data["ingredients"][0]["base_unit"] = to_unit
    conversion = dto.Conversion(kind="declared_conversion", from_unit=from_unit, to_unit=to_unit,
        factor=dto.Factor(numerator=factor, denominator="1"), evidence_reference="Reviewed source assertion")
    rows = case("recipes", [value], data, conversions=(conversion,))
    assert [b.code for b in rows[0].blockers] == [code]


def test_missing_basis_is_a_mapping_gap_not_a_header_guess():
    value = recipe(); del value["quantity_basis"]
    with pytest.raises(AssertionError, match="recipes.quantity_basis"):
        case("recipes", [value], snapshot(value))
