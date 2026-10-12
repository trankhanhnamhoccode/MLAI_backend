"""Hand-calculated scalar sources, pure existing row/preview invariants."""

from uuid import uuid4
from datetime import datetime, timezone
import json
import pytest
from pydantic import ValidationError
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_field_values import (
    ProfileConstant,
    ImportValue,
    ImportValueRequirement,
    SharedValueResolution,
)
from app.application.import_preview import normalize, make_preview, RowBlocked
from app.application.import_analysis import discover, build_spec
from app.infrastructure.import_parser import parse_source
from app.infrastructure.import_suggestions import sheet_payload


def constant(target, value):
    return ProfileConstant(
        target_field=target,
        value=value,
        declaration_id=uuid4(),
        evidence_reference="explicit",
    )


def declared(target, value):
    return ImportValue(
        target_field=target,
        value=value,
        declaration_id=uuid4(),
        evidence_reference="this import only",
    )


def spec(schema, fields, rules=(), norms=()):
    return dto.ProfileSpec(
        scope=dto.ProfileScope(source_system_key="POS", report_type="DAILY"),
        schema=schema,
        structure=dto.Structure(
            sheet_roles=(schema,), header_rules=fields, schema_signature="fixture"
        ),
        field_bindings=tuple(
            dto.FieldBinding(
                source_column_index=i,
                source_header=f,
                target_field=schema + "." + f,
                requiredness="required",
                ignored=False,
            )
            for i, f in enumerate(fields)
        ),
        shared_field_bindings=rules,
        normalizations=norms,
        source_provenance=dto.SourceProvenance(
            declared_by=uuid4(), evidence_references=("reviewed",)
        ),
    )


def row(*values):
    return {
        "cells": [
            dict(column_index=i, raw=v, kind="text") for i, v in enumerate(values)
        ]
    }


def test_shared_sales_values_preserve_zero_and_declared_date_provenance():
    product = uuid4()
    report = declared("sales.business_report_key", "POS-A-20261010")
    unit = constant("sales.unit", "ly")
    s = spec(
        "sales",
        ("product_id", "sales_date", "quantity"),
        (unit, ImportValueRequirement(target_field=report.target_field)),
        (
            dto.Normalization(
                rule_id="date",
                kind="date_format",
                fields=("sales_date",),
                parameter="DMY_SLASH",
                evidence_reference="format",
            ),
        ),
    )
    for q in ("12", "0"):
        result, prov = normalize(row(str(product), "10/10/2026", q), s, (report,))
        assert (
            result.quantity == q
            and str(result.sales_date) == "2026-10-10"
            and result.unit == "ly"
        )
        by = {p.field: p for p in prov}
        assert (
            by["unit"].value_source == "PROFILE_CONSTANT"
            and by["unit"].declaration_id == unit.declaration_id
        )
        assert (
            by["business_report_key"].value_source == "IMPORT_VALUE"
            and by["business_report_key"].declaration_id == report.declaration_id
        )
    with pytest.raises(RowBlocked, match="MISSING_IMPORT_VALUE"):
        normalize(row(str(product), "10/10/2026", "0"), s)
    assert "POS-A-20261010" not in s.model_dump_json()


@pytest.mark.parametrize(
    "target,scope,value",
    [
        ("sales.quantity", "IMPORT_VALUE", "0"),
        ("sales.product_id", "PROFILE_CONSTANT", str(uuid4())),
        ("sales.business_report_key", "PROFILE_CONSTANT", "R"),
        ("scope_declarations.declaration", "IMPORT_VALUE", "{}"),
        ("products.active", "PROFILE_CONSTANT", 0),
        ("recipes.version", "IMPORT_VALUE", True),
        ("sales.unit", "PROFILE_CONSTANT", None),
        ("recipes.process_loss_rate", "PROFILE_CONSTANT", 0.2),
    ],
)
def test_forbidden_scopes_nested_and_scalar_types(target, scope, value):
    with pytest.raises(ValidationError):
        SharedValueResolution(
            target_field=target, scope=scope, value=value, evidence_reference="explicit"
        )


