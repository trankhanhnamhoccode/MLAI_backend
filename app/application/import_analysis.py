"""Deterministic source discovery. Suggestions are proposals, not accepted facts."""

from uuid import uuid4
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_source import ParsedFile, SourceRow
from app.application.import_identity import content_digest


from app.application.import_descriptors import (
    options, rule_classification, column_candidates, unsupported_sheet_reason,
    semantic_review_candidate,
)


def header_index(rows: tuple[SourceRow, ...]) -> int:
    """Bounded title/preamble detection. Never skip a populated multi-column row."""
    for index, row in enumerate(rows[:8]):
        populated = [c for c in row.cells if c.raw not in (None, "")]
        if len(populated) >= 3 and all(c.kind == "text" and not c.formula for c in populated):
            return index
        if len(populated) > 1:
            return 0
    return 0


def source_row(row: SourceRow) -> dict:
    return dict(
        row_number=row.row_number, record_number=row.record_number,
        line_start=row.line_start, line_end=row.line_end,
        cells=[dict(column_index=c.column_index, raw=c.raw, kind=c.kind, formula=c.formula)
               for c in row.cells],
    )


def discover(file_id, parsed: ParsedFile):
    sheets = []
    issues = []
    sources = []
    for sheet in parsed.sheets:
        if len(sheet.rows) <= 1:
            continue
        index = header_index(sheet.rows)
        header = sheet.rows[index]
        body = sheet.rows[index + 1:]
        # Styled empty cells do not create columns; populated unlabelled data does.
        width = max((c.column_index + 1 for row in sheet.rows[index:]
                     for c in row.cells if c.raw not in (None, "")), default=0)
        headers = tuple(
            next((c.raw or "" for c in header.cells if c.column_index == i), "")
            for i in range(width)
        )
        kinds = [
            sorted(
                {
                    c.kind
                    for row in body
                    for c in row.cells
                    if c.column_index == i and c.kind != "empty"
                }
            )
            for i in range(width)
        ]
        signature = content_digest(
            dict(headers=headers, kinds=kinds, header_row=header.row_number,
                 **({'excel_date_system': parsed.excel_date_system} if parsed.excel_date_system else {}))
        )
        sid = uuid4()
        selected, proposals, confidence, _ = rule_classification(headers, sheet.name)
        sheets.append(
            dto.SheetInfo(
                file_id=file_id,
                sheet_id=sid,
                name=sheet.name,
                schema_signature=signature,
                row_count=len(body),
                headers=headers,
                header_row=header.row_number,
                preamble_rows=tuple(r.row_number for r in sheet.rows[:index]),
                preamble_samples=tuple(" | ".join(c.raw or "" for c in r.cells
                    if c.raw not in (None, ""))[:1000] for r in sheet.rows[:index]),
                profile_id=None,
                excel_date_system=parsed.excel_date_system,
                selected_type=selected,
                suggested_type=selected,
                classification_origin="RULE" if selected else "NONE",
                confidence=confidence,
            )
        )
        issues.append(
            dto.MappingIssue(
                mapping_id=uuid4(),
                sheet_id=sid,
                issue_type="classification",
                code=(
                    "SHEET_TYPE_PROPOSED"
                    if selected
                    else "UNSUPPORTED_OR_UNRESOLVED_SHEET"
                ),
                suggestion_reason=unsupported_sheet_reason(headers) or (
                    "SCHEMA_HEADER_EVIDENCE" if selected else "NO_UNIQUE_SCHEMA_EVIDENCE"
                ),
                status="needs_confirmation" if selected else "unmatched",
                source_location=dto.SourceLocation(file_id=file_id, sheet_id=sid),
                resolution_origin="UNRESOLVED",
                suggestion_origin="RULE" if selected else "NONE",
                confidence=confidence,
            )
        )
        issues.append(
            dto.MappingIssue(
                mapping_id=uuid4(),
                sheet_id=sid,
                issue_type="source_context",
                code="SOURCE_CONTEXT_REQUIRED",
                status="unmatched",
                source_location=dto.SourceLocation(file_id=file_id, sheet_id=sid),
                resolution_origin="UNRESOLVED",
            )
        )
        unsupported = {o.key for o in options() if o.support == "unsupported"}
        for i, h in enumerate(headers):
            target = proposals[i]
            candidates = column_candidates(h, selected) if selected else ()
            reason = "EXACT_CANONICAL_HEADER" if target == h else "CONTROLLED_HEADER_ALIAS"
            if not target:
                reason = ("DUPLICATE_OR_AMBIGUOUS_TARGET" if candidates else
                          unsupported_sheet_reason(headers) or "NO_SUPPORTED_TARGET")
                semantic = semantic_review_candidate(h, selected)
                if not candidates and semantic:
                    candidates = (semantic[0],)
                    reason = semantic[1]
            if target and target.endswith((".sales_date", ".effective_from", ".effective_to")):
                if any(c.column_index == i and c.kind == "numeric" for r in body for c in r.cells):
                    reason += ";DATE_CONVENTION_REVIEW: numeric lexical value is not an approved date format"
            informational = selected is None and sheet.name.casefold() == "readme"
            issues.append(
                dto.MappingIssue(
                    mapping_id=uuid4(),
                    sheet_id=sid,
                    issue_type="schema_blocker" if h in unsupported else "column",
                    code=(
                        "UNSUPPORTED_BUSINESS_RULE"
                        if h in unsupported
                        else (
                            "OWNER_MAPPING_APPROVAL_REQUIRED"
                            if target
                            else "AMBIGUOUS_TARGET" if candidates else "UNKNOWN_SOURCE_FIELD"
                        )
                    ),
                    status="needs_confirmation" if target else ("ambiguous" if candidates else "unmatched"),
                    source_location=dto.SourceLocation(
                        file_id=file_id, sheet_id=sid, source_column_index=i
                    ),
                    source_header=h,
                    target_field=target,
                    suggested_target_field=target,
                    candidate_targets=candidates,
                    suggestion_reason=reason,
                    field_category="D" if informational else ("B" if candidates and not target or "DATE_CONVENTION_REVIEW" in reason else "A" if target else "C"),
                    suggested_ignore=informational,
                    samples=tuple(
                        (
                            next((c.raw for c in r.cells if c.column_index == i), None)
                            or ""
                        )[:200]
                        for r in body[:5]
                    ),
                    resolution_origin="UNRESOLVED",
                    suggestion_origin="RULE" if target else "NONE",
                    confidence=confidence if target else None,
                )
            )
        sources.append(
            dict(
                sheet_id=str(sid),
                file_id=str(file_id),
                preamble=[source_row(r) for r in sheet.rows[:index]],
                header=source_row(header),
                excel_date_system=parsed.excel_date_system,
                rows=[dict(source_row(r), excel_date_system=parsed.excel_date_system) for r in body],
            )
        )
    return sheets, issues, sources


