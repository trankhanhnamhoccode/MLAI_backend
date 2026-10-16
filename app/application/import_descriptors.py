"""Single descriptor projection of supported typed source models. No new schema."""

from dataclasses import dataclass, replace
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_field_values import allowed_scopes
from app.application import import_templates as curated
from app.application.import_templates import (
    ColumnHint, normalized_hint, validate_templates, matching_templates,
    contextual_column, nsx_hint,
)

SCHEMAS = {
    "inventory_receipts": ("Hàng thực nhận", "ACTUAL_RECEIPT: creates a received lot and RECEIPT movement; not opening/count/history or Planning purchases."),
    "calendar_events": ("Sự kiện lịch", "Declared Store event; history-only, no forecast features."),
    "promotion_observations": ("Khuyến mãi quan sát", "Observed Product/day evidence; no inferred discount or uplift."),
    "usage_history": ("Lịch sử sử dụng", "Recorded consumption; no inventory movement or BOM adjustment."),
    "purchase_history": ("Lịch sử mua", "Record-only; no receipt, inbound or current SupplierTerm."),
    "sales": ("Doanh số", "Observed sales theo Product/ngày; missing khác zero."),
    "inventory_count": ("Kiểm kê lô", "Count cho lô đã có; không receipt hoặc tạo lô."),
    "opening_stock": ("Tồn đầu kỳ", "OPENING_STOCK của lô vật lý; không kiểm kê lô existing hoặc hàng thực nhận."),
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
    'source_record_key': 'Mã record lịch sử ở nguồn',
    'event_name': 'Tên sự kiện lịch',
    'declared_at': 'Thời điểm khai báo sự kiện',
    'is_closed': 'Đóng cửa (true/false/unknown)',
    'is_holiday': 'Ngày lễ (true/false/unknown)',
    'promotion_name': 'Tên chương trình khuyến mãi quan sát',
    'promotion_applied': 'Có khuyến mãi (true/false/unknown)',
    'usage_date': 'Ngày thực sử dụng',
    'order_date': 'Ngày đặt mua (có thể chưa biết)',
    'report_date': 'Ngày báo cáo lịch sử mua',
    'is_stockout': 'Observed product stockout (true/false/unknown)',
    "source_record_id": "Mã nguồn của lô tồn đầu kỳ",
    "lot_code": "Nhãn lô vật lý",
    "received_date": "Ngày thực nhận (có thể chưa biết)",
    "expiry_date": "Ngày hết hạn",
    "unit_cost": "Giá một đơn vị vật lý (có thể chưa biết)",
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
    "quantity_basis": "Cơ sở định lượng nguyên liệu",
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
    "pack_size_base_quantity": "Lượng nguyên liệu trong một pack (đơn vị nguồn)",
    "pack_cost": "Giá nguồn theo cơ sở giá",
    "currency": "Tiền tệ",
    "minimum_order_packs": "Số pack tối thiểu",
    "minimum_order_quantity": "MOQ nguồn theo basis đã khai báo",
    "price_basis": "Cơ sở giá nguồn",
    "price_quantity": "Lượng mẫu số của giá",
    "price_unit": "Đơn vị mẫu số của giá",
    "moq_basis": "Cơ sở MOQ nguồn",
    "moq_unit": "Đơn vị lượng MOQ",
    "pack_label": "Nhãn pack (không đơn vị vật lý)",
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
    'usage_history.usage_date': ('Ngày sử dụng',),
    'usage_history.quantity': ('Lượng thực dùng',),
    'usage_history.ingredient_id': ('Nguyên liệu sử dụng',),
    'purchase_history.order_date': ('Ngày đặt mua',),
    'purchase_history.received_date': ('Ngày thực nhận',),
    'purchase_history.report_date': ('Ngày báo cáo mua',),
    'promotion_observations.promotion_name': ('Tên CTKM quan sát',),
    'sales.is_stockout': ('stockout', 'out of stock', 'Hết món?'),
    "sales.quantity": ("Số lượng bán", "SL", "quantity sold"),
    "sales.sales_date": ("Ngày bán", "Ngày", "sales date", "Ngày GD"),
    "sales.unit": ("ĐVT", "ĐV"),
    "inventory_count.unit": ("ĐVT", "ĐV"),
    "inventory_count.on_hand": ("Số tồn kiểm kê", "on hand", "SL cuối ngày"),
    "inventory_count.observed_at": ("Thời điểm kiểm kê", "count timestamp"),
    "recipes.quantity": ("Định lượng nguyên liệu",),
    "sales.product_id": ("Tên món", "Mã món", "Món", "product name", "product code", "Tên món / SKU"),
    "recipes.product_id": ("Tên món", "Mã món", "product name", "product code", "Món bán"),
    "inventory_count.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu", "Mặt hàng tồn"),
    "recipes.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu", "Thành phần"),
    "recipes.unit": ("Đơn vị NL",),
    "recipes.yield_quantity": ("Sản lượng toàn mẻ", "Yield"),
    "recipes.yield_unit": ("Đơn vị SP",),
    "recipes.effective_from": ("Áp dụng từ",),
    "supplier_terms.ingredient_id": ("Tên nguyên liệu", "Mã nguyên liệu", "Material"),
    "supplier_terms.supplier_id": ("Tên nhà cung cấp", "Mã nhà cung cấp", "Vendor"),
    "supplier_terms.pack_size_base_quantity": ("Pack Size", "Số lượng cơ sở mỗi pack"),
    "supplier_terms.pack_cost": ("Giá mỗi pack",),
    "supplier_terms.unit": ("Base UOM",),
    "supplier_terms.lead_time_days": ("Lead time (days)",),
    "inventory_count.lot_id": ("Mã lô đã định danh", "Mã lô"),
    "products.source_business_key": ("Mã món",),
    "products.name": ("Tên món / Combo",),
    "products.selling_unit": ("ĐVT",),
}
FIELD_LABELS = {
    'inventory_receipts.source_record_id': 'Mã dòng nhận hàng ở nguồn',
    'inventory_receipts.observed_at': 'Thời điểm thực nhận có múi giờ',
    'usage_history.observed_at': 'Thời điểm thực sử dụng (có thể chưa biết)',
    'purchase_history.price': 'Giá mua lịch sử theo cơ sở giá',
}
UNSUPPORTED = (
    'business_constraints.minimum_safety_stock',
    'business_constraints.product_priority',
    'business_constraints.open_purchase_orders',
    'calendar_events.weather',
    'calendar_events.demand_uplift',
    'promotion_observations.discount_rate',
    "payable_fees.tax_percent",
    "payable_fees.free_over_threshold",
    "payable_fees.tiers",
    "supplier_terms.payment_terms",
)


