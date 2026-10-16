"""Versioned, source-independent lexical proposals. Never profiles or business facts."""

from dataclasses import dataclass
import re
from typing import Literal, Mapping, Sequence
import unicodedata


def normalized_hint(value: str) -> str:
    """Proposal-only normalization; never normalize source values or identities."""
    text = unicodedata.normalize("NFKD", value).casefold().replace("đ", "d")
    return " ".join("".join(
        c if c.isalnum() else " " for c in text if not unicodedata.combining(c)
    ).split())


@dataclass(frozen=True)
class FieldRule:
    rule_id: str
    target: str
    aliases: tuple[str, ...]
    reason: str
    reviews: tuple[str, ...]
    mode: Literal["proposal", "candidate"] = "proposal"


@dataclass(frozen=True)
class CuratedTemplate:
    template_id: str
    version: int
    schema: str
    # Each group requires at least one lexical header; all groups must match.
    header_groups: tuple[tuple[str, ...], ...]
    negative_headers: tuple[str, ...]
    rules: tuple[FieldRule, ...]


@dataclass(frozen=True)
class ColumnHint:
    target: str | None
    candidates: tuple[str, ...]
    reason: str
    requires_review: bool = False
    ambiguous: bool = False


@dataclass(frozen=True)
class TemplateMatch:
    template: CuratedTemplate
    conflicting: bool


TEMPLATES = (
    CuratedTemplate("tabular.sales", 1, "sales",
        (("Ngày bán", "Ngày GD", "sales.sales_date"),
         ("Tên món", "Tên món / SKU", "Mã món", "sales.product_id")),
        ("Ngày sử dụng", "Ngày kiểm kê", "Ngày thực nhận", "Ngày đặt mua"), (
            FieldRule("quantity", "sales.quantity", ("SL",), "CONTEXTUAL_SOLD_QUANTITY",
                      ("sold_quantity_meaning",)),
            FieldRule("slx", "sales.quantity", ("SLX",), "ABBREVIATION_MEANING_REVIEW",
                      ("sold_vs_exported_quantity",), "candidate"),
        )),
    CuratedTemplate("tabular.usage", 1, "usage_history",
        (("Ngày sử dụng", "usage_history.usage_date"),
         ("Tên NL", "Nguyên liệu sử dụng", "usage_history.ingredient_id")),
        ("Ngày bán", "Ngày GD", "Ngày kiểm kê", "Ngày thực nhận", "Ngày đặt mua"), (
            FieldRule("ingredient", "usage_history.ingredient_id", ("Tên NL",),
                      "SOURCE_INGREDIENT_TOKEN", ("store_identity_binding",)),
            FieldRule("quantity", "usage_history.quantity", ("SL",),
                      "CONTEXTUAL_ACTUAL_USAGE", ("actual_consumption_not_bom_or_loss",)),
            FieldRule("unit", "usage_history.unit", ("ĐVT", "ĐV"),
                      "SOURCE_UNIT_LABEL", ("exact_unit_no_conversion",)),
        )),
    CuratedTemplate("tabular.count", 1, "inventory_count",
        (("Ngày kiểm kê", "Thời điểm kiểm kê", "inventory_count.observed_at"),
         ("Mặt hàng tồn", "Tên NL", "Tên nguyên liệu", "inventory_count.ingredient_id")),
        ("Ngày bán", "Ngày GD", "Ngày sử dụng", "Ngày thực nhận", "Ngày đặt mua"), (
            FieldRule("ingredient", "inventory_count.ingredient_id", ("Tên NL",),
                      "SOURCE_INGREDIENT_TOKEN", ("existing_store_identity",)),
            FieldRule("quantity", "inventory_count.on_hand", ("SL",),
                      "CONTEXTUAL_COUNT_BALANCE", ("balance_not_receipt", "existing_lot_identity")),
        )),
    CuratedTemplate("tabular.actual-receipt", 1, "inventory_receipts",
        (("Ngày thực nhận", "Thời điểm thực nhận", "inventory_receipts.observed_at"),
         ("Mã nhận hàng", "inventory_receipts.source_record_id"),
         ("Tên NL", "Tên nguyên liệu", "inventory_receipts.ingredient_id")),
        ("Ngày bán", "Ngày GD", "Ngày sử dụng", "Ngày kiểm kê", "Ngày đặt mua", "NCT", "Số PO"), (
            FieldRule("record", "inventory_receipts.source_record_id", ("Mã nhận hàng",),
                      "SOURCE_RECEIPT_RECORD", ("stable_source_record_identity",)),
            FieldRule("ingredient", "inventory_receipts.ingredient_id", ("Tên NL", "Tên nguyên liệu"),
                      "SOURCE_INGREDIENT_TOKEN", ("store_identity_binding",)),
            FieldRule("quantity", "inventory_receipts.quantity", ("SL",),
                      "CONTEXTUAL_ACTUAL_RECEIPT", ("actually_received_not_ordered_or_counted",)),
            FieldRule("date", "inventory_receipts.received_date", ("Ngày thực nhận",),
                      "RECEIPT_DATE_REVIEW", ("date_convention_not_observation_timestamp",)),
            FieldRule("observation", "inventory_receipts.observed_at", ("Thời điểm thực nhận",),
                      "RECEIPT_OBSERVATION_REVIEW", ("aware_actual_observation",)),
            FieldRule("unit", "inventory_receipts.unit", ("ĐVT", "ĐV"),
                      "SOURCE_UNIT_LABEL", ("exact_unit_no_conversion",)),
        )),
    CuratedTemplate("tabular.recipe", 1, "recipes",
        (("Món bán", "recipes.product_id"), ("Thành phần", "recipes.ingredient_id")),
        ("Ngày bán", "Ngày GD", "Ngày sử dụng", "Ngày kiểm kê", "Ngày thực nhận"), (
            FieldRule("per-serving", "recipes.quantity", ("Lượng / 1 SP",),
                      "PER_SERVING_VS_WHOLE_YIELD_REVIEW", ("quantity_basis", "yield_and_loss"), "candidate"),
            FieldRule("version", "recipes.version", ("Ver",),
                      "INTEGER_VERSION_REQUIRED", ("integer_recipe_version",), "candidate"),
        )),
    CuratedTemplate("tabular.supplier-pack", 1, "supplier_terms",
        (("Vendor", "supplier_terms.supplier_id"), ("Material", "supplier_terms.ingredient_id"),
         ("Pack Size", "supplier_terms.pack_size_base_quantity")),
        ("Ngày bán", "Ngày GD", "Ngày sử dụng", "Ngày kiểm kê", "Ngày thực nhận"), (
            FieldRule("order-uom", "supplier_terms.pack_label", ("Order UOM",),
                      "PACK_LABEL_NOT_PHYSICAL_UNIT", ("pack_label_vs_physical_unit",), "candidate"),
            FieldRule("moq", "supplier_terms.minimum_order_quantity", ("MOQ",),
                      "MOQ_PACK_VS_BASE_UNIT_REVIEW", ("moq_basis_and_unit",), "candidate"),
            FieldRule("price", "supplier_terms.pack_cost", ("Giá mua",),
                      "PER_PACK_VS_UNIT_PRICE_REVIEW", ("price_basis_and_denominator",), "candidate"),
        )),
)