def source_context_conflicts(sheet, rawsheet, scope):
    """Only explicit metadata columns, never filename/header-shape identity inference.

    These columns are still manually resolved/ignored. Their declarations cannot
    override an approved scope and are not evidence of external verification.
    """
    conflicts = []
    for key in ("source_system_key", "report_type"):
        header = "source_context." + key
        if header not in sheet.headers:
            continue
        index = sheet.headers.index(header)
        values = {
            c["raw"]
            for row in rawsheet["rows"]
            for c in row["cells"]
            if c["column_index"] == index and c["raw"] not in (None, "")
        }
        if len(values) > 1 or values and values != {getattr(scope, key)}:
            conflicts.append(
                dto.Notice(
                    code="SOURCE_CONTEXT_CONFLICT",
                    severity="ERROR",
                    message="Explicit source declaration conflicts with the selected scope",
                    source_location=dto.SourceLocation(
                        file_id=sheet.file_id,
                        sheet_id=sheet.sheet_id,
                        source_column_index=index,
                    ),
                )
            )
    return tuple(conflicts)


def receipt_sensitive_reads(sources, bindings, import_values=None):
    """Conservative raw/declaration guards before source/evidence is exposed."""
    required=set()
    fields={'inventory_receipts.unit_cost':'procurement.cost.read',
            'inventory_receipts.supplier_id':'supplier.read'}
    for source in sources:
        for binding in bindings.get(source['sheet_id'],()):
            permission=fields.get(binding.target_field)
            if permission is None: continue
            column=binding.source_column_index if isinstance(binding,dto.FieldBinding) else binding.source_location.source_column_index
            if any(cell.get('raw') is not None and str(cell['raw']).strip()!=''
                for row in source['rows'] for cell in row['cells'] if cell['column_index']==column):
                required.add(permission)
        for declaration in (import_values or {}).get(source['sheet_id'],()):
            if declaration.target_field in fields and declaration.value is not None:
                required.add(fields[declaration.target_field])
    return required


