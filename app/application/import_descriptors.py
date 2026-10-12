"""Single descriptor projection of supported typed source models. No new schema."""

import unicodedata
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_field_values import allowed_scopes

SCHEMAS = {
    "sales": ("Doanh số", "Observed sales theo Product/ngày; missing khác zero."),
    "inventory_count": ("Kiểm kê lô", "Count cho lô đã có; không receipt hoặc tạo lô."),
    "recipes": ("Công thức", "Dated version; quantity mỗi Ingredient cho toàn yield."),
    "products": ("Món bán", "Định nghĩa Product, không doanh số."),
    "ingredients": ("Nguyên liệu", "Định nghĩa Ingredient và exact base unit."),
    "suppliers": ("Nhà cung cấp", "Định nghĩa Supplier, không điều khoản mua."),
    "supplier_terms": (
        "Điều khoản mua",
        "Pack price/lead time/MOQ và inclusive effectivity.",
    ),
    "payable_fees": ("Phí phải trả", "Fixed phí WHEN_ORDERED; không tax/tier formula."),
    "scope_declarations": (
        "Khai báo phạm vi",
        "Explicit tagged completeness/constraints; không suy dữ liệu thiếu.",
    ),
}

LABELS = {
    "product_id": "Món bán (tên/mã đã nối)",
    "ingredient_id": "Nguyên liệu (tên/mã đã nối)",
    "supplier_id": "Nhà cung cấp (tên/mã đã nối)",
    "lot_id": "Lô hiện có (mã đã định danh)",
    "sales_date": "Ngày bán",
    "quantity": "Số lượng",
    "unit": "Đơn vị",
    "business_report_key": "Mã báo cáo nghiệp vụ",
    "on_hand": "Tồn kiểm kê",
    "observed_at": "Thời điểm kiểm kê",
    "reason": "Lý do",
    "version": "Phiên bản",
    "effective_from": "Ngày bắt đầu hiệu lực",
    "effective_to": "Ngày kết thúc hiệu lực",
    "yield_quantity": "Sản lượng toàn mẻ",
    "yield_unit": "Đơn vị sản lượng",
    "process_loss_rate": "Tỷ lệ hao hụt",
    "name": "Tên",
    "selling_unit": "Đơn vị bán",
    "base_unit": "Đơn vị cơ sở",
    "sku": "SKU",
    "price": "Giá bán",
    "active": "Đang hoạt động",
    "expiry_tracking": "Theo dõi hạn dùng",
    "source_business_key": "Mã thực thể ở nguồn",
    "source_supplier_key": "Mã nhà cung cấp ở nguồn",
    "source_term_key": "Mã điều khoản ở nguồn",
    "pack_size_base_quantity": "Số lượng cơ sở mỗi pack",
    "pack_cost": "Giá mỗi pack",
    "currency": "Tiền tệ",
    "minimum_order_packs": "Số pack tối thiểu",
    "lead_time_days": "Số ngày giao",
    "shelf_life_days": "Số ngày hạn dùng",
    "maximum_order_base_quantity": "Lượng mua tối đa",
    "source_fee_key": "Mã khai báo phí",
    "scope": "Phạm vi",
    "mode": "Cơ chế phí",
    "coverage": "Mức khai báo đầy đủ",
    "components": "Các thành phần phí",
    "covered_source_term_keys": "Điều khoản trong phạm vi",
    "covered_source_supplier_keys": "Nhà cung cấp trong phạm vi",
    "evidence_reference": "Bằng chứng khai báo",
    "source_declaration_key": "Mã khai báo",
    "declaration": "Nội dung khai báo",
}
ALIASES = {
    "sales.quantity": ("Số lượng bán", "SL", "quantity sold"),
    "sales.sales_date": ("Ngày bán", "Ngày", "sales date"),
    "inventory_count.on_hand": ("Số tồn kiểm kê", "on hand"),
    "inventory_count.observed_at": ("Thời điểm kiểm kê", "count timestamp"),
    "recipes.quantity": ("Định lượng nguyên liệu",),
    "recipes.yield_quantity": ("Sản lượng toàn mẻ",),
    "sales.product_id": ("Tên món", "Mã món", "Món", "product name", "product code"),
    "recipes.product_id": ("Tên món", "Mã món", "product name", "product code"),
    "inventory_count.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu"),
    "recipes.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu"),
    "supplier_terms.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu"),
    "supplier_terms.supplier_id": ("Tên nhà cung cấp", "Mã nhà cung cấp"),
    "inventory_count.lot_id": ("Mã lô đã định danh",),
}
UNSUPPORTED = (
    "payable_fees.tax_percent",
    "payable_fees.free_over_threshold",
    "payable_fees.tiers",
    "supplier_terms.payment_terms",
)