def test_missing_null_zero_false_are_distinct_and_invalid_rows_still_fail():
    with pytest.raises(ValidationError):
        SharedValueResolution(
            target_field="products.active",
            scope="PROFILE_CONSTANT",
            evidence_reference="missing",
        )
    assert constant("products.active", False).value is False
    product_spec = spec(
        "products",
        ("name", "selling_unit", "sku", "price", "source_business_key"),
        (constant("products.active", False),),
    )
    product, _ = normalize(row("Tea", "cup", None, None, "P-1"), product_spec)
    assert product.active is False and product.price is None
    end = declared("recipes.effective_to", None)
    assert end.value is None
    for blank in ("", " "):
        with pytest.raises(ValidationError, match="EXPLICIT_NULL_OR_NONBLANK_REQUIRED"):
            declared("recipes.effective_to", blank)
    fields = ("product_id", "ingredient_id", "quantity", "unit")
    rules = (
        constant("recipes.yield_quantity", "10"),
        constant("recipes.yield_unit", "ly"),
        constant("recipes.process_loss_rate", "0.2"),
        ImportValueRequirement(target_field="recipes.version"),
        ImportValueRequirement(target_field="recipes.effective_from"),
        ImportValueRequirement(target_field="recipes.effective_to"),
    )
    s = spec("recipes", fields, rules)
    imports = (
        declared("recipes.version", 1),
        declared("recipes.effective_from", "2026-10-10"),
        end,
    )
    result, _ = normalize(row(str(uuid4()), str(uuid4()), "1000", "ml"), s, imports)
    assert result.effective_to is None and result.process_loss_rate == "0.2"
    for invalid_date in ("2026-02-30", "2026-13-01", "10000-01-01"):
        with pytest.raises(RowBlocked, match="INVALID_SOURCE_VALUE"):
            normalize(
                row(str(uuid4()), str(uuid4()), "1000", "ml"),
                s,
                (imports[0], declared("recipes.effective_from", invalid_date), end),
            )
    for bad in ("NaN", "Infinity", "-1", "1e3", "false"):
        broken = s.model_copy(
            update={
                "shared_field_bindings": tuple(
                    (
                        constant("recipes.yield_quantity", bad)
                        if r.target_field == "recipes.yield_quantity"
                        else r
                    )
                    for r in rules
                )
            }
        )
        with pytest.raises((ValueError, RowBlocked)):
            normalize(row(str(uuid4()), str(uuid4()), "1000", "ml"), broken, imports)
    with pytest.raises(RowBlocked, match="INVALID_SOURCE_VALUE"):
        normalize(
            row(str(uuid4()), str(uuid4()), "1000", "ml"),
            s,
            (declared("recipes.version", 0), *imports[1:]),
        )


def test_column_and_shared_conflict_and_invalid_copied_input_revalidated():
    s = spec("sales", ("unit",))
    with pytest.raises(ValidationError):
        dto.ProfileSpec.model_validate(
            {
                **s.model_dump(),
                "shared_field_bindings": [constant("sales.unit", "ly").model_dump()],
            }
        )
    forged = s.model_copy(
        update={"shared_field_bindings": (constant("sales.unit", "ly"),)}
    )
    with pytest.raises(ValidationError):
        normalize(row("cup"), forged)
    duplicate = s.model_copy(
        update={"field_bindings": s.field_bindings + s.field_bindings}
    )
    with pytest.raises(ValidationError):
        normalize(row("cup"), duplicate)
    with pytest.raises(ValidationError):
        SharedValueResolution(
            target_field="sales.unit",
            scope="PROFILE_CONSTANT",
            value="ly",
            replace_source_column_index=0,
            evidence_reference="switch",
        )


