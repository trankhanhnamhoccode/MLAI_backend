"""Deterministic source discovery. Suggestions are proposals, not accepted facts."""

from uuid import uuid4
from app.application.contracts import import_mapping as dto
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_source import ParsedFile
from app.application.import_identity import content_digest


from app.application.import_descriptors import options, rule_classification


def discover(file_id, parsed: ParsedFile):
    sheets = []
    issues = []
    sources = []
    for sheet in parsed.sheets:
        if len(sheet.rows) <= 1:
            continue
        header = sheet.rows[0]
        width = max((c.column_index + 1 for c in header.cells), default=0)
        headers = tuple(
            next((c.raw or "" for c in header.cells if c.column_index == i), "")
            for i in range(width)
        )
        kinds = [
            sorted(
                {
                    c.kind
                    for row in sheet.rows[1:]
                    for c in row.cells
                    if c.column_index == i and c.kind != "empty"
                }
            )
            for i in range(width)
        ]
        signature = content_digest(
            dict(headers=headers, kinds=kinds, header_row=header.row_number)
        )
        sid = uuid4()
        selected, proposals, confidence, _ = rule_classification(headers, sheet.name)
        sheets.append(
            dto.SheetInfo(
                file_id=file_id,
                sheet_id=sid,
                name=sheet.name,
                schema_signature=signature,
                row_count=max(0, len(sheet.rows) - 1),
                headers=headers,
                profile_id=None,
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
            # Only exact canonical descriptor keys are proposed, never silently bound.
            target = proposals[i]
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
                            else "UNKNOWN_SOURCE_FIELD"
                        )
                    ),
                    status="needs_confirmation" if target else "unmatched",
                    source_location=dto.SourceLocation(
                        file_id=file_id, sheet_id=sid, source_column_index=i
                    ),
                    source_header=h,
                    target_field=target,
                    samples=tuple(
                        (
                            next((c.raw for c in r.cells if c.column_index == i), None)
                            or ""
                        )[:200]
                        for r in sheet.rows[1:6]
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
                rows=[
                    dict(
                        row_number=r.row_number,
                        record_number=r.record_number,
                        line_start=r.line_start,
                        line_end=r.line_end,
                        cells=[
                            dict(
                                column_index=c.column_index,
                                raw=c.raw,
                                kind=c.kind,
                                formula=c.formula,
                            )
                            for c in r.cells
                        ],
                    )
                    for r in sheet.rows[1:]
                ],
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
        }:
            missing.append("sheet_type_review")
    for i in cols:
        if i.status not in {"resolved", "auto_mapped"}:
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
    if missing:
        return None, tuple(missing)
    normalizations = list(prior_normalizations)
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
                "pack_cost",
                "pack_size_base_quantity",
                "maximum_order_base_quantity",
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
            if k in {"sales_date", "effective_from", "effective_to"}
        )
        normalizations.append(
            dto.Normalization(
                rule_id="declared_date_format",
                kind="date_format",
                fields=fields,
                parameter=context.date_format,
                evidence_reference=context.evidence_reference,
            )
        )
    if context.pack_cost_basis == "PER_SOURCE_UNIT":
        normalizations = [
            r for r in normalizations if r.rule_id != "declared_pack_pricing_basis"
        ]
        if schema != "supplier_terms":
            return None, ("pricing_basis_requires_supplier_terms",)
        normalizations.append(
            dto.Normalization(
                rule_id="declared_pack_pricing_basis",
                kind="exact_scale",
                fields=("pack_cost", "pack_size_base_quantity"),
                parameter="PACK_COST_FROM_SOURCE_UNIT_PRICE",
                evidence_reference=context.evidence_reference,
            )
        )
    elif context.pack_cost_basis == "PER_PACK":
        normalizations = [
            r for r in normalizations if r.rule_id != "declared_pack_pricing_basis"
        ]
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
    return extra