def normalized_hint(value):
    # Only proposal matching. Never normalize canonical labels/identities/units.
    return " ".join(
        unicodedata.normalize("NFKC", value).casefold().replace("_", " ").split()
    )


def options(schema=None):
    result = []
    for name, model in SOURCE_MODELS.items():
        if schema is not None and schema != name:
            continue
        for key, field in model.model_fields.items():
            if key == "domain":
                continue
            full = name + "." + key
            unit = key in {"unit", "yield_unit", "base_unit", "selling_unit"}
            role = (
                "resolve_only"
                if key.endswith("_id")
                else (
                    "source_only"
                    if key.startswith("source_")
                    or key in {"business_report_key", "reason", "evidence_reference"}
                    else "canonical_candidate"
                )
            )
            conditional = ()
            if full == "payable_fees.components":
                conditional = (
                    "NONE requires empty components and COMPLETE; other components must match mode and exact scoped refs.",
                )
            elif full == "scope_declarations.declaration":
                conditional = (
                    "Required fields depend on kind INVENTORY/SALES_COVERAGE/PROCUREMENT_CONTEXT; nested source validation remains authoritative.",
                )
            elif key == "effective_to":
                conditional = (
                    "Giá trị row bắt buộc, nhận null rõ ràng; không buộc cột Excel. Ngày kết thúc khác null phải >= effective_from, inclusive.",
                )
            elif full == "supplier_terms.shelf_life_days":
                conditional = (
                    "Null là chưa biết hạn dùng; preview cảnh báo REQUIRED_ARRIVAL_EXPIRY_UNKNOWN khi Ingredient theo dõi expiry thiếu shelf life hoặc approved arrival-expiry rule. Không tự điền hạn dùng.",
                )
            elif full == "inventory_count.lot_id":
                conditional = (
                    "Phải resolve duy nhất lô hiện có trong Store; không tạo lô, opening stock hoặc receipt từ kiểm kê.",
                )
            description = (
                "Exact label; no inferred conversion."
                if unit
                else (
                    "Tên/mã nguồn hoặc UUID được resolve bằng binding đã duyệt trong Store; không fuzzy-match hoặc tự tạo thực thể."
                    if key.endswith("_id")
                    else (
                        "Explicit source reference, not automatically a canonical DB column."
                        if role == "source_only"
                        else "Typed source value validated before preview; mapping does not promise a DB write."
                    )
                )
            )
            if full == "inventory_count.observed_at":
                description = "Thời điểm thực sự kiểm kê có timezone; không ngày nhận hàng, ngày mua hoặc ngày upload."
            elif full == "inventory_count.on_hand":
                description = "Số còn thực tế của lô hiện có, không lượng nhận/mua; zero hợp lệ, không tạo lô mới."
            elif full == "sales.sales_date":
                description = "Ngày bán đã quan sát; không ngày nhập file hoặc ngày mua nguyên liệu."
            prop = model.model_json_schema()["properties"][key]
            bounds = tuple(f"{name}={p[name]}" for p in prop.get("anyOf", (prop,))
                           for name in ("minLength", "maxLength", "pattern") if name in p)
            conditional += bounds
            nullable = any(p.get("type") == "null" for p in prop.get("anyOf", ()))
            result.append(
                dto.FieldOption(
                    key=full,
                    type=str(field.annotation),
                    requiredness="required" if field.is_required() else "optional",
                    unit_semantics="exact" if unit else None,
                    support="source_only" if role == "source_only" else "supported",
                    available=True,
                    label=LABELS[key],
                    description=description,
                    aliases=(key, LABELS[key], *ALIASES.get(full, ())),
                    conditional_requirements=conditional,
                    nullable=nullable,
                    input_sources=(
                        ("excel", "binding")
                        if key.endswith("_id")
                        else (
                            ("excel", "shared_value")
                            if allowed_scopes(full)
                            else ("excel",)
                        )
                    ),
                    allowed_shared_scopes=allowed_scopes(full),
                    input_help=(
                        "Cột có thể chứa tên/mã nguồn đã nối với IdentityRule hoặc reservation được duyệt; không bắt Excel chứa UUID. Mã lô phải xác định duy nhất, lot_code không tự là identity."
                        if key.endswith("_id")
                        else (
                            "Chọn rõ cột hoặc giá trị chung thuộc allowed_shared_scopes; không fallback ô trống, đoán defaults. IMPORT_VALUE không reuse giá trị; PROFILE_CONSTANT cần Owner duyệt. Null chỉ khi nullable."
                            if allowed_scopes(full)
                            else "Chỉ lấy từ cột đã map trong lát này; không shared/nested injection. Required là giá trị row, không tự default."
                        )
                    ),
                    value_role=role,
                )
            )
    for key in UNSUPPORTED:
        if schema is None or key.split(".")[0] == schema:
            result.append(
                dto.FieldOption(
                    key=key,
                    type="unsupported_business_rule",
                    requiredness="optional",
                    support="unsupported",
                    available=False,
                    reason_code="UNSUPPORTED_BUSINESS_RULE",
                    label="Quy tắc chưa hỗ trợ",
                    description="Không có source schema/writer hiện hành.",
                    value_role="unsupported",
                )
            )
    return tuple(result)