def validate_templates(templates: Sequence[CuratedTemplate],
                       supported: Mapping[str, frozenset[str]]) -> None:
    seen = set()
    for template in templates:
        key = (template.template_id, template.version)
        if (key in seen or type(template.version) is not int or template.version < 1
                or not template.template_id or not template.header_groups
                or any(not group or not all(normalized_hint(h) for h in group)
                       for group in template.header_groups)):
            raise ValueError("Invalid template identity/context")
        seen.add(key)
        rule_ids = set()
        for rule in template.rules:
            if rule.target not in supported.get(template.schema, ()):
                raise ValueError("Template must reference a supported target in its schema")
            if (rule.rule_id in rule_ids or not rule.rule_id or not rule.aliases or not rule.reason
                    or not rule.reviews or rule.mode not in {"proposal", "candidate"}):
                raise ValueError("Invalid template rule/review semantics")
            rule_ids.add(rule.rule_id)


def matching_templates(headers: tuple[str, ...]) -> tuple[TemplateMatch, ...]:
    present = {normalized_hint(h) for h in headers}
    return tuple(TemplateMatch(t, bool(present & {normalized_hint(h) for h in t.negative_headers}))
                 for t in TEMPLATES
                 if all(present & {normalized_hint(h) for h in group} for group in t.header_groups))


def contextual_column(header: str, matches: Sequence[TemplateMatch]) -> ColumnHint | None:
    found = [(m, r) for m in matches for r in m.template.rules
             if normalized_hint(header) in {normalized_hint(a) for a in r.aliases}]
    if not found:
        return None
    candidates = tuple(sorted({r.target for _, r in found}))
    ambiguous = len(candidates) != 1 or any(m.conflicting for m, _ in found)
    target = candidates[0] if not ambiguous and all(r.mode == "proposal" for _, r in found) else None
    provenance = "|".join(f"CURATED:{m.template.template_id}/{m.template.version}:{r.rule_id};"
                          f"{r.reason};REVIEW:{','.join(r.reviews)}" for m, r in found)
    if ambiguous:
        provenance += ";CONFLICTING_WORKFLOW_EVIDENCE"
    return ColumnHint(target, candidates, provenance, requires_review=True, ambiguous=ambiguous)


def nsx_hint(header: str, headers: tuple[str, ...], samples: tuple[str | None, ...]) -> ColumnHint | None:
    """Bounded lexical diagnostics only: neither manufacture meaning has a writer.

    Numeric Excel cells do not prove dates; no conversion or business value is returned.
    """
    if normalized_hint(header) != "nsx":
        return None
    values = tuple(v[:200].strip() for v in samples[:8] if v and v.strip())
    date_pattern = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"
    has_expiry = any(normalized_hint(h) in {"hsd", "han dung", "ngay het han"} for h in headers)
    if values and has_expiry and all(re.fullmatch(date_pattern, v) for v in values):
        reason = "MANUFACTURE_DATE_NOT_SUPPORTED"
    elif values and all(any(c.isalpha() for c in v)
                        and all(c.isalpha() or c.isspace() or c in ".-&" for c in v) for v in values):
        reason = "MANUFACTURER_NOT_SUPPORTED"
    else:
        reason = "NSX_MEANING_AMBIGUOUS"
    return ColumnHint(None, (), f"CURATED:lexical.nsx/1:meaning;{reason};REVIEW:source_semantics",
                      requires_review=True, ambiguous=True)
