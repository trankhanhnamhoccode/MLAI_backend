"""Independent fixtures for schema coverage and untrusted indexed suggestions."""

import io
import json
from uuid import uuid4
import pytest
from pydantic import SecretStr, ValidationError
from app.config import Settings
from app.application.import_descriptors import descriptors, options, rule_classification
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_suggestions import SheetSuggestion
from app.application.contracts import import_mapping as dto
from app.application.import_analysis import discover, build_spec
from app.infrastructure.import_parser import parse_source
from app.infrastructure import import_suggestions as gateway

HEADERS = (
    "sales.product_id",
    "sales.sales_date",
    "sales.quantity",
    "sales.unit",
    "sales.business_report_key",
)


def source(headers=HEADERS):
    return discover(
        uuid4(),
        parse_source(
            (",".join(headers) + "\nP,2026-10-09,0,cup,REPORT\n").encode(), "csv"
        ),
    )


def output(headers=HEADERS):
    return dict(
        version="sheet_suggestion/1",
        sheet_type="sales",
        confidence=0.99,
        warnings=[],
        columns=[
            dict(source_column_index=i, target_field=h, confidence=0.8)
            for i, h in enumerate(headers)
        ],
    )


def test_descriptor_requiredness_and_roles_are_source_contract_not_db_promise():
    assert {d.schema_id for d in descriptors()} == set(SOURCE_MODELS)
    for descriptor in descriptors():
        fields = {f.key.split(".", 1)[1]: f for f in descriptor.fields if f.available}
        model = SOURCE_MODELS[descriptor.schema_id]
        assert set(fields) == set(model.model_fields) - {"domain"}
        for key, field in fields.items():
            assert (field.requiredness == "required") == model.model_fields[
                key
            ].is_required()
            assert field.label and field.description
    assert (
        next(
            f for f in options("sales") if f.key == "sales.business_report_key"
        ).value_role
        == "source_only"
    )


def test_nullable_required_fields_and_bound_business_tokens_are_explained():
    fields = {f.key: f for f in options() if f.available}
    for key in (
        "products.sku",
        "products.price",
        "recipes.effective_to",
        "supplier_terms.shelf_life_days",
    ):
        assert fields[key].requiredness == "required" and fields[key].nullable
    assert not fields["sales.quantity"].nullable
    assert fields["sales.product_id"].input_sources == ("excel", "binding")
    assert "UUID" in fields["sales.product_id"].input_help
    assert fields["sales.quantity"].input_sources == ("excel",)
    assert "không tự default" in fields["sales.quantity"].input_help


def test_business_headers_resolve_without_excel_uuid_and_receipt_dates_are_not_counts():
    from app.application.import_preview import normalize

    product = uuid4()
    headers = ("Tên món", "Ngày bán", "Số lượng bán", "Đơn vị", "Mã báo cáo nghiệp vụ")
    kind, targets, _, _ = rule_classification(headers, "", selected="sales")
    assert kind == "sales" and targets == HEADERS
    spec = dto.ProfileSpec(
        scope=dto.ProfileScope(source_system_key="POS", report_type="DAILY"),
        schema="sales",
        structure=dto.Structure(
            sheet_roles=("sales",), header_rules=headers, schema_signature="fixture"
        ),
        field_bindings=tuple(
            dto.FieldBinding(
                source_column_index=i,
                source_header=h,
                target_field=t,
                requiredness="required",
                ignored=False,
            )
            for i, (h, t) in enumerate(zip(headers, targets))
        ),
        identity_rules=(
            dto.IdentityRule(
                entity="product", source_token="Trà đào", canonical_id=product
            ),
        ),
        source_provenance=dto.SourceProvenance(
            declared_by=uuid4(), evidence_references=("manual",)
        ),
    )
    value, _ = normalize(
        {
            "cells": [
                dict(column_index=i, raw=v, kind="text")
                for i, v in enumerate(("Trà đào", "2026-10-09", "0", "cup", "R-1"))
            ]
        },
        spec,
    )
    assert value.product_id == product and value.quantity == "0"
    _, mapped, _, _ = rule_classification(
        ("Ngày nhận hàng", "Ngày mua", "Số lượng thực nhận", "Tồn đầu kỳ"),
        "inventory_count",
        selected="inventory_count",
    )
    assert mapped == (None, None, None, None)
    assert set(SOURCE_MODELS) == {
        "sales",
        "inventory_count",
        "recipes",
        "products",
        "ingredients",
        "suppliers",
        "supplier_terms",
        "payable_fees",
        "scope_declarations",
    }
    assert (
        next(f for f in options("recipes") if f.key == "recipes.product_id").value_role
        == "resolve_only"
    )


@pytest.mark.parametrize("name", ["", "Inventory", "payable_fees", "Doanh số"])
def test_name_is_not_sole_classification_evidence(name):
    kind, targets, confidence, needs_model = rule_classification(HEADERS, name)
    assert (
        kind == "sales" and targets == HEADERS and confidence == 1 and not needs_model
    )
    assert rule_classification(("alien header",), "sales")[0] is None