def unsupported_sheet_reason(headers):
    """Known unsupported workflows, identified by headers rather than filename."""
    present = {normalized_hint(h) for h in headers}
    for code, markers in (
        ("PURCHASE_HISTORY_DATE_AND_BASIS_REVIEW_REQUIRED", ("NCT", "SLN", "Giá nhập")),
        ("CALENDAR_DECLARATION_REQUIRED", ("Date", "Weekend", "Holiday")),
        ("TABULAR_BUSINESS_RULES_UNSUPPORTED", ("Loại điều kiện", "Áp dụng cho NL")),
    ):
        if {normalized_hint(h) for h in markers} <= present:
            return code
    return None


def column_candidates(header, schema):
    fields = [o for o in options(schema) if o.available]
    exact = tuple(o.key for o in fields if header == o.key)
    return exact or tuple(o.key for o in fields
                         if normalized_hint(header) in {normalized_hint(a) for a in o.aliases})


def semantic_review_candidate(header, schema):
    """Possible targets are review hints, never bindings or inferred values."""
    candidates = {
        ("sales", "SLX"): ("sales.quantity", "ABBREVIATION_MEANING_REVIEW"),
        ("inventory_count", "Ngày kiểm kê"): ("inventory_count.observed_at", "COUNT_TIME_AND_TIMEZONE_REQUIRED"),
        ("recipes", "Lượng / 1 SP"): ("recipes.quantity", "PER_SERVING_VS_WHOLE_YIELD_REVIEW"),
        ("recipes", "Ver"): ("recipes.version", "INTEGER_VERSION_REQUIRED"),
        ("supplier_terms", "MOQ"): ("supplier_terms.minimum_order_quantity", "MOQ_PACK_VS_BASE_UNIT_REVIEW"),
        ("supplier_terms", "Giá mua"): ("supplier_terms.pack_cost", "PER_PACK_VS_UNIT_PRICE_REVIEW"),
    }
    return next((value for (kind, name), value in candidates.items()
                 if kind == schema and normalized_hint(name) == normalized_hint(header)), None)