def test_required_sources_use_shared_rules_and_values_not_sent_to_provider():
    sheets, issues, sources = discover(
        uuid4(),
        parse_source(
            b"sales.product_id,sales.sales_date,sales.quantity\nP,2026-10-10,0\n", "csv"
        ),
    )
    context = dto.SourceContext(
        kind="source_context",
        source_system_key="POS",
        report_type="DAILY",
        sales_semantics="daily_total",
        evidence_reference="explicit",
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
    rules = (
        constant("sales.unit", "SECRET-UNIT"),
        ImportValueRequirement(target_field="sales.business_report_key"),
    )
    sh = sheets[0].model_copy(
        update={
            "shared_field_bindings": rules,
            "import_values": (declared("sales.business_report_key", "SECRET-BATCH"),),
        }
    )
    built, missing = build_spec(sh, issues, uuid4())
    assert not missing and len(built.shared_field_bindings) == 2
    payload = sheet_payload(sh, sources[0], "file.csv", {}, None)
    assert "SECRET-" not in json.dumps(payload)


def test_shared_recipe_dates_and_units_cannot_bypass_overlap_and_keep_derivation_ref():
    product, ingredient = uuid4(), uuid4()
    columns = ("product_id", "ingredient_id", "quantity", "unit")
    rules = (
        constant("recipes.yield_quantity", "1,25"),
        constant("recipes.yield_unit", "cup"),
        constant("recipes.process_loss_rate", "0"),
        ImportValueRequirement(target_field="recipes.version"),
        ImportValueRequirement(target_field="recipes.effective_from"),
        ImportValueRequirement(target_field="recipes.effective_to"),
    )
    norms = (
        dto.Normalization(
            rule_id="decimal",
            kind="decimal_locale",
            fields=("yield_quantity",),
            parameter="comma",
            evidence_reference="locale",
        ),
    )
    s = spec("recipes", columns, rules, norms)
    values = (
        declared("recipes.version", 1),
        declared("recipes.effective_from", "2026-10-10"),
        declared("recipes.effective_to", None),
    )
    result, provenance = normalize(
        row(str(product), str(ingredient), "1000", "ml"), s, values
    )
    assert result.yield_quantity == "1.25"
    origin = next(p for p in provenance if p.field == "yield_quantity")
    assert (
        origin.value_source == "PROFILE_CONSTANT"
        and origin.declaration_id == rules[0].declaration_id
        and origin.applied_rule_ids == ("decimal",)
    )
    parsed = parse_source(
        (
            "recipes.product_id,recipes.ingredient_id,recipes.quantity,recipes.unit\n"
            + str(product)
            + ","
            + str(ingredient)
            + ",1000,g\n"
        ).encode(),
        "csv",
    )
    sheets, _, sources = discover(uuid4(), parsed)
    snapshot = {
        k: []
        for k in (
            "products",
            "ingredients",
            "suppliers",
            "sales_daily",
            "inventory_lots",
            "inventory_movements",
            "recipes",
            "recipe_lines",
            "supplier_terms",
        )
    }
    snapshot.update(
        products=[dict(id=str(product), selling_unit="cup")],
        ingredients=[dict(id=str(ingredient), base_unit="ml")],
        recipes=[
            dict(
                id=str(uuid4()),
                product_id=str(product),
                version=2,
                effective_from="2026-10-09",
                effective_to=None,
            )
        ],
    )
    preview = make_preview(
        sources,
        {str(sheets[0].sheet_id): s},
        snapshot,
        datetime(2026, 10, 10, 3, tzinfo=timezone.utc),
        "Asia/Ho_Chi_Minh",
        "VND",
        {str(sheets[0].sheet_id): values},
    )[0]
    assert {b.code for b in preview.blockers} >= {
        "UNIT_MISMATCH",
        "RECIPE_PERIOD_OVERLAP",
    }
