"""Independent contextual proposals: no source proof, identity or business defaults."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.application.import_analysis import discover, build_spec
from app.application.import_descriptors import sheet_rules, options
from app.application.import_templates import TEMPLATES, validate_templates
from app.infrastructure.import_parser import parse_source


@pytest.mark.parametrize("headers,schema,target", [
    (("Ngày bán", "Tên món", "SL", "ĐVT"), "sales", "sales.quantity"),
    (("Ngay su dung", "Ten NL", " SL ", "DVT"), "usage_history", "usage_history.quantity"),
    (("Ngày kiểm kê", "Mặt hàng tồn", "SL", "Mã lô"), "inventory_count", "inventory_count.on_hand"),
    (("Ngày thực nhận", "Mã nhận hàng", "Tên NL", "SL"), "inventory_receipts", "inventory_receipts.quantity"),
])
def test_quantity_abbreviation_requires_workflow_context(headers, schema, target):
    result = sheet_rules(headers, "unrelated display name")
    assert result.schema == schema
    index = next(i for i, h in enumerate(headers) if h.strip() == "SL")
    hint = result.columns[index]
    assert hint.target == target and hint.requires_review
    assert "CURATED:" in hint.reason and ("/2:" if schema=='sales' else "/1:") in hint.reason
    assert result.low_quality  # A proposed target is not a fully reviewed spec.


@pytest.mark.parametrize("name", ["sales", "usage_history", "inventory_receipts", "inventory_count", "random"])
def test_generic_headers_or_sheet_name_never_establish_workflow(name):
    result = sheet_rules(("SL", "ĐVT", "NSX"), name)
    assert result.schema is None
    assert all(c.target is None for c in result.columns)


@pytest.mark.parametrize("samples,reason", [
    ((("2026-03-01", "01/04/2026"),), "MANUFACTURE_DATE_NOT_SUPPORTED"),
    ((("Maker Alpha", "Maker Beta"),), "MANUFACTURER_NOT_SUPPORTED"),
    ((("2026-03-01", "Maker Beta"),), "NSX_MEANING_AMBIGUOUS"),
    ((("46200",),), "NSX_MEANING_AMBIGUOUS"),
    ((("31-Mar-2026",),), "NSX_MEANING_AMBIGUOUS"),
    (((),), "NSX_MEANING_AMBIGUOUS"),
])
def test_nsx_does_not_become_received_date_or_supplier(samples, reason):
    hints = sheet_rules(("NSX", "HSD"), "sales", samples=samples + ((),)).columns
    assert hints[0].target is None and hints[0].candidates == ()
    assert reason in hints[0].reason and hints[0].ambiguous


def test_lexical_samples_are_bounded_and_never_emitted_in_reason():
    values = ("2026-03-01",) * 8 + ("PRIVATE-UNBOUNDED-TAIL",)
    hint = sheet_rules(("NSX", "HSD"), "x", samples=(values, ())).columns[0]
    assert "MANUFACTURE_DATE_NOT_SUPPORTED" in hint.reason
    assert "PRIVATE" not in hint.reason and "2026-03-01" not in hint.reason


@pytest.mark.parametrize("headers", [
    ("Món bán", "Thành phần", "Lượng / 1 SP", "Ver"),
    (" ver ", " LUONG / 1 SP ", "THANH PHAN", "mon ban"),
])
def test_recipe_candidates_explain_basis_and_integer_review(headers):
    sheets, issues, _ = discover(uuid4(), parse_source(
        (",".join(headers) + "\n" + ",".join(["1"] * len(headers)) + "\n").encode(), "csv"))
    assert sheets[0].selected_type == "recipes"
    columns = {i.source_location.source_column_index: i for i in issues if i.issue_type == "column"}
    for index, header in enumerate(headers):
        key = header.strip().casefold()
        if key == "ver":
            target, reason, review = "recipes.version", "INTEGER_VERSION_REQUIRED", "integer_recipe_version"
        elif "1 sp" in key:
            target, reason, review = "recipes.quantity", "PER_SERVING_VS_WHOLE_YIELD_REVIEW", "quantity_basis,yield_and_loss"
        else:
            continue
        issue = columns[index]
        assert issue.target_field is None and issue.candidate_targets == (target,)
        assert issue.field_category == "B" and issue.status not in {"resolved", "auto_mapped"}
        assert reason in issue.suggestion_reason and "REVIEW:" + review in issue.suggestion_reason
        assert "CURATED:tabular.recipe/1:" in issue.suggestion_reason


@pytest.mark.parametrize("headers", [
    ("Vendor", "Material", "Pack Size", "Order UOM", "MOQ", "Giá mua"),
    (" gia mua ", " moq ", "ORDER UOM", "pack size", "material", "vendor"),
])
def test_supplier_candidates_do_not_claim_physical_unit_price_or_moq_basis(headers):
    result = sheet_rules(headers, "arbitrary")
    assert result.schema == "supplier_terms"
    sheets, issues, _ = discover(uuid4(), parse_source(
        (",".join(headers) + "\n" + ",".join(["1"] * len(headers)) + "\n").encode(), "csv"))
    assert sheets[0].selected_type == "supplier_terms"
    columns = {i.source_location.source_column_index: i for i in issues if i.issue_type == "column"}
    expected = {
        "order uom": ("supplier_terms.pack_label", "PACK_LABEL_NOT_PHYSICAL_UNIT", "pack_label_vs_physical_unit"),
        "moq": ("supplier_terms.minimum_order_quantity", "MOQ_PACK_VS_BASE_UNIT_REVIEW", "moq_basis_and_unit"),
        "gia mua": ("supplier_terms.pack_cost", "PER_PACK_VS_UNIT_PRICE_REVIEW", "price_basis_and_denominator"),
    }
    from app.application.import_templates import normalized_hint
    for index, (header, hint) in enumerate(zip(headers, result.columns)):
        if normalized_hint(header) not in expected:
            continue
        target, reason, review = expected[normalized_hint(header)]
        assert hint.target is None and hint.candidates == (target,) and hint.requires_review
        assert reason in hint.reason and "REVIEW:" + review in hint.reason
        assert "CURATED:tabular.supplier-pack/1:" in hint.reason
        issue = columns[index]
        assert issue.target_field is None and issue.candidate_targets == (target,)
        assert issue.field_category == "B" and issue.status == "ambiguous"
        assert issue.suggestion_reason == hint.reason


@pytest.mark.parametrize("content,missing_fields", [
    ("Món bán,Thành phần,Lượng / 1 SP,Ver\nP,I,2,1\n",
     {"recipes.yield_quantity", "recipes.yield_unit", "recipes.quantity_basis",
      "recipes.unit", "recipes.effective_from"}),
    ("Món bán,Thành phần,Lượng / 1 SP,Yield\nP,I,2,4\n",
     {"recipes.quantity_basis", "recipes.unit", "recipes.effective_from"}),
    ("Vendor,Material,Pack Size,MOQ,Giá mua\nV,I,3,2,10\n",
     {"supplier_terms.price_basis", "supplier_terms.price_quantity", "supplier_terms.price_unit",
      "supplier_terms.unit", "supplier_terms.effective_from", "supplier_terms.moq_basis"}),
])
def test_required_semantics_without_defaults_stay_missing(content, missing_fields):
    sheets, issues, _ = discover(uuid4(), parse_source(content.encode(), "csv"))
    spec, missing = build_spec(sheets[0], issues, uuid4())
    assert spec is None and missing_fields <= set(missing)
    if sheets[0].selected_type == 'recipes':
        assert 'recipes.process_loss_rate' not in missing  # Approved effective-zero policy.
    assert not sheets[0].shared_field_bindings and not sheets[0].import_values


def test_mixed_workflows_and_negative_evidence_remain_ambiguous():
    headers = ("Ngày bán", "Tên món", "SL", "Ngày sử dụng", "Tên NL", "ĐVT")
    result = sheet_rules(headers, "sales")
    assert result.schema is None
    assert result.columns[2].target is None
    assert set(result.columns[2].candidates) == {"sales.quantity", "usage_history.quantity"}
    manual = sheet_rules(headers, "x", selected="sales")
    assert manual.columns[2].target is None and manual.columns[2].ambiguous
    # A date from another workflow is negative evidence even without a complete second template.
    assert sheet_rules(("Ngày bán", "Tên món", "SL", "Ngày kiểm kê"), "x").columns[2].target is None
    assert sheet_rules(("Món bán", "Thành phần", "Lượng / 1 SP", "Ver", "Ngày bán"), "x").schema is None


def test_mixed_layout_has_no_targets_and_known_unsupported_guard_stays_first():
    mixed = sheet_rules(("Ngày sử dụng", "Tên NL", "SL", "Món bán", "Thành phần"), "x")
    assert mixed.schema is None and all(c.target is None for c in mixed.columns)
    assert mixed.columns[2].candidates == ("usage_history.quantity",)
    unsupported = sheet_rules(("Ngày bán", "Tên món", "SL", "Ngày sử dụng", "Tên NL",
                               "Loại điều kiện", "Áp dụng cho NL"), "x")
    assert unsupported.schema is None and not unsupported.low_quality
    assert all(c.target is None for c in unsupported.columns)


def test_duplicate_target_keeps_both_columns_and_explicit_canonical_behavior():
    result = sheet_rules(("Ngày sử dụng", "Tên NL", "SL", "Lượng thực dùng"), "x")
    assert result.schema == "usage_history"
    assert all(result.columns[i].target is None for i in (2, 3))
    assert all(result.columns[i].candidates == ("usage_history.quantity",) for i in (2, 3))
    assert all(result.columns[i].reason.startswith("DUPLICATE_OR_AMBIGUOUS_TARGET") for i in (2, 3))
    assert "CURATED:tabular.usage/1:quantity" in result.columns[2].reason
    exact = sheet_rules(("sales.sales_date", "sales.product_id", "sales.quantity"), "x")
    assert exact.schema == "sales"
    assert all(c.reason == "EXACT_CANONICAL_HEADER" for c in exact.columns)


def test_registry_rejects_missing_or_unsupported_targets():
    supported = {d: frozenset(o.key for o in options(d) if o.available)
                 for d in {t.schema for t in TEMPLATES}}
    validate_templates(TEMPLATES, supported)
    first = TEMPLATES[0]
    for target in ("sales.invented", "payable_fees.tax_percent"):
        bad = replace(first, rules=(replace(first.rules[0], target=target),))
        with pytest.raises(ValueError, match="supported target"):
            validate_templates((bad,), supported)


def test_layout_variants_preserve_raw_signature_and_require_full_manual_semantics():
    body = "Notes\nMore notes\n ĐVT ,SL,Ten NL,Ngay su dung\ng,2,UNKNOWN-NL,2026-02-01\n".encode()
    sheets, issues, raw = discover(uuid4(), parse_source(body, "csv"))
    assert sheets[0].header_row == 3 and sheets[0].selected_type == "usage_history"
    assert sheets[0].profile_id is None
    assert raw[0]["rows"][0]["cells"][1]["raw"] == "2"
    assert all(i.profile_ref is None and i.resolution is None for i in issues)
    assert all(i.status not in {"resolved", "auto_mapped"} for i in issues)
    spec, missing = build_spec(sheets[0], issues, uuid4())
    assert spec is None and "source_context" in missing
    assert "column:1" in missing  # Curated semantic hints cannot bypass build_spec's whitelist.
    assert not sheets[0].shared_field_bindings and not sheets[0].import_values


def test_missing_semantics_and_unsupported_mixed_layouts_are_not_filled():
    for headers in (("NCT", "Tên hàng", "SLN", "ĐVT", "Giá nhập"),
                    ("Loại điều kiện", "Áp dụng cho NL", "Giá trị"),
                    ("Date", "Weekend", "Holiday")):
        assert sheet_rules(headers, "sales").schema is None
    sheets, issues, _ = discover(uuid4(), parse_source(
        "Ngày sử dụng,Tên NL,SL\n2026-03-01,unbound,1\n".encode(), "csv"))
    spec, missing = build_spec(sheets[0], issues, uuid4())
    assert spec is None and "usage_history.unit" in missing
    assert not any(i.target_field and i.target_field.endswith("loss_rate") for i in issues)


def test_provider_cannot_overwrite_new_fixed_contextual_target(monkeypatch):
    import io
    import json
    from pydantic import SecretStr
    from app.config import Settings
    from app.infrastructure import import_suggestions as gateway

    sheets, issues, raw = discover(uuid4(), parse_source(
        "Ngày sử dụng,Tên NL,SL,ĐVT\n2026-03-01,unknown,2,g\n".encode(), "csv"))
    columns = [i for i in issues if i.issue_type == "column"]
    rule = dict(columns=[dict(source_column_index=i.source_location.source_column_index,
                              target_field=i.target_field) for i in columns])
    output = dict(version="sheet_suggestion/1", sheet_type="usage_history", confidence=1.0,
                  warnings=[], columns=[dict(source_column_index=n, target_field=i.target_field,
                                             confidence=1.0) for n, i in enumerate(columns)])
    output["columns"][1]["target_field"] = "usage_history.evidence_reference"

    class Transport:
        def open(self, *args, **kwargs):
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(output)}}]}).encode())

    monkeypatch.setattr(gateway, "build_opener", lambda *args: Transport())
    settings = Settings(_env_file=None, import_llm_suggestions_enabled=True,
                        openrouter_api_key=SecretStr("SYNTHETIC-ONLY"))
    assert gateway.suggest_sheet(settings, sheets[0], raw[0], "anything", rule,
                                 "usage_history") == (None, "LLM_INVALID_OUTPUT")