def descriptors():
    return tuple(
        dto.SchemaDescriptor(
            schema_id=name,
            label=SCHEMAS[name][0],
            description=SCHEMAS[name][1],
            fields=options(name),
        )
        for name in SOURCE_MODELS
    )


def rule_classification(headers, sheet_name, selected=None):
    ranked = []
    for name in SOURCE_MODELS:
        if selected is not None and name != selected:
            continue
        fields = [o for o in options(name) if o.available]
        proposals = []
        for header in headers:
            exact = [o.key for o in fields if header == o.key]
            aliases = [
                o.key
                for o in fields
                if normalized_hint(header) in {normalized_hint(a) for a in o.aliases}
            ]
            candidates = exact or aliases
            proposals.append(candidates[0] if len(candidates) == 1 else None)
        # Duplicate headers/aliases cannot silently overwrite the same target.
        duplicates = {p for p in proposals if p and proposals.count(p) > 1}
        proposals = tuple(None if p in duplicates else p for p in proposals)
        present = {p for p in proposals if p}
        required = {o.key for o in fields if o.requiredness == "required"}
        coverage = len(present & required) / max(1, len(required))
        hint = normalized_hint(sheet_name) in {
            normalized_hint(name),
            normalized_hint(SCHEMAS[name][0]),
        }
        ranked.append((len(present), coverage, bool(hint), name, proposals))
    ranked.sort(reverse=True)
    best = ranked[0]
    ambiguous = len(ranked) > 1 and best[:2] == ranked[1][:2]
    if best[0] == 0 or ambiguous:
        return None, tuple(None for _ in headers), None, True
    return best[3], best[4], best[1], best[1] < 1 or any(p is None for p in best[4])