def captured_domains(sources, bindings):
    """Classify only explicitly bound declaration kind for least-privilege reads.

    Unknown/malformed kind remains the conservative full declaration scope; this
    does not validate a declaration or elevate actor permissions.
    """
    import json

    domains = set()
    for source in sources:
        fields = bindings.get(source["sheet_id"], ())
        schemas = {b.target_field.split(".")[0] for b in fields if b.target_field}
        domains.update(schemas - {"scope_declarations"})
        if "scope_declarations" not in schemas:
            continue
        column = next(
            (
                (
                    b.source_column_index
                    if isinstance(b, dto.FieldBinding)
                    else b.source_location.source_column_index
                )
                for b in fields
                if b.target_field == "scope_declarations.declaration"
            ),
            None,
        )
        for row in source["rows"]:
            raw = next(
                (c["raw"] for c in row["cells"] if c["column_index"] == column), None
            )
            try:
                kind = json.loads(raw).get("kind")
            except (ValueError, TypeError, AttributeError):
                kind = None
            domains.add(
                "scope_declarations." + kind
                if kind in {"INVENTORY", "SALES_COVERAGE", "PROCUREMENT_CONTEXT"}
                else "scope_declarations"
            )
    return domains


def build_spec(
    sheet,
    issues,
    actor_id,
    identities=(),
    entities=(),
    conversions=(),
    prior_normalizations=(),
    prior_spec: dto.ProfileSpec | None = None,
    shared_field_bindings=None,
):
    own = [i for i in issues if i.sheet_id == sheet.sheet_id]
    context = next(
        (
            i.resolution.resolution
            for i in own
            if i.issue_type == "source_context" and i.resolution
        ),
        None,
    )
    cols = [i for i in own if i.issue_type == "column"]
    targets = [i.target_field for i in cols if i.target_field]
    schemas = {t.split(".")[0] for t in targets}
    if sheet.selected_type is not None:
        schemas.add(sheet.selected_type)
    missing = []
    if context is None:
        missing.append("source_context")
    if len(schemas) != 1:
        missing.append("single_sheet_schema")
    for i in own:
        if i.issue_type == "classification" and i.status not in {
            "resolved",
            "auto_mapped",
        } and not (i.status == "needs_confirmation" and i.suggestion_origin == "RULE"
                   and sheet.selected_type == sheet.suggested_type):
            missing.append("sheet_type_review")
    for i in cols:
        if i.status not in {"resolved", "auto_mapped"} and not (
            i.status == "needs_confirmation" and i.suggestion_origin == "RULE"
            and i.target_field and i.candidate_targets == (i.target_field,)
            and (i.suggestion_reason in {"EXACT_CANONICAL_HEADER", "CONTROLLED_HEADER_ALIAS"}
                 or "DATE_CONVENTION_REVIEW" in (i.suggestion_reason or "")
                 and context is not None and context.date_format == "EXCEL_SERIAL"
                 and sheet.excel_date_system in {"1900", "1904"})
        ):
            missing.append("column:" + str(i.source_location.source_column_index))
    for i in own:
        if i.issue_type in {
            "identity",
            "conversion",
            "schema_blocker",
        } and i.status not in {"resolved", "auto_mapped"}:
            missing.append(i.code + ":" + str(i.mapping_id))
    schema = next(iter(schemas)) if len(schemas) == 1 else None
    if len(targets) != len(set(targets)):
        missing.append("DUPLICATE_MAPPING")
    shared = tuple(
        shared_field_bindings
        if shared_field_bindings is not None
        else sheet.shared_field_bindings
    )
    if schema:
        required = {o.key for o in options(schema) if o.requiredness == "required"}
        shared_targets = {r.target_field for r in shared}
        if shared_targets & set(targets):
            missing.append("FIELD_SOURCE_CONFLICT")
        missing.extend(sorted(required - (set(targets) | shared_targets)))
        if (
            schema == "sales"
            and context is not None
            and context.sales_semantics is None
        ):
            missing.append("sales_semantics")
        if (
            schema == "inventory_count"
            and context is not None
            and context.inventory_semantics is None
        ):
            missing.append("inventory_semantics")
        if schema == 'inventory_receipts' and (context is None or context.inventory_semantics != 'actual_receipt'):
            missing.append('inventory_semantics:actual_receipt')
    if missing:
        return None, tuple(missing)
    normalizations = list(prior_normalizations)
    if context.stockout_aliases:
        import json
        normalizations = [r for r in normalizations if r.kind != 'stockout_alias']
        normalizations.append(dto.Normalization(rule_id='declared_stockout_aliases', kind='stockout_alias',
            fields=('is_stockout',), parameter=json.dumps([a.model_dump() for a in context.stockout_aliases],
                ensure_ascii=False, sort_keys=True), evidence_reference=context.evidence_reference))
    if context.decimal_locale:
        normalizations = [r for r in normalizations if r.kind != "decimal_locale"]
        fields = tuple(
            k
            for k in SOURCE_MODELS[schema].model_fields
            if k
            in {
                "quantity",
                "on_hand",
                "yield_quantity",
                "process_loss_rate",
                "price",
                "unit_cost",
                "pack_cost",
                "pack_size_base_quantity",
                "maximum_order_base_quantity",
                "price_quantity",
                "minimum_order_quantity",
            }
        )
        normalizations.append(
            dto.Normalization(
                rule_id="declared_decimal_locale",
                kind="decimal_locale",
                fields=fields,
                parameter=context.decimal_locale,
                evidence_reference=context.evidence_reference,
            )
        )
    if context.date_format:
        normalizations = [r for r in normalizations if r.kind != "date_format"]
        fields = tuple(
            k
            for k in SOURCE_MODELS[schema].model_fields
            if k in {"sales_date", "effective_from", "effective_to", "received_date", "expiry_date", "order_date", "report_date", "usage_date"}
        )
        if context.date_format == "EXCEL_SERIAL" and sheet.excel_date_system is None:
            return None, ("EXCEL_DATE_SYSTEM_REQUIRED",)
        normalizations.append(
            dto.Normalization(
                rule_id="declared_date_format",
                kind="date_format",
                fields=fields,
                parameter=("EXCEL_" + sheet.excel_date_system if context.date_format == "EXCEL_SERIAL" else context.date_format),
                evidence_reference=context.evidence_reference,
            )
        )
    if context.pack_cost_basis is not None:
        return None, ("USE_EXPLICIT_SUPPLIER_PRICE_BASIS",)
    if schema == "supplier_terms":
        # A newly reviewed explicit source contract replaces the old implicit-one rule.
        # Retained approved versions are never mutated by this proposal rebuild.
        normalizations = [r for r in normalizations if r.parameter != "PACK_COST_FROM_SOURCE_UNIT_PRICE"]
    return (
        dto.ProfileSpec(
            shared_field_bindings=shared,
            scope=dto.ProfileScope(
                source_system_key=context.source_system_key,
                report_type=context.report_type,
            ),
            schema=schema,
            structure=dto.Structure(
                sheet_roles=(schema,),
                header_rules=sheet.headers,
                schema_signature=sheet.schema_signature,
            ),
            field_bindings=tuple(
                dto.FieldBinding(
                    source_column_index=i.source_location.source_column_index,
                    source_header=i.source_header or "",
                    target_field=i.target_field,
                    requiredness=next(
                        (
                            o.requiredness
                            for o in options(schema)
                            if o.key == i.target_field
                        ),
                        "optional",
                    ),
                    ignored=i.target_field is None,
                    origin=i.suggestion_origin,
                    confidence=i.confidence,
                    evidence_reference=(
                        i.resolution.resolution.evidence_reference
                        if i.resolution
                        and isinstance(i.resolution.resolution, dto.Ignored)
                        else None
                    ),
                )
                for i in cols
            ),
            identity_rules=identities,
            entity_proposals=entities,
            conversions=conversions,
            normalizations=tuple(normalizations),
            sales_semantics=context.sales_semantics,
            inventory_semantics=context.inventory_semantics,
            planned_arrival_expiry_rule=context.planned_arrival_expiry_rule
            or (prior_spec.planned_arrival_expiry_rule if prior_spec else None),
            term_period_amendments=context.term_period_amendments
            or (prior_spec.term_period_amendments if prior_spec else ()),
            fee_period_amendments=context.fee_period_amendments or (prior_spec.fee_period_amendments if prior_spec else ()),
            source_provenance=dto.SourceProvenance(
                declared_by=next(
                    (
                        i.resolved_by
                        for i in own
                        if i.issue_type == "source_context" and i.resolved_by
                    ),
                    actor_id,
                ),
                evidence_references=(context.evidence_reference,),
            ),
        ),
        (),
    )