def options(schema=None):
    result = []
    for name, model in SOURCE_MODELS.items():
        if schema is not None and schema != name:
            continue
        for key, field in model.model_fields.items():
            if key == "domain":
                continue
            full = name + "." + key
            unit = key in {"unit", "yield_unit", "base_unit", "selling_unit", "price_unit", "moq_unit"}
            role = (
                "resolve_only"
                if key.endswith("_id") and key != "source_record_id"
                else (
                    "source_only"
                    if key.startswith("source_") or name == "supplier_terms" and key in {
                        "price_basis", "price_quantity", "price_unit", "moq_basis",
                        "moq_unit", "minimum_order_quantity", "pack_label"}
                    or key in {"business_report_key", "reason", "evidence_reference", "quantity_basis"}
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
                    if key.endswith("_id") and key != "source_record_id"
                    else (
                        "Explicit source reference, not automatically a canonical DB column."
                        if role == "source_only"
                        else "Typed source value validated before preview; mapping does not promise a DB write."
                    )
                )
            )
            if full == "inventory_count.observed_at":
                description = "Thời điểm thực sự kiểm kê có timezone; không ngày nhận hàng, ngày mua hoặc ngày upload."
            elif full == "inventory_receipts.observed_at":
                description = "Actual receipt observation with timezone; never upload/filename/received-date inference."
            elif full == "inventory_receipts.quantity":
                description = "Positive quantity actually received now or recorded late; not a target balance or planned purchase."
            elif full == "inventory_receipts.source_record_id":
                description = "Stable receipt identity within the proven source namespace shared with N6; not filename/row number/lot label."
            elif full == "opening_stock.observed_at":
                description = "Thời điểm quan sát tồn đầu kỳ có timezone, khác ngày nhận; không tự dùng ngày upload."
            elif full == "opening_stock.quantity":
                description = "Số còn thực tế >0 của lô vật lý riêng; zero toàn nguyên liệu dùng completeness declaration, không tạo lô zero."
            elif full == "inventory_count.on_hand":
                description = "Số còn thực tế của lô hiện có, không lượng nhận/mua; zero hợp lệ, không tạo lô mới."
            elif full == "sales.sales_date":
                description = "Ngày bán đã quan sát; không ngày nhập file hoặc ngày mua nguyên liệu."
            elif full == 'sales.is_stockout':
                description = 'Observed product/day stockout. True: positive evidence; false: known uncensored; null: unknown. No sales-zero inference. Value aliases require explicit review.'
            elif full == "recipes.quantity_basis":
                description = "Explicit PER_SERVING (mỗi đơn vị bán) hoặc WHOLE_BATCH (toàn yield); Owner review, không suy từ header."
            elif full == "recipes.quantity":
                description = "Định lượng nguồn theo quantity_basis; preview chuyển PER_SERVING × yield sang lượng toàn mẻ, chưa áp loss."
            elif full == "supplier_terms.pack_cost":
                description = "Giá nguồn theo price_basis; canonical after luôn là giá trọn pack, không gồm payable fees."
            elif full == "supplier_terms.price_basis":
                description = "PER_PACK hoặc PER_QUANTITY. PER_QUANTITY bắt buộc price_quantity >0 và price_unit; PER_PACK cần hai giá trị null rõ ràng."
            elif full == "supplier_terms.minimum_order_quantity":
                description = "MOQ nguồn >0: PACKS phải nguyên; PHYSICAL_QUANTITY cần moq_unit và exact ceil thành minimum_order_packs. Zero basket vẫn hợp lệ."
            elif full == "supplier_terms.unit":
                description = "Đơn vị vật lý của lượng trong một pack; không phải nhãn thùng/bao. Quy đổi có evidence tới Ingredient.base_unit."
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
                    label=FIELD_LABELS.get(full, LABELS[key]),
                    description=description,
                    aliases=(key, FIELD_LABELS.get(full, LABELS[key]), *ALIASES.get(full, ())),
                    conditional_requirements=conditional,
                    nullable=nullable,
                    input_sources=(
                        ("excel", "binding")
                        if key.endswith("_id") and key != "source_record_id"
                        else (
                            ("excel", "shared_value")
                            if allowed_scopes(full)
                            else ("excel",)
                        )
                    ),
                    allowed_shared_scopes=allowed_scopes(full),
                    input_help=(
                        "Cột có thể chứa tên/mã nguồn đã nối với IdentityRule hoặc reservation được duyệt; không bắt Excel chứa UUID. Mã lô phải xác định duy nhất, lot_code không tự là identity."
                        if key.endswith("_id") and key != "source_record_id"
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


@dataclass(frozen=True)
class SheetRules:
    schema: str | None
    columns: tuple[ColumnHint, ...]
    confidence: float | None
    low_quality: bool
    provenance: tuple[str, ...] = ()


def sheet_rules(headers: tuple[str, ...], sheet_name: str, selected: str | None = None,
                samples: tuple[tuple[str | None, ...], ...] = ()) -> SheetRules:
    """One proposal policy for discovery and explicit manual classification."""
    validate_templates(curated.TEMPLATES, {
        name: frozenset(name + "." + key for key in model.model_fields if key != "domain")
        for name, model in SOURCE_MODELS.items()
    })
    unsupported = unsupported_sheet_reason(headers)
    if selected is None and unsupported:
        return SheetRules(None, tuple(ColumnHint(None, (), unsupported) for _ in headers), None, False)
    matches = matching_templates(headers)
    canonical_schemas = {name for name, model in SOURCE_MODELS.items()
                         if any(h == name + "." + key for h in headers for key in model.model_fields)}
    mixed = len({m.template.schema for m in matches}) > 1
    if selected is None and mixed and not canonical_schemas:
        columns = []
        for i, h in enumerate(headers):
            hint = (nsx_hint(h, headers, samples[i] if i < len(samples) else ())
                    or contextual_column(h, matches))
            columns.append(replace(hint, target=None, ambiguous=True,
                                   reason=hint.reason + ";MIXED_WORKFLOW_REVIEW") if hint
                           else ColumnHint(None, (), "AMBIGUOUS_WORKFLOW"))
        return SheetRules(None, tuple(columns), None, True,
            tuple(f"CURATED:{m.template.template_id}/{m.template.version}" for m in matches))
    ranked = []
    for name in SOURCE_MODELS:
        if selected is not None and name != selected:
            continue
        fields = [o for o in options(name) if o.available]
        own_matches = tuple(m for m in matches if m.template.schema == name)
        columns = []
        for header in headers:
            candidates = column_candidates(header, name)
            target = candidates[0] if len(candidates) == 1 else None
            reason = ("EXACT_CANONICAL_HEADER" if target == header else "CONTROLLED_HEADER_ALIAS")
            hint = ColumnHint(target, candidates, reason if target else (
                "DUPLICATE_OR_AMBIGUOUS_TARGET" if candidates else "NO_SUPPORTED_TARGET"))
            contextual = contextual_column(header, own_matches)
            if contextual and header not in {o.key for o in fields}:
                hint = contextual
            elif (target and normalized_hint(header) in {"sl", "dvt", "dv"}
                  and not own_matches and matches and name not in canonical_schemas):
                hint = ColumnHint(None, (target,), "CONFLICTING_WORKFLOW_EVIDENCE",
                                  requires_review=True, ambiguous=True)
            columns.append(hint)
        proposals = tuple(c.target for c in columns)
        # Duplicate headers/aliases cannot silently overwrite the same target.
        duplicates = {p for p in proposals if p and proposals.count(p) > 1}
        columns = [replace(c, target=None, candidates=(c.target,),
                           reason="DUPLICATE_OR_AMBIGUOUS_TARGET" + (
                               ";" + c.reason if "CURATED:" in c.reason else ""), ambiguous=True)
                   if c.target in duplicates else c for c in columns]
        proposals = tuple(c.target for c in columns)
        present = {p for p in proposals if p}
        # Generic unit/name/currency alone cannot establish a business workflow.
        canonical = any(h.startswith(name + ".") and h in {o.key for o in fields} for h in headers)
        distinctive = present - {
            name + "." + k for k in ("unit", "name", "currency", "active", "price", "product_id", "ingredient_id", "supplier_id")
        }
        # Generic quantity/unit/manufacturer labels do not establish a workflow.
        generic_targets = {c.target for h, c in zip(headers, columns, strict=True)
                           if normalized_hint(h) in {"sl", "dvt", "dv", "nsx", "so luong", "quantity", "unit"}}
        if not own_matches:
            distinctive -= generic_targets
        contextual = any(not m.conflicting for m in own_matches)
        if selected is None and not canonical and (len(present) < 2 or not (distinctive or contextual)):
            continue
        required = {o.key for o in fields if o.requiredness == "required"}
        coverage = len(present & required) / max(1, len(required))
        hint = normalized_hint(sheet_name) in {
            normalized_hint(name),
            normalized_hint(SCHEMAS[name][0]),
        }
        ranked.append((len(present), coverage, bool(hint), name, tuple(columns)))
    ranked.sort(reverse=True)
    if not ranked:
        return SheetRules(None, tuple(nsx_hint(h, headers, samples[i] if i < len(samples) else ())
                                      or ColumnHint(None, (), "NO_SUPPORTED_TARGET")
                                      for i, h in enumerate(headers)), None, True)
    best = ranked[0]
    ambiguous = len(ranked) > 1 and best[:2] == ranked[1][:2]
    if best[0] == 0 or ambiguous:
        return SheetRules(None, tuple(nsx_hint(h, headers, samples[i] if i < len(samples) else ())
                                      or ColumnHint(None, (), "NO_UNIQUE_SCHEMA_EVIDENCE")
                                      for i, h in enumerate(headers)), None, True)
    columns = list(best[4])
    for i, h in enumerate(headers):
        lexical = nsx_hint(h, headers, samples[i] if i < len(samples) else ())
        if lexical:
            columns[i] = lexical
        elif columns[i].target is None and not columns[i].candidates:
            semantic = semantic_review_candidate(h, best[3])
            if semantic:
                columns[i] = ColumnHint(None, (semantic[0],), semantic[1], requires_review=True)
    return SheetRules(best[3], tuple(columns), best[1], best[1] < 1 or any(
        c.target is None or c.requires_review for c in columns),
        tuple(f"CURATED:{m.template.template_id}/{m.template.version}"
              for m in matches if m.template.schema == best[3]))


def rule_classification(headers, sheet_name, selected=None):
    result = sheet_rules(headers, sheet_name, selected)
    return result.schema, tuple(c.target for c in result.columns), result.confidence, result.low_quality