def test_duplicate_headers_do_not_silently_overwrite_targets():
    kind, targets, _, _ = rule_classification((*HEADERS, "sales.quantity"), "sales")
    assert kind == "sales" and targets[2] is None and targets[5] is None


def test_high_confidence_and_missing_required_fields_still_block_profile():
    sheets, issues, _ = source(HEADERS[:3])
    issues = [
        i.model_copy(update={"status": "resolved", "confidence": 1.0}) for i in issues
    ]
    _, missing = build_spec(sheets[0], issues, uuid4())
    assert "sales.unit" in missing and "sales.business_report_key" in missing
    with pytest.raises(ValidationError):
        dto.SheetTypeResolution(
            kind="sheet_type", sheet_type=None, ignored=True, reason="Skip"
        )


def test_payload_is_bounded_indexed_and_does_not_send_unrelated_facts():
    sheets, _, raw = source(("duplicate", "duplicate", "x"))
    raw[0]["catalog"] = "SECRET-CATALOG-SHOULD-NOT-BE-SENT"
    raw[0]["actor"] = "SECRET-SESSION"
    payload = gateway.sheet_payload(sheets[0], raw[0], "display.csv", {}, None)
    # The fixture has two extra populated cells: preserve unlabelled data columns.
    assert [c["source_column_index"] for c in payload["columns"]] == [0, 1, 2, 3, 4]
    assert payload["columns"][0]["header"] == payload["columns"][1]["header"]
    assert len(payload["sample_rows"]) <= 8
    assert "SECRET" not in json.dumps(payload)
    assert "rows" not in payload and "workbook" not in payload


@pytest.mark.parametrize(
    "fault",
    [
        "invented",
        "duplicate_target",
        "duplicate_index",
        "missing_index",
        "extra",
        "wrong_type",
        "nan",
    ],
)
def test_invalid_output_rejected_wholly(fault, monkeypatch):
    sheets, _, raw = source()
    value = output()
    if fault == "invented":
        value["columns"][0]["target_field"] = "sales.invented"
    if fault == "duplicate_target":
        value["columns"][1]["target_field"] = "sales.product_id"
    if fault == "duplicate_index":
        value["columns"][1]["source_column_index"] = 0
    if fault == "missing_index":
        value["columns"].pop()
    if fault == "extra":
        value["approved"] = True
    if fault == "wrong_type":
        value["sheet_type"] = "recipes"
    if fault == "nan":
        value["confidence"] = float("nan")

    class Transport:
        def open(self, request, timeout):
            body = json.loads(request.data)
            assert body["model"] == "qwen/qwen3.5-9b" and body["reasoning"] == {
                "enabled": False
            }
            assert (
                body["temperature"] == 0
                and body["max_tokens"] == 1800
                and timeout <= 30
            )
            assert body["response_format"]["json_schema"]["strict"]
            return io.BytesIO(
                json.dumps(
                    {"choices": [{"message": {"content": json.dumps(value)}}]}
                ).encode()
            )

    monkeypatch.setattr(gateway, "build_opener", lambda *a: Transport())
    settings = Settings(_env_file=None, import_llm_suggestions_enabled=True, openrouter_api_key=SecretStr("SYNTHETIC-ONLY"))
    assert gateway.suggest_sheet(settings, sheets[0], raw[0], "sales.csv", {}) == (
        None,
        "LLM_INVALID_OUTPUT",
    )


def test_valid_output_missing_key_and_timeout_keep_manual_flow(monkeypatch):
    sheets, _, raw = source()
    settings = Settings(_env_file=None, openrouter_api_key=None)
    monkeypatch.setattr(
        gateway,
        "build_opener",
        lambda *a: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    assert gateway.suggest_sheet(settings, sheets[0], raw[0], "x", {}) == (
        None,
        "LLM_UNAVAILABLE",
    )
    calls = []

    class Transport:
        def open(self, request, timeout):
            calls.append(timeout)
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {"content": json.dumps(output())},
                                "finish_reason": "stop",
                            }
                        ]
                    }
                ).encode()
            )

    monkeypatch.setattr(gateway, "build_opener", lambda *a: Transport())
    settings = Settings(_env_file=None, import_llm_suggestions_enabled=True, openrouter_api_key=SecretStr("SYNTHETIC-ONLY"))
    value, error = gateway.suggest_sheet(settings, sheets[0], raw[0], "x", {}, "sales")
    assert value == SheetSuggestion.model_validate(output()) and error is None

    class Timeout:
        def open(self, *a, **kw):
            calls.append("timeout")
            raise TimeoutError()

    monkeypatch.setattr(gateway, "build_opener", lambda *a: Timeout())
    assert gateway.suggest_sheet(settings, sheets[0], raw[0], "x", {}) == (
        None,
        "LLM_UNAVAILABLE",
    )
    assert calls.count("timeout") == 2


@pytest.mark.parametrize("value", [False, 0, 1, "true", None])
def test_review_confirmation_requires_explicit_boolean_true(value):
    with pytest.raises(ValidationError):
        dto.ConfirmReviewRequest(
            phase="confirm_review",
            preview_id=uuid4(),
            preview_digest="sha256:" + "0" * 64,
            mapping_revision="synthetic-revision",
            confirm=value,
            reason="Explicit review",
        )