def identity_issues(sheets, issues, sources, snapshot, specs=None):
    """Unknown source tokens never gain identity from a name/filename."""
    registries = {
        "product": snapshot["products"],
        "ingredient": snapshot["ingredients"],
        "lot": snapshot["inventory_lots"],
        "supplier": snapshot["suppliers"],
    }
    extra = []
    seen = set()
    for sheet in sheets:
        spec = (specs or {}).get(str(sheet.sheet_id))
        bindings = (
            spec.field_bindings
            if spec
            else [
                dto.FieldBinding(
                    source_column_index=i.source_location.source_column_index,
                    source_header=i.source_header or "",
                    target_field=i.target_field,
                    requiredness="required",
                    ignored=False,
                )
                for i in issues
                if i.sheet_id == sheet.sheet_id
                and i.issue_type == "column"
                and i.target_field
            ]
        )
        rawsheet = next(
            raw for raw in sources if raw["sheet_id"] == str(sheet.sheet_id)
        )
        # Nested declarations use the same reviewed Store bindings as flat references.
        import json
        declaration_column = next((b.source_column_index for b in bindings
            if b.target_field == "scope_declarations.declaration"), None)
        if declaration_column is not None:
            for row in rawsheet["rows"]:
                raw = next((c["raw"] for c in row["cells"] if c["column_index"] == declaration_column), None)
                try:
                    declaration = json.loads(raw)
                    tokens = []
                    if declaration.get("kind") == "INVENTORY":
                        tokens = [("ingredient", declaration.get("ingredient_id"))] + [("lot", t) for t in declaration.get("covered_lot_ids", [])]
                    elif declaration.get("kind") == "SALES_COVERAGE":
                        tokens = [("product", t) for t in declaration.get("product_ids", [])]
                    elif declaration.get("kind") == "PROCUREMENT_CONTEXT":
                        for key in ("capacities", "supplier_limits"):
                            for item in declaration.get(key, []):
                                tokens.append(("ingredient", item.get("ingredient_id")))
                                if key == "supplier_limits":tokens.append(("supplier", item.get("supplier_id")))
                except (ValueError, TypeError, AttributeError):
                    continue
                for entity, token_value in tokens:
                    if not isinstance(token_value, str) or not token_value:
                        continue
                    resolved = any(r["id"] == token_value for r in registries[entity]) or spec and any(
                        r.entity == entity and r.source_token == token_value for r in spec.identity_rules + spec.aliases)
                    token = (str(sheet.sheet_id), entity, token_value)
                    if resolved or token in seen:
                        continue
                    seen.add(token)
                    extra.append(dto.MappingIssue(mapping_id=uuid4(), sheet_id=sheet.sheet_id,
                        issue_type="identity", code="UNKNOWN_" + entity.upper(), status="unmatched",
                        source_location=dto.SourceLocation(file_id=sheet.file_id, sheet_id=sheet.sheet_id,
                            row_number=row["row_number"], source_column_index=declaration_column),
                        source_header=token_value, target_field="scope_declarations.declaration",
                        samples=(token_value[:200],), resolution_origin="UNRESOLVED"))
        for bind in bindings:
            if not bind.target_field:
                continue
            key = bind.target_field.split(".", 1)[1]
            entity = {
                "product_id": "product",
                "ingredient_id": "ingredient",
                "lot_id": "lot",
                "supplier_id": "supplier",
                "source_business_key": {
                    "products": "product",
                    "ingredients": "ingredient",
                }.get(bind.target_field.split(".")[0]),
                "source_supplier_key": "supplier",
            }.get(key)
            if not entity:
                continue
            for row in rawsheet["rows"]:
                raw = next(
                    (
                        c["raw"]
                        for c in row["cells"]
                        if c["column_index"] == bind.source_column_index
                    ),
                    None,
                )
                if not raw:
                    continue
                resolved = (
                    any(r["id"] == raw for r in registries[entity])
                    if key.endswith("_id")
                    else False
                )
                if spec:
                    resolved = (
                        resolved
                        or any(
                            a.entity == entity and a.source_token == raw
                            for a in spec.identity_rules + spec.aliases
                        )
                        or any(
                            a.entity == entity and a.source_business_key == raw
                            for a in spec.entity_proposals
                        )
                    )
                if resolved:
                    continue
                token = (str(sheet.sheet_id), entity, raw)
                if token in seen:
                    continue
                seen.add(token)
                extra.append(
                    dto.MappingIssue(
                        mapping_id=uuid4(),
                        sheet_id=sheet.sheet_id,
                        issue_type="identity",
                        code="UNKNOWN_" + entity.upper(),
                        status="unmatched",
                        source_location=dto.SourceLocation(
                            file_id=sheet.file_id,
                            sheet_id=sheet.sheet_id,
                            row_number=row["row_number"],
                            source_column_index=bind.source_column_index,
                        ),
                        source_header=raw,
                        target_field=bind.target_field,
                        samples=(raw[:200],),
                        resolution_origin="UNRESOLVED",
                    )
                )
        unit_bind = next(
            (
                b
                for b in bindings
                if b.target_field and b.target_field.endswith(".unit")
            ),
            None,
        )
        reference_field = (
            "product_id"
            if unit_bind and unit_bind.target_field.startswith("sales.")
            else "ingredient_id"
        )
        ref_bind = next(
            (
                b
                for b in bindings
                if b.target_field and b.target_field.endswith("." + reference_field)
            ),
            None,
        )
        if unit_bind and ref_bind:
            entity = (
                "ingredient"
                if ref_bind.target_field.endswith(".ingredient_id")
                else "product"
            )
            for row in rawsheet["rows"]:
                raw = next(
                    (
                        c["raw"]
                        for c in row["cells"]
                        if c["column_index"] == unit_bind.source_column_index
                    ),
                    None,
                )
                ident = next(
                    (
                        c["raw"]
                        for c in row["cells"]
                        if c["column_index"] == ref_bind.source_column_index
                    ),
                    None,
                )
                record = next((r for r in registries[entity] if r["id"] == ident), None)
                unit = (
                    record.get(
                        "base_unit" if entity == "ingredient" else "selling_unit"
                    )
                    if record
                    else None
                )
                token = (str(sheet.sheet_id), "unit", raw)
                if (
                    raw
                    and unit
                    and raw != unit
                    and token not in seen
                    and not (
                        spec
                        and any(
                            c.from_unit == raw and c.to_unit == unit
                            for c in spec.conversions
                        )
                    )
                ):
                    seen.add(token)
                    extra.append(
                        dto.MappingIssue(
                            mapping_id=uuid4(),
                            sheet_id=sheet.sheet_id,
                            issue_type="conversion",
                            code="UNIT_CONVERSION_REQUIRED",
                            status="unmatched",
                            source_location=dto.SourceLocation(
                                file_id=sheet.file_id,
                                sheet_id=sheet.sheet_id,
                                row_number=row["row_number"],
                                source_column_index=unit_bind.source_column_index,
                            ),
                            source_header=raw,
                            target_field=unit_bind.target_field,
                            samples=(raw[:200], unit),
                            resolution_origin="UNRESOLVED",
                        )
                    )
        # Supplier denominator and physical MOQ units also need reachable M04 review.
        # Shared declarations and reviewed identity aliases must follow the same path.
        if any(b.target_field and b.target_field.startswith("supplier_terms.") for b in bindings):
            def source_field(row, field):
                target = "supplier_terms." + field
                binding = next((b for b in bindings if b.target_field == target), None)
                if binding:
                    return next((c["raw"] for c in row["cells"] if c["column_index"] == binding.source_column_index), None), binding.source_column_index
                rule = next((r for r in spec.shared_field_bindings if r.target_field == target), None) if spec else None
                declaration = rule if rule and rule.scope == "PROFILE_CONSTANT" else next(
                    (v for v in sheet.import_values if v.target_field == target), None)
                return (declaration.value if declaration else None), None

            for row in rawsheet["rows"]:
                ident, _ = source_field(row, "ingredient_id")
                if spec:
                    ident = next((str(r.canonical_id) for r in spec.identity_rules + spec.aliases
                        if r.entity == "ingredient" and r.source_token == ident), ident)
                record = next((r for r in registries["ingredient"] if r["id"] == ident), None)
                if record is None and spec:
                    record = next(({"base_unit": r.metadata.base_unit} for r in spec.entity_proposals
                        if r.entity == "ingredient" and r.source_business_key == ident), None)
                unit = record["base_unit"] if record else None
                for field in ("unit", "price_unit", "moq_unit"):
                    raw, index = source_field(row, field)
                    token = (str(sheet.sheet_id), "unit", raw)
                    if raw and unit and raw != unit and token not in seen and not (
                        spec and any(c.from_unit == raw and c.to_unit == unit for c in spec.conversions)):
                        seen.add(token)
                        extra.append(dto.MappingIssue(mapping_id=uuid4(), sheet_id=sheet.sheet_id,
                            issue_type="conversion", code="UNIT_CONVERSION_REQUIRED", status="unmatched",
                            source_location=dto.SourceLocation(file_id=sheet.file_id, sheet_id=sheet.sheet_id,
                                row_number=row["row_number"], source_column_index=index),
                            source_header=raw, target_field="supplier_terms." + field,
                            samples=(raw[:200], unit), resolution_origin="UNRESOLVED"))
    return extra
