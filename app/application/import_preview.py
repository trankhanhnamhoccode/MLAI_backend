"""Snapshot-only normalization/preview. Retains blockers; never writes canonical data."""

from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import json
import re
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from typing import Annotated, get_args, get_origin
from pydantic import BaseModel, ValidationError
from app.application.contracts import import_mapping as dto
from app.application.contracts import import_domains as domains


class RowBlocked(Exception):
    pass


def exact_text(value):
    value = Fraction(value)
    d = value.denominator
    a = b = 0
    while d % 2 == 0:
        d //= 2
        a += 1
    while d % 5 == 0:
        d //= 5
        b += 1
    if d != 1:
        raise RowBlocked("NON_TERMINATING_CONVERSION")
    scale = max(a, b)
    if scale > 1000:
        raise RowBlocked("NUMERIC_RESOURCE_LIMIT")
    n = value.numerator * 2 ** (scale - a) * 5 ** (scale - b)
    sign = "-" if n < 0 else ""
    s = str(abs(n)).rjust(scale + 1, "0")
    s = (s[:-scale] + "." + s[-scale:]).rstrip("0").rstrip(".") if scale else s
    return sign + s if n else "0"


def notice(code, location, warning=False):
    return dto.Notice(
        code=code,
        severity="WARNING" if warning else "ERROR",
        message=code,
        source_location=location,
    )


def metadata_equal(key, left, right):
    if key == "price" and left is not None and right is not None:
        return Decimal(left) == Decimal(right)
    return left == right


def raw_value(raw, annotation):
    # Canonical lexical grammar only. No locale/date/unit guessing.
    if raw is None or raw == "":
        return None

    def includes(wanted):
        def visit(value):
            if get_origin(value) is Annotated:
                return visit(get_args(value)[0])
            if value is wanted:
                return True
            if (
                wanted is BaseModel
                and isinstance(value, type)
                and issubclass(value, BaseModel)
            ):
                return True
            return any(visit(a) for a in get_args(value) if a is not type(None))

        return visit(annotation)

    if includes(bool):
        if raw not in {"true", "false"}:
            raise RowBlocked("INVALID_BOOLEAN")
        return raw == "true"
    if includes(int):
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)", raw):
            raise RowBlocked("INVALID_INTEGER")
        return int(raw)
    if get_origin(annotation) is tuple or includes(BaseModel):
        try:
            return json.loads(
                raw,
                parse_float=lambda _: (_ for _ in ()).throw(
                    RowBlocked("FLOAT_NOT_ALLOWED")
                ),
            )
        except (ValueError, TypeError):
            raise RowBlocked("INVALID_STRUCTURED_VALUE") from None
    return raw


def derived_provenance(provenance, field, rules):
    original = next(p for p in provenance if p.field == field)
    return original.model_copy(
        update={"origin": "DETERMINISTIC_DERIVED",
                "applied_rule_ids": tuple(dict.fromkeys(original.applied_rule_ids + rules))}
    )


def approved_identity(spec: dto.ProfileSpec, entity: str, token: str) -> str | None:
    targets = {str(r.canonical_id) for r in spec.identity_rules + spec.aliases
        if r.entity == entity and r.source_token == token}
    targets.update(str(r.reserved_canonical_id) for r in spec.entity_proposals
        if r.entity == entity and r.source_business_key == token)
    if len(targets) > 1:
        raise RowBlocked("AMBIGUOUS_IDENTITY_BINDING")
    return next(iter(targets), None)


def resolve_nested_identities(value, spec):
    """Only existing typed declaration paths; never arbitrary nested-field inference."""
    def one(entity, token):
        return approved_identity(spec, entity, token) or token if isinstance(token, str) else token
    value = dict(value)
    if value.get("kind") == "INVENTORY":
        value["ingredient_id"] = one("ingredient", value.get("ingredient_id"))
        value["covered_lot_ids"] = [one("lot", t) for t in value.get("covered_lot_ids", [])]
    elif value.get("kind") == "SALES_COVERAGE":
        value["product_ids"] = [one("product", t) for t in value.get("product_ids", [])]
    elif value.get("kind") == "PROCUREMENT_CONTEXT":
        for key in ("capacities", "supplier_limits"):
            value[key] = [dict(item, ingredient_id=one("ingredient", item.get("ingredient_id")),
                **({"supplier_id":one("supplier", item.get("supplier_id"))} if key == "supplier_limits" else {}))
                for item in value.get(key, [])]
    return value


def normalize_supplier(
    values: dict[str, object], spec: dto.ProfileSpec, provenance: list[dto.FieldProvenance],
) -> tuple[domains.ResolvedTermSource, tuple[dto.FieldProvenance, ...]]:
    from app.domain.supplier_units import physical_factor, pack_price, physical_moq_packs
    source = domains.TermImportSource.model_validate(values)
    matching = [c for c in spec.conversions if c.from_unit == source.unit]
    if len(matching) > 1:
        raise RowBlocked("AMBIGUOUS_CONVERSION")
    canonical_unit = matching[0].to_unit if matching else source.unit

    def scale(unit: str) -> tuple[Fraction, tuple[str, ...]]:
        expected = physical_factor(unit, canonical_unit)
        rules = [c for c in spec.conversions if c.from_unit == unit]
        if len(rules) > 1:
            raise RowBlocked("AMBIGUOUS_CONVERSION")
        if unit != canonical_unit and not rules:
            raise RowBlocked("SUPPLIER_UNIT_CONVERSION_REQUIRED")
        if rules:
            c = rules[0]
            factor = Fraction(Decimal(c.factor.numerator)) / Fraction(Decimal(c.factor.denominator))
            if c.to_unit != canonical_unit or factor != expected:
                raise RowBlocked("INVALID_SUPPLIER_UNIT_FACTOR")
            return expected, ("conversion:" + c.evidence_reference,)
        return expected, ()

    factor, pack_rules = scale(source.unit)
    pack = Fraction(Decimal(source.pack_size_base_quantity)) * factor
    data = {k: v for k, v in source.model_dump().items() if k in domains.TermSource.model_fields}
    data.update(unit=canonical_unit, pack_size_base_quantity=exact_text(pack))
    for field in ("unit", "pack_size_base_quantity", "maximum_order_base_quantity"):
        if field == "maximum_order_base_quantity" and source.maximum_order_base_quantity is None:
            continue
        if source.maximum_order_base_quantity is not None and field == "maximum_order_base_quantity":
            data[field] = exact_text(Fraction(Decimal(source.maximum_order_base_quantity)) * factor)
        if pack_rules:
            provenance = [p for p in provenance if p.field != field] + [derived_provenance(provenance, field, pack_rules)]
    denominator = None
    if source.price_basis == "PER_QUANTITY":
        price_factor, price_rules = scale(source.price_unit)
        denominator = Fraction(Decimal(source.price_quantity)) * price_factor
        data["pack_cost"] = exact_text(pack_price(Fraction(Decimal(source.pack_cost)), pack, denominator))
        provenance = [p for p in provenance if p.field != "pack_cost"] + [
            derived_provenance(provenance, "pack_cost", pack_rules + price_rules + ("supplier:price_per_quantity",))]
    moq_quantity = None
    moq_rules = ()
    if source.moq_basis == "PHYSICAL_QUANTITY":
        moq_factor, moq_rules = scale(source.moq_unit)
        moq_quantity = Fraction(Decimal(source.minimum_order_quantity)) * moq_factor
        minimum_packs = physical_moq_packs(moq_quantity, pack)
        moq_rules += pack_rules + ("supplier:physical_moq_ceil_packs",)
    else:
        minimum_packs = int(Decimal(source.minimum_order_quantity))
        moq_rules = ("supplier:integer_pack_moq",)
    data["minimum_order_packs"] = minimum_packs
    p = derived_provenance(provenance, "minimum_order_quantity", moq_rules)
    provenance.append(p.model_copy(update={"field": "minimum_order_packs"}))
    canonical = domains.TermSource.model_validate(data)
    semantics = domains.SupplierTermSemantics(
        pack_label=source.pack_label, source_pack_quantity=source.pack_size_base_quantity,
        source_pack_unit=source.unit, source_price=source.pack_cost, price_basis=source.price_basis,
        price_quantity=source.price_quantity, price_unit=source.price_unit,
        canonical_price_quantity=exact_text(denominator) if denominator is not None else None,
        moq_basis=source.moq_basis, source_moq_quantity=source.minimum_order_quantity,
        moq_unit=source.moq_unit, canonical_moq_quantity=exact_text(moq_quantity) if moq_quantity is not None else None,
        minimum_order_packs=minimum_packs)
    return domains.ResolvedTermSource(**canonical.model_dump(), source_semantics=semantics), tuple(provenance)


def normalize(source, spec, import_values=()):
    from app.application.contracts.import_field_values import (
        ImportValue,
        ProfileConstant,
    )

    spec = dto.ProfileSpec.model_validate(spec.model_dump())
    model = domains.SOURCE_MODELS[spec.schema]
    values = {"domain": spec.schema}
    provenance = []
    for bind in spec.field_bindings:
        if bind.ignored:
            continue
        field = bind.target_field.split(".", 1)[1]
        cell = next(
            (
                c
                for c in source["cells"]
                if c["column_index"] == bind.source_column_index
            ),
            None,
        )
        raw = cell["raw"] if cell else None
        if cell and cell["kind"] == "error":
            raise RowBlocked("SOURCE_CELL_ERROR")
        if (
            cell
            and cell["kind"] == "boolean"
            and "bool" in str(model.model_fields[field].annotation)
        ):
            if raw not in {"0", "1"}:
                raise RowBlocked("INVALID_BOOLEAN")
            raw = "true" if raw == "1" else "false"
        identity_bound = False
        if field in {"source_business_key", "source_supplier_key"} and raw:
            kind = {"products":"product", "ingredients":"ingredient", "suppliers":"supplier"}.get(spec.schema)
            if kind:
                approved_identity(spec, kind, raw)
        if field in {"product_id", "ingredient_id", "lot_id", "supplier_id"} and raw:
            entity = {
                "product_id": "product",
                "ingredient_id": "ingredient",
                "lot_id": "lot",
                "supplier_id": "supplier",
            }[field]
            target = approved_identity(spec, entity, raw)
            if target:
                identity_bound = True
                raw = target
        alias_rules = ()
        if field == 'is_stockout' and raw not in (None, '', 'true', 'false'):
            aliases = [a for n in spec.normalizations if n.kind == 'stockout_alias'
                       for a in (dto.StockoutAlias.model_validate(v) for v in json.loads(n.parameter))
                       if a.token == raw]
            if len(aliases) != 1:
                raise RowBlocked('STOCKOUT_VALUE_ALIAS_REQUIRED')
            raw = None if aliases[0].value is None else 'true' if aliases[0].value else 'false'
            alias_rules = ('declared_stockout_aliases',)
        values[field] = raw_value(raw, model.model_fields[field].annotation)
        if field == "declaration" and isinstance(values[field], dict):
            bound = resolve_nested_identities(values[field], spec)
            identity_bound = bound != values[field]
            values[field] = bound
        provenance.append(
            dto.FieldProvenance(
                field=field,
                source_value=cell["raw"] if cell else None,
                origin="SOURCE_EXPLICIT",
                value_source="IDENTITY_BINDING" if identity_bound else "SOURCE_COLUMN",
                source_column_index=bind.source_column_index,
                applied_rule_ids=alias_rules,
            )
        )
    declarations = [
        ImportValue.model_validate(v.model_dump() if isinstance(v, ImportValue) else v)
        for v in import_values
    ]
    by_target = {v.target_field: v for v in declarations}
    allowed = {
        r.target_field for r in spec.shared_field_bindings if r.scope == "IMPORT_VALUE"
    }
    if len(by_target) != len(declarations) or not set(by_target) <= allowed:
        raise RowBlocked("FIELD_SOURCE_CONFLICT")
    for rule in spec.shared_field_bindings:
        declaration = (
            rule
            if isinstance(rule, ProfileConstant)
            else by_target.get(rule.target_field)
        )
        if declaration is None:
            raise RowBlocked("MISSING_IMPORT_VALUE")
        field = rule.target_field.split(".", 1)[1]
        value = declaration.value
        raw = (
            "true"
            if value is True
            else (
                "false"
                if value is False
                else str(value) if type(value) is int else value
            )
        )
        values[field] = raw_value(raw, model.model_fields[field].annotation)
        provenance.append(
            dto.FieldProvenance(
                field=field,
                source_value=declaration.value,
                origin="SOURCE_EXPLICIT",
                value_source=rule.scope,
                declaration_id=declaration.declaration_id,
            )
        )
    for rule in spec.normalizations:
        if (
            rule.kind == "exact_scale"
            and rule.parameter == "PACK_COST_FROM_SOURCE_UNIT_PRICE"
        ):
            raise RowBlocked("SUPPLIER_BASIS_REVIEW_REQUIRED")
        for field in rule.fields:
            if rule.kind == 'stockout_alias':
                continue  # Exact aliases applied before strict scalar parsing above.
            value = values.get(field)
            if value is None:
                continue
            if rule.kind == "decimal_locale" and rule.parameter == "comma":
                if not re.fullmatch(r"(0|[1-9][0-9]*)(,[0-9]+)?", value):
                    raise RowBlocked("INVALID_DECLARED_DECIMAL")
                values[field] = value.replace(",", ".")
            elif rule.kind == "date_format" and rule.parameter in {"EXCEL_1900", "EXCEL_1904"}:
                from app.application.import_excel_dates import excel_date
                system = rule.parameter.removeprefix("EXCEL_")
                if source.get("excel_date_system") != system:
                    raise RowBlocked("EXCEL_DATE_SYSTEM_CONFLICT")
                try:
                    values[field] = excel_date(value, system)
                except ValueError:
                    raise RowBlocked("INVALID_EXCEL_DATE") from None
            elif rule.kind == "date_format" and rule.parameter in {
                "DMY_SLASH",
                "MDY_SLASH",
            }:
                if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
                    raise RowBlocked("INVALID_DECLARED_DATE")
                a, b, y = map(int, value.split("/"))
                values[field] = (
                    date(y, b, a).isoformat()
                    if rule.parameter == "DMY_SLASH"
                    else date(y, a, b).isoformat()
                )
            elif rule.kind not in {"decimal_locale", "date_format"}:
                raise RowBlocked("UNSUPPORTED_NORMALIZATION")
            if values[field] != value:
                provenance = [p for p in provenance if p.field != field] + [
                    derived_provenance(provenance, field, (rule.rule_id,))
                ]
    if spec.schema in domains.HISTORY_MODELS:
        from app.application.import_history import normalize_history
        return normalize_history(values, spec, provenance)
    if spec.schema == "supplier_terms":
        if not spec.supports_supplier_basis():
            raise RowBlocked("SUPPLIER_BASIS_REVIEW_REQUIRED")
        try:
            return normalize_supplier(values, spec, provenance)
        except ValidationError:
            raise RowBlocked("INVALID_SOURCE_VALUE") from None
        except ValueError as error:
            raise RowBlocked(str(error)) from None
    # Conversions must not launder unsupported lexical representations into valid facts.
    if spec.schema in {"recipes", "opening_stock", "inventory_count", "inventory_receipts"}:
        try:
            model.model_validate(values)
        except ValidationError as e:
            missing = any(error["loc"] and values.get(error["loc"][0]) is None
                          for error in e.errors(include_input=False))
            raise RowBlocked("MISSING_REQUIRED_VALUE" if missing else "INVALID_SOURCE_VALUE") from None
    if values.get("unit"):
        matching = [c for c in spec.conversions if c.from_unit == values["unit"]]
        if len(matching) > 1:
            raise RowBlocked("AMBIGUOUS_CONVERSION")
        if matching:
            c = matching[0]
            factor = Fraction(Decimal(c.factor.numerator)) / Fraction(
                Decimal(c.factor.denominator)
            )
            if spec.schema in {"recipes", "opening_stock", "inventory_count", "inventory_receipts"}:
                unit_kind = "RECIPE" if spec.schema == "recipes" else "STOCK"
                # Supported physical rules only; a declared factor is not density authority.
                scales = {"mg": ("mass", Fraction(1, 1000)), "g": ("mass", Fraction(1)),
                          "kg": ("mass", Fraction(1000)), "ml": ("volume", Fraction(1)),
                          "mL": ("volume", Fraction(1)), "l": ("volume", Fraction(1000)),
                          "L": ("volume", Fraction(1000))}
                source_unit, target_unit = scales.get(c.from_unit), scales.get(c.to_unit)
                if c.from_unit == c.to_unit:
                    expected_factor = Fraction(1)
                elif source_unit is None or target_unit is None:
                    raise RowBlocked("UNSUPPORTED_" + unit_kind + "_UNIT_CONVERSION")
                elif source_unit[0] != target_unit[0]:
                    raise RowBlocked("INCOMPATIBLE_" + unit_kind + "_UNIT_CONVERSION")
                else:
                    expected_factor = source_unit[1] / target_unit[1]
                if factor != expected_factor:
                    raise RowBlocked("INVALID_" + unit_kind + "_UNIT_FACTOR")
            if spec.schema in {"opening_stock", "inventory_receipts"} and values.get("unit_cost") is not None:
                values["unit_cost"] = exact_text(Fraction(Decimal(values["unit_cost"])) / factor)
                provenance = [p for p in provenance if p.field != "unit_cost"] + [
                    derived_provenance(provenance, "unit_cost", ("conversion:" + c.evidence_reference,))]
            for field in (
                "quantity",
                "on_hand",
                "pack_size_base_quantity",
                "maximum_order_base_quantity",
            ):
                if values.get(field) is not None:
                    values[field] = exact_text(
                        Fraction(Decimal(values[field])) * factor
                    )
                    provenance = [p for p in provenance if p.field != field] + [
                        derived_provenance(
                            provenance, field, ("conversion:" + c.evidence_reference,)
                        )
                    ]
            values["unit"] = c.to_unit
            provenance = [p for p in provenance if p.field != "unit"] + [
                derived_provenance(
                    provenance, "unit", ("conversion:" + c.evidence_reference,)
                )
            ]
    try:
        value = model.model_validate(values)
        if isinstance(value, domains.RecipeSource) and value.quantity_basis == "PER_SERVING":
            quantity = exact_text(Fraction(Decimal(value.quantity)) * Fraction(Decimal(value.yield_quantity)))
            value = model.model_validate({**value.model_dump(), "quantity": quantity})
            original = next(p for p in provenance if p.field == "quantity")
            provenance = [p for p in provenance if p.field != "quantity"] + [
                derived_provenance(provenance, "quantity", original.applied_rule_ids + ("recipe:per_serving_times_yield",))
            ]
        return value, tuple(provenance)
    except ValidationError as e:
        errors = e.errors(include_input=False)
        code = (
            "MISSING_REQUIRED_VALUE"
            if any(
                x["type"] in {"missing", "string_type", "date_type", "uuid_type"}
                and values.get(x["loc"][0]) is None
                for x in errors
            )
            else "INVALID_SOURCE_VALUE"
        )
        raise RowBlocked(code) from None
    except (ValueError, ArithmeticError):
        raise RowBlocked("INVALID_SOURCE_VALUE") from None


def supplier_fee_coverage(value, spec, snapshot, normalized):
    """Coverage at term start only, not procurement readiness for a future horizon."""
    from app.application.operational_import_facts import current_fees
    from app.application.planning_fee_bindings import fee_bindings
    try:
        amendments = {str(a.fee_id): a for _, _, _, s in normalized for a in s.fee_period_amendments}
        fees = [(domains.FeeSource.model_validate({**r["payload"], **(
                    {"effective_to": amendments[r["id"]].effective_to.isoformat()} if r["id"] in amendments else {})},
                    context={"retained_evidence": True}), r["source_system_key"]) for r in current_fees(snapshot)]
    except ValidationError:
        return "UNKNOWN"
    fees.extend((v, s.scope.source_system_key) for v, _, _, s in normalized if isinstance(v, domains.FeeSource))
    fees = [(f, system) for f, system in fees if f.effective_from <= value.effective_from
            and (f.effective_to is None or f.effective_to >= value.effective_from)]
    if len(fees) != 1:
        return "UNKNOWN"
    fee, system = fees[0]
    if fee.coverage != "COMPLETE" or fee.currency != value.currency:
        return "UNKNOWN"
    probe = "preview-term:" + value.source_term_key
    terms = list(snapshot.get("term_source_records", ()))
    terms.extend(dict(id="preview-term:" + v.source_term_key, source_system_key=s.scope.source_system_key,
        source_record_key=v.source_term_key) for v, _, _, s in normalized if isinstance(v, domains.TermSource))
    suppliers = list(snapshot.get("supplier_source_records", ()))
    for v, _, _, s in normalized:
        if isinstance(v, domains.SupplierSource):
            ident = next((r.canonical_id for r in s.identity_rules + s.aliases
                if r.entity == "supplier" and r.source_token == v.source_supplier_key), None)
            ident = ident or next((r.reserved_canonical_id for r in s.entity_proposals
                if r.entity == "supplier" and r.source_business_key == v.source_supplier_key), None)
            if ident:
                suppliers.append(dict(supplier_id=str(ident), source_system_key=s.scope.source_system_key,
                    source_record_key=v.source_supplier_key))
    bindings = fee_bindings(terms, suppliers, system)
    return "COMPLETE" if bindings.covers(fee, [dict(id=probe, supplier_id=str(value.supplier_id))]) else "UNKNOWN"


def make_preview(
    sources, specs, snapshot, now, store_timezone, currency, import_values=None, stockout_policies=None
):
    products = {r["id"]: r for r in snapshot["products"]}
    ingredients = {r["id"]: r for r in snapshot["ingredients"]}
    suppliers = {r["id"]: r for r in snapshot["suppliers"]}
    lots = {r["id"]: r for r in snapshot["inventory_lots"]}
    reservations = {}
    reservation_conflicts = set()
    for spec in specs.values():
        for ent in spec.entity_proposals:
            previous = reservations.get(str(ent.reserved_canonical_id))
            if previous and (previous.entity != ent.entity or previous.metadata != ent.metadata):
                reservation_conflicts.add(str(ent.reserved_canonical_id))
            reservations[str(ent.reserved_canonical_id)] = ent
            target = {
                "product": products,
                "ingredient": ingredients,
                "supplier": suppliers,
            }[ent.entity]
            payload = ent.metadata.model_dump(mode="json")
            payload["id"] = str(ent.reserved_canonical_id)
            existing = target.get(payload["id"])
            if existing:
                continue
            target[payload["id"]] = payload
    rows = []
    normalized = []
    seen = set()
    recipe_groups = {}
    amended_terms = set()
    today = now.astimezone(ZoneInfo(store_timezone)).date()
    for sheet in sources:
        spec = specs[sheet["sheet_id"]]
        for source in sheet["rows"]:
            location = dto.SourceLocation(
                file_id=sheet["file_id"],
                sheet_id=sheet["sheet_id"],
                row_number=source["row_number"],
                record_number=source["record_number"],
                line_start=source["line_start"],
                line_end=source["line_end"],
            )
            try:
                value, prov = normalize(
                    source, spec, (import_values or {}).get(str(sheet["sheet_id"]), ())
                )
                normalized.append((value, prov, location, spec))
            except (RowBlocked, ArithmeticError, ValueError) as e:
                code = str(e) if isinstance(e, RowBlocked) else "INVALID_SOURCE_VALUE"
                rows.append(
                    dto.PreviewRow(
                        row_id=uuid4(),
                        source_location=location,
                        classification="INVALID",
                        proposed_action="BLOCKED",
                        entity_refs=(),
                        before=None,
                        after=None,
                        provenance=(),
                        blockers=(notice(code, location),),
                        canonical_domain=spec.schema,
                    )
                )
    for value, prov, loc, spec in normalized:
        before = None
        after = value
        action = "INSERT"
        cls = "NEW"
        blockers = []
        warnings = []
        confirm = False
        refs = []
        supplier_semantics = None
        inventory_effect = None
        receipt_effect = None
        required_permissions = ()
        stockout_update = None
        source_stockout = None
        data = value.model_dump(mode="json")

        def block(code):
            blockers.append(notice(code, loc))

        def warn(code):
            warnings.append(notice(code, loc, True))

        if any(b.ignored for b in spec.field_bindings):
            warn("SOURCE_ONLY_FIELD_IGNORED")

        def entity(kind, ident, registry):
            refs.append(dto.EntityRef(entity=kind, canonical_id=ident))
            record = registry.get(str(ident))
            if record is None:
                block("UNKNOWN_" + kind.upper())
            return record

        history_target = None
        history_version = None
        if value.domain in domains.HISTORY_MODELS:
            from app.application.import_history import preview_history
            before, cls, action, confirm, history_target = preview_history(
                value, spec, snapshot, normalized, today, now, entity, block, warn,
                ingredients, products, suppliers)
            from app.application.import_history import latest_record
            old_history = latest_record(snapshot.get('import_history_records', ()), value, spec.scope)
            history_version = str(old_history['version']) if old_history else None
            if isinstance(value, domains.UsageHistorySource) and value.observed_at is not None:
                if value.observed_at.astimezone(ZoneInfo(store_timezone)).date() != value.usage_date:
                    block('USAGE_DAY_TIMESTAMP_MISMATCH')
        elif isinstance(value, domains.SalesSource):
            product = entity("product", value.product_id, products)
            if product and value.unit != product["selling_unit"]:
                block("UNIT_MISMATCH")
            if value.sales_date > today:
                block("FUTURE_SALES_NOT_OBSERVED")
            key = ("sales", str(value.product_id), str(value.sales_date))
            if key in seen:
                block("DUPLICATE_DAILY_OBSERVATION")
            seen.add(key)
            current = next(
                (
                    r
                    for r in snapshot["sales_daily"]
                    if r["product_id"] == str(value.product_id)
                    and r["sales_date"] == str(value.sales_date)
                ),
                None,
            )
            from app.application.import_sales_sources import classify_sales, sources_for
            from app.application.import_sales_sources import latest_source, project_stockout
            history = sources_for(snapshot, value.product_id, value.sales_date)
            old_source = latest_source(history, spec.scope.source_system_key, value.business_report_key,
                                       spec.scope.report_type)
            provided = any(p.field == 'is_stockout' for p in prov)
            policy, policy_evidence = (stockout_policies or {}).get(str(loc.sheet_id), (None, None))
            if provided and (value.is_stockout is not None or policy != 'quantity_only'):
                stockout_update = 'source'
                source_stockout = value.is_stockout
            elif policy == 'quantity_only':
                stockout_update = policy
                if not old_source:
                    block('STOCKOUT_QUANTITY_ONLY_REQUIRES_EXISTING_CONTRIBUTION')
                source_stockout = old_source.get('source_stockout') if old_source else None
            else:
                stockout_update = policy
                if current and policy != 'not_provided':
                    block('STOCKOUT_UPDATE_DECLARATION_REQUIRED')
            if stockout_update == 'quantity_only' or not provided:
                prov += (dto.FieldProvenance(field='is_stockout', origin='UNKNOWN' if source_stockout is None else 'DETERMINISTIC_DERIVED',
                    applied_rule_ids=('stockout:' + (policy or 'new_unknown'),), source_value=policy_evidence),)
            target, action, cls, source_blocker = classify_sales(value, current, spec, snapshot)
            canonical_stockout = project_stockout(source_stockout, old_source, current, spec, history)
            if current and action == 'NO_OP' and current.get('is_stockout') is not canonical_stockout:
                action, cls = 'REPLACE_DAILY_TOTAL', 'CHANGED'
            after = value.model_copy(update={"quantity": target, 'is_stockout': canonical_stockout})
            if canonical_stockout is None:
                warn('STOCKOUT_UNKNOWN')
            elif canonical_stockout:
                warn('CENSORED_SALES_REQUIRES_DEMAND_POLICY')
            if Decimal(target) != Decimal(value.quantity):
                prov = tuple(
                    p.model_copy(update={
                        "origin": "DETERMINISTIC_DERIVED",
                        "applied_rule_ids": p.applied_rule_ids + ("sales:canonical_total_from_retained_source_revision",),
                    }) if p.field == "quantity" else p
                    for p in prov
                )
            if current:
                before = value.model_copy(update={"quantity": current["quantity"], 'is_stockout': current.get('is_stockout')})
            if source_blocker:
                block(source_blocker)
            confirm = action in {"REPLACE_DAILY_TOTAL", "MERGE_DISJOINT_SALES"}
            if confirm:
                warn("SALES_DISJOINTNESS_REQUIRES_CONFIRMATION" if action == "MERGE_DISJOINT_SALES" else "SALES_REPLACEMENT_REQUIRES_CONFIRMATION")
            if current and not sources_for(snapshot, value.product_id, value.sales_date):
                warn("EXISTING_SALES_SOURCE_PROVENANCE_UNKNOWN")
        elif isinstance(value, domains.CountSource):
            ing = entity("ingredient", value.ingredient_id, ingredients)
            lot = entity("lot", value.lot_id, lots)
            if ing and value.unit != ing["base_unit"]:
                block("UNIT_MISMATCH")
            if lot and lot["ingredient_id"] != str(value.ingredient_id):
                block("LOT_INGREDIENT_MISMATCH")
            if value.observed_at > now:
                block("STALE_STOCK_OBSERVATION")
            if lot:
                if value.observed_at < datetime.fromisoformat(lot["updated_at"]):
                    block("STALE_STOCK_OBSERVATION")
                if any(r["lot_id"] == str(value.lot_id) and (
                        datetime.fromisoformat(r["occurred_at"]) > value.observed_at or
                        datetime.fromisoformat(r["created_at"]) > value.observed_at)
                        for r in snapshot["inventory_movements"]):
                    block("STALE_STOCK_OBSERVATION")
                if any(datetime.fromisoformat(r["occurred_at"]) > value.observed_at and any(
                        ref.get("canonical_domain") == "inventory_count" and ref["canonical_id"] == str(value.lot_id)
                        for ref in r["record_json"].get("completion", {}).get("canonical_references", ()))
                        for r in snapshot.get("import_audit", ())):
                    block("STALE_STOCK_OBSERVATION")
                before = value.model_copy(update={"on_hand": lot["on_hand_quantity"]})
                cls = (
                    "UNCHANGED"
                    if Decimal(value.on_hand) == Decimal(lot["on_hand_quantity"])
                    else "CHANGED"
                )
                action = "NO_OP" if cls == "UNCHANGED" else "COUNT_CORRECTION"
                confirm = cls != "UNCHANGED"
            key = ("lot", str(value.lot_id))
            if key in seen:
                block("DUPLICATE_COUNT")
            seen.add(key)
        elif isinstance(value, domains.ActualReceiptSource):
            from app.application.import_actual_receipts import canonical_receipt, planned_effect
            ing=entity('ingredient',value.ingredient_id,ingredients)
            if value.supplier_id is not None:
                entity('supplier',value.supplier_id,suppliers)
                required_permissions+=('supplier.read',)
            if value.unit_cost is not None:
                required_permissions+=('procurement.cost.read',)
            if ing and value.unit!=ing['base_unit']: block('INVALID_UNIT')
            if ing and ing['expiry_tracking'] and value.expiry_date is None: block('REQUIRED_EXPIRY_MISSING')
            if value.currency!=currency: block('CURRENCY_MISMATCH')
            if value.observed_at>now: block('STALE_STOCK_OBSERVATION')
            if value.received_date is not None and value.received_date>today: block('FUTURE_RECEIVED_DATE')
            after=canonical_receipt(value,spec.scope.source_system_key)
            receipt_effect=planned_effect(after,snapshot)
            if receipt_effect.conflict_code: block(receipt_effect.conflict_code)
            if receipt_effect.action=='REUSE_RECEIPT':
                before=after
                cls='UNCHANGED'
            action=receipt_effect.action
            refs.append(dto.EntityRef(entity='lot',canonical_id=receipt_effect.lot_id))
            if value.received_date is None: warn('MISSING_RECEIVED_DATE')
            if value.expiry_date is not None and value.expiry_date<today: warn('LOT_EXPIRED')
            if value.observed_at.astimezone(ZoneInfo(store_timezone)).date()<today or value.received_date is not None and value.received_date<today:
                warn('LATE_RECEIPT_RECORDED')
            warn('INVENTORY_COMPLETENESS_REQUIRES_DECLARATION')
            if blockers:
                receipt_effect=receipt_effect.model_copy(update={'action':'BLOCKED','conflict_code':blockers[0].code})
        elif isinstance(value, domains.OpeningSource):
            from app.application.import_opening_stock import receipt_semantics, fingerprint
            from app.application.stock_observation import opening_observation_issue
            ing = entity("ingredient", value.ingredient_id, ingredients)
            if value.supplier_id is not None:
                entity("supplier", value.supplier_id, suppliers)
            if ing and value.unit != ing["base_unit"]:
                block("UNIT_MISMATCH")
            if ing and ing["expiry_tracking"] and value.expiry_date is None:
                block("REQUIRED_EXPIRY_MISSING")
            if value.currency != currency:
                block("CURRENCY_MISMATCH")
            if value.observed_at > now:
                block("STALE_STOCK_OBSERVATION")
            if value.received_date is not None and value.received_date > today:
                block("FUTURE_RECEIVED_DATE")
            system = spec.scope.source_system_key
            old = next((r for r in snapshot.get("inventory_receipt_records", ())
                if (r["source_system_key"], r["source_record_key"]) == (system, value.source_record_id)), None)
            if old:
                if old["payload_digest"] != fingerprint(receipt_semantics(value, system)):
                    block("RECEIPT_IDENTITY_CONFLICT")
                after = domains.OpeningValue(**value.model_dump(exclude={"domain"}), lot_id=old["lot_id"])
                before = after
                cls, action = "UNCHANGED", "NO_OP"
            else:
                after = domains.OpeningValue(**value.model_dump(exclude={"domain"}), lot_id=uuid4())
                ingredient_lots = [r for r in snapshot["inventory_lots"] if r["ingredient_id"] == str(value.ingredient_id)]
                movements = [r for r in snapshot["inventory_movements"] if r["ingredient_id"] == str(value.ingredient_id)]
                counts = [(r["occurred_at"], tuple(ref["canonical_id"] for ref in
                    r["record_json"].get("completion", {}).get("canonical_references", ())
                    if ref.get("canonical_domain") == "inventory_count"))
                    for r in snapshot.get("import_audit", ())
                    if datetime.fromisoformat(r["occurred_at"]) >= value.observed_at]
                code = opening_observation_issue(ingredient_lots, movements, counts, value.observed_at, value.lot_code)
                if code:
                    block(code)
                if any(isinstance(other, domains.CountSource) and other.ingredient_id == value.ingredient_id
                        for other, _, _, _ in normalized):
                    block("STOCK_OBSERVATION_UNVERIFIABLE")
                action = "CREATE_OPENING_STOCK"
            refs.append(dto.EntityRef(entity="lot", canonical_id=after.lot_id))
            if value.received_date is None:
                warn("MISSING_RECEIVED_DATE")
            if value.expiry_date is not None and value.expiry_date < today:
                warn("LOT_EXPIRED")
            warn("INVENTORY_COMPLETENESS_REQUIRES_DECLARATION")
            for other, _, _, other_spec in normalized:
                if not isinstance(other, domains.OpeningSource) or other is value:
                    continue
                if (system, value.source_record_id) == (other_spec.scope.source_system_key, other.source_record_id):
                    block("DUPLICATE_OPENING_IDENTITY")
                if other.ingredient_id == value.ingredient_id and (other.lot_code is None or value.lot_code is None or other.lot_code == value.lot_code):
                    block("AMBIGUOUS_OPENING_LOT")
        elif isinstance(value, domains.RecipeSource):
            p = entity("product", value.product_id, products)
            i = entity("ingredient", value.ingredient_id, ingredients)
            if (
                p
                and value.yield_unit != p["selling_unit"]
                or i
                and value.unit != i["base_unit"]
            ):
                block("UNIT_MISMATCH")
            key = (str(value.product_id), value.version)
            group = recipe_groups.setdefault(key, [])
            group.append((value, prov, loc, tuple(blockers)))
            continue
        elif isinstance(
            value,
            (domains.ProductSource, domains.IngredientSource, domains.SupplierSource),
        ):
            kind = {
                "products": "product",
                "ingredients": "ingredient",
                "suppliers": "supplier",
            }[value.domain]
            sourcekey = (
                value.source_supplier_key
                if kind == "supplier"
                else value.source_business_key
            )
            proposal = next(
                (
                    e
                    for e in spec.entity_proposals
                    if e.entity == kind and e.source_business_key == sourcekey
                ),
                None,
            )
            alias = next(
                (
                    a
                    for a in spec.identity_rules + spec.aliases
                    if a.entity == kind and a.source_token == sourcekey
                ),
                None,
            )
            if proposal is None and alias is None:
                block("OWNER_ENTITY_APPROVAL_REQUIRED")
            else:
                ident = (
                    proposal.reserved_canonical_id if proposal else alias.canonical_id
                )
                refs.append(dto.EntityRef(entity=kind, canonical_id=ident))
                metadata = {
                    k: v
                    for k, v in data.items()
                    if k not in {"domain", "source_business_key", "source_supplier_key"}
                }
                if proposal and any(
                    not metadata_equal(k, metadata.get(k), v)
                    for k, v in proposal.metadata.model_dump(mode="json").items()
                ):
                    block("ENTITY_METADATA_CONFLICT")
                existing = next(
                    (r for r in snapshot[value.domain] if r["id"] == str(ident)), None
                )
                if existing:
                    if any(
                        not metadata_equal(k, existing.get(k), v)
                        for k, v in metadata.items()
                    ):
                        block("ENTITY_METADATA_CONFLICT")
                    else:
                        cls = "UNCHANGED"
                elif alias and alias.reference_state == "existing":
                    block("SOURCE_IDENTITY_CONFLICT")
                if metadata.get("sku") and any(r["id"] != str(ident) and r.get("sku") == metadata["sku"]
                        for r in snapshot[value.domain]):
                    block("ENTITY_IDENTITY_CONFLICT")
            action = "NO_OP" if cls == "UNCHANGED" else "CREATE_" + kind.upper()
        elif isinstance(value, domains.TermSource):
            after = domains.TermValue.model_validate({k: v for k, v in data.items() if k in domains.TermValue.model_fields})
            entity("supplier", value.supplier_id, suppliers)
            i = entity("ingredient", value.ingredient_id, ingredients)
            if i and value.unit != i["base_unit"]:
                block("UNIT_MISMATCH")
            if value.currency != currency:
                block("CURRENCY_MISMATCH")
            for other, _, _, _ in normalized:
                if other is value or not isinstance(other, domains.TermSource):
                    continue
                if (
                    other.active
                    and value.active
                    and other.supplier_id == value.supplier_id
                    and other.ingredient_id == value.ingredient_id
                    and other.effective_from <= (value.effective_to or date.max)
                    and value.effective_from <= (other.effective_to or date.max)
                ):
                    block("TERM_PERIOD_OVERLAP")
            key = ("term", value.source_term_key)
            if key in seen:
                block("DUPLICATE_TERM_SOURCE")
            seen.add(key)
            from app.application.operational_import_facts import latest_source
            registered = latest_source(snapshot, "term_source_records", spec.scope.source_system_key, value.source_term_key)
            latest_term = next((r for r in snapshot["supplier_terms"] if registered and r["id"] == registered["id"]),None)
            if latest_term and (latest_term["supplier_id"] != str(value.supplier_id) or latest_term["ingredient_id"] != str(value.ingredient_id)):
                block("SOURCE_IDENTITY_CONFLICT")
            if latest_term and value.effective_from < date.fromisoformat(latest_term["effective_from"]):
                block("HISTORICAL_TERM_CORRECTION")
            exact = []
            for r in snapshot["supplier_terms"]:
                numeric = ("pack_size_base_quantity", "pack_cost")
                plain = (
                    "supplier_id",
                    "ingredient_id",
                    "effective_from",
                    "effective_to",
                    "unit",
                    "minimum_order_packs",
                    "lead_time_days",
                    "shelf_life_days",
                    "active",
                )
                if registered and r["id"] != registered["id"]:
                    continue
                if all(r[k] == data[k] for k in plain) and all(
                    Decimal(r[k]) == Decimal(data[k]) for k in numeric
                ):
                    exact.append(r)
            if len(exact) > 1:
                block("SOURCE_IDENTITY_CONFLICT")
            if len(exact) == 1:
                old = exact[0]
                refs.append(
                    dto.EntityRef(entity="supplier_term", canonical_id=UUID(old["id"]))
                )
                before = after
                cls = "UNCHANGED"
                known = next((m for m in snapshot.get("term_source_records", ()) if m["id"] == old["id"]),None)
                if known and (known["source_system_key"] != spec.scope.source_system_key or known["source_record_key"] != value.source_term_key):
                    block("SOURCE_IDENTITY_CONFLICT")
                maximum = known["payload"]["maximum_order_base_quantity"] if known else None
                if known and ((maximum is None) != (value.maximum_order_base_quantity is None)
                    or maximum is not None and Decimal(maximum) != Decimal(value.maximum_order_base_quantity)):
                    block("HISTORICAL_TERM_CORRECTION")
                if not known:
                    warn("EXISTING_TERM_SOURCE_PROVENANCE_UNKNOWN")
            for r in snapshot["supplier_terms"]:
                if len(exact) == 1 and r["id"] == exact[0]["id"]:
                    continue
                if (
                    r["supplier_id"] == str(value.supplier_id)
                    and r["ingredient_id"] == str(value.ingredient_id)
                    and r["active"]
                    and value.active
                ):
                    if date.fromisoformat(r["effective_from"]) <= (
                        value.effective_to or date.max
                    ) and value.effective_from <= (
                        date.fromisoformat(r["effective_to"])
                        if r["effective_to"]
                        else date.max
                    ):
                        amendment = next(
                            (
                                a
                                for a in spec.term_period_amendments
                                if str(a.supplier_term_id) == r["id"]
                            ),
                            None,
                        )
                        if (
                            value.effective_from <= today
                            or value.effective_from
                            <= date.fromisoformat(r["effective_from"])
                        ):
                            block("HISTORICAL_TERM_CORRECTION")
                        elif amendment is None:
                            block("TERM_PERIOD_OVERLAP")
                        elif (
                            amendment.expected_version != r["_row_version"]
                            or amendment.effective_to
                            != date.fromordinal(value.effective_from.toordinal() - 1)
                            or r["effective_to"] is not None
                            or r["id"] in amended_terms
                        ):
                            block("TERM_AMENDMENT_CONFLICT")
                        else:
                            old_values = {
                                key: r[key]
                                for key in domains.TermSource.model_fields
                                if key in r
                            }
                            old_values.update(
                                domain="supplier_terms",
                                source_term_key=None,
                                currency=currency,
                                maximum_order_base_quantity=next((m["payload"]["maximum_order_base_quantity"] for m in snapshot.get("term_source_records", ()) if m["id"]==r["id"]),None),
                            )
                            previous = domains.TermValue.model_validate(old_values, context={"retained_evidence": True})
                            changed = previous.model_copy(
                                update={"effective_to": amendment.effective_to}
                            )
                            rows.append(
                                dto.PreviewRow(
                                    row_id=uuid4(),
                                    source_location=loc,
                                    classification="CHANGED",
                                    proposed_action="AMEND_TERM_PERIOD",
                                    entity_refs=(
                                        dto.EntityRef(
                                            entity="supplier_term",
                                            canonical_id=UUID(r["id"]),
                                        ),
                                    ),
                                    before=previous,
                                    after=changed,
                                    changes=(
                                        dto.Change(
                                            field="effective_to",
                                            before=None,
                                            after=amendment.effective_to.isoformat(),
                                        ),
                                    ),
                                    provenance=(
                                        dto.FieldProvenance(
                                            field="effective_to",
                                            origin="DETERMINISTIC_DERIVED",
                                            applied_rule_ids=(
                                                "owner_reviewed_period_amendment",
                                            ),
                                        ),
                                    ),
                                    warnings=(
                                        notice(
                                            "EXISTING_TERM_SOURCE_PROVENANCE_UNKNOWN",
                                            loc,
                                            True,
                                        ),
                                    ),
                                    confirmation_required=True,
                                    target_reserved_or_existing_id=UUID(r["id"]),
                                    expected_version=r["_row_version"],
                                    required_permissions=("supplier.terms.correct",),
                                )
                            )
                            amended_terms.add(r["id"])
            action = "NO_OP" if cls == "UNCHANGED" else "CREATE_SUPPLIER_TERM"
            if exact and not any(m["id"] == exact[0]["id"] for m in snapshot.get("term_source_records", ())):
                action, cls = "REGISTER_TERM_SOURCE", "NEW"
            if latest_term and not exact:
                before = domains.TermValue.model_validate({**registered["payload"],
                    "effective_to": latest_term["effective_to"]}, context={"retained_evidence": True})
                cls, confirm = "CHANGED", True
                if value.effective_from <= today or value.effective_from <= date.fromisoformat(latest_term["effective_from"]):
                    block("HISTORICAL_TERM_CORRECTION")
            if value.maximum_order_base_quantity is None:
                warn("SUPPLIER_LIMIT_SCOPE_REQUIRES_DECLARATION")
            coverage = supplier_fee_coverage(value, spec, snapshot, normalized)
            supplier_semantics = value.source_semantics.model_copy(update={
                "fee_coverage": coverage, "fee_coverage_date": value.effective_from})
            if coverage == "UNKNOWN":
                warn("PAYABLE_FEES_NOT_ESTABLISHED")
            if (
                i
                and i.get("expiry_tracking")
                and (
                    value.shelf_life_days is None
                    or spec.planned_arrival_expiry_rule is None
                )
            ):
                warn("REQUIRED_ARRIVAL_EXPIRY_UNKNOWN")
        elif isinstance(value, domains.FeeSource):
            if value.currency != currency:
                block("CURRENCY_MISMATCH")
            if value.coverage == "UNKNOWN":
                warn("FEE_COVERAGE_UNKNOWN")
            action = "CREATE_FEE_DECLARATION"
        elif isinstance(value, domains.DeclarationSource):
            d = value.declaration
            action = "SET_SCOPE_DECLARATION"
            if isinstance(d, domains.InventoryDeclaration):
                entity("ingredient", d.ingredient_id, ingredients)
                for lid in d.covered_lot_ids:
                    covered = entity("lot", lid, lots)
                    if covered and covered["ingredient_id"] != str(d.ingredient_id):
                        block("LOT_INGREDIENT_MISMATCH")
                actual = {
                    r["id"]
                    for r in snapshot["inventory_lots"]
                    if r["ingredient_id"] == str(d.ingredient_id)
                }
                if d.observed_at > now:
                    block("STALE_STOCK_OBSERVATION")
                if (
                    d.state == "COMPLETE_CURRENT_LOTS"
                    and set(map(str, d.covered_lot_ids)) != actual
                ):
                    block("INVENTORY_COVERAGE_INCOMPLETE")
                if d.state == "CONFIRMED_EMPTY" and (
                    d.covered_lot_ids
                    or any(
                        Decimal(r["on_hand_quantity"]) > 0
                        for r in snapshot["inventory_lots"]
                        if r["ingredient_id"] == str(d.ingredient_id)
                    )
                ):
                    block("INVENTORY_NOT_EMPTY")
                if any(
                    d.observed_at < datetime.fromisoformat(r["updated_at"])
                    for r in snapshot["inventory_lots"]
                    if r["ingredient_id"] == str(d.ingredient_id)
                ):
                    block("STALE_STOCK_OBSERVATION")
            elif isinstance(d, domains.SalesDeclaration):
                for pid in d.product_ids:
                    entity("product", pid, products)
                if d.to_date < d.from_date or d.to_date > today:
                    block("INVALID_COVERAGE_WINDOW")
                elif d.state == "COMPLETE":
                    days = (d.to_date - d.from_date).days + 1
                    if days * len(d.product_ids) > 100000:
                        block("RESOURCE_LIMIT_EXCEEDED")
                    else:
                        actual = {
                            (str(x.product_id), x.sales_date)
                            for x, _, _, _ in normalized
                            if isinstance(x, domains.SalesSource)
                        } | {
                            (r["product_id"], date.fromisoformat(r["sales_date"]))
                            for r in snapshot["sales_daily"]
                        }
                        if any(
                            (
                                str(pid),
                                date.fromordinal(d.from_date.toordinal() + offset),
                            )
                            not in actual
                            for pid in d.product_ids
                            for offset in range(days)
                        ):
                            block("SALES_COVERAGE_INCOMPLETE")
            else:
                for c in d.capacities + d.supplier_limits:
                    i = entity("ingredient", c.ingredient_id, ingredients)
                    if i and c.unit != i["base_unit"]:
                        block("UNIT_MISMATCH")
                    if isinstance(c, domains.SupplierLimit):
                        entity("supplier", c.supplier_id, suppliers)
                if d.committed_inbound_state == "PRESENT_UNSUPPORTED":
                    warn("COMMITTED_INBOUND_UNSUPPORTED")
            if getattr(d, "state", None) == "UNKNOWN":
                warn("DECLARATION_UNKNOWN")
        changes = ()
        if before:
            bd = before.model_dump(mode="json")
            ad = after.model_dump(mode="json")
            changes = tuple(
                dto.Change(
                    field=k,
                    before=str(bd[k]),
                    after=str(v),
                    delta=(
                        exact_text(Fraction(Decimal(v)) - Fraction(Decimal(bd[k])))
                        if k in {"quantity", "on_hand"}
                        else None
                    ),
                )
                for k, v in ad.items()
                if bd.get(k) != v
                and not (k in {"quantity", "on_hand"} and Decimal(bd[k]) == Decimal(v))
            )
        rid = uuid4()
        if isinstance(after, (domains.CountSource, domains.OpeningValue)):
            opening = isinstance(after, domains.OpeningValue)
            quantity = after.quantity if opening else after.on_hand
            baseline = before.quantity if opening and before else before.on_hand if before else None
            if opening and action == "NO_OP":
                current_lot = lots.get(str(after.lot_id))
                if current_lot:
                    baseline = quantity = current_lot["on_hand_quantity"]
            delta = exact_text(Fraction(quantity) - Fraction(baseline or "0"))
            inventory_effect = dto.InventoryEffect(origin="OPENING_STOCK" if opening else "IMPORT_COUNT",
                lot_id=after.lot_id, before_quantity=baseline, after_quantity=quantity, quantity_delta=delta,
                movement_type="COUNT_CORRECTION" if not blockers and delta != "0" else None,
                unit=after.unit, observed_at=after.observed_at)
        target_entities = {"supplier_term"} if value.domain == "supplier_terms" else {"lot"} if value.domain in {"inventory_count", "opening_stock"} else set()
        target = history_target or next(
            (r.canonical_id for r in refs if r.entity in target_entities),
            (
                rid
                if value.domain
                in {"supplier_terms", "payable_fees", "scope_declarations", *domains.HISTORY_MODELS}
                else None
            ),
        )
        if receipt_effect is not None:
            target=receipt_effect.receipt_id
        rows.append(
            dto.PreviewRow(
                row_id=rid,
                source_location=loc,
                classification="CONFLICT" if blockers else cls,
                proposed_action="BLOCKED" if blockers else action,
                entity_refs=tuple(refs),
                before=before,
                after=after,
                normalized_source_quantity=value.quantity if isinstance(value, domains.SalesSource) else None,
                normalized_source_stockout=source_stockout,
                stockout_update=stockout_update,
                changes=changes,
                provenance=prov,
                blockers=tuple(blockers),
                warnings=tuple(warnings),
                confirmation_required=confirm,
                target_reserved_or_existing_id=target,
                expected_version=history_version,
                supplier_term_semantics=supplier_semantics,
                inventory_effect=inventory_effect,
                receipt_effect=receipt_effect,
                required_permissions=required_permissions,
            )
        )
    for key, group in sorted(recipe_groups.items()):
        first, prov, loc, _ = group[0]
        blockers = [b for _, _, _, bs in group for b in bs]
        # Matching Product/version and headers do not establish one report grain.
        # Split-part declarations are not implemented; never combine independent
        # sheets into a complete recipe by source iteration order.
        if len({location.sheet_id for _, _, location, _ in group}) > 1:
            blockers.extend(notice("RECIPE_SOURCE_SCOPE_AMBIGUOUS", location)
                for _, _, location, _ in group)
        fields = (
            "effective_from",
            "effective_to",
            "yield_quantity",
            "yield_unit",
            "process_loss_rate",
        )
        if any(
            any(
                (
                    (Decimal(getattr(v, k)) != Decimal(getattr(first, k)))
                    if k in {"yield_quantity", "process_loss_rate"}
                    else getattr(v, k) != getattr(first, k)
                )
                for k in fields
            )
            for v, _, _, _ in group
        ):
            blockers.append(notice("RECIPE_HEADER_CONFLICT", loc))
        if len({v.ingredient_id for v, _, _, _ in group}) != len(group):
            blockers.append(notice("DUPLICATE_RECIPE_INGREDIENT", loc))
        after = domains.RecipeValue(
            product_id=first.product_id,
            version=first.version,
            effective_from=first.effective_from,
            effective_to=first.effective_to,
            yield_quantity=first.yield_quantity,
            yield_unit=first.yield_unit,
            process_loss_rate=first.process_loss_rate,
            lines=tuple(
                domains.RecipeLineValue(
                    ingredient_id=v.ingredient_id, quantity=v.quantity, unit=v.unit
                )
                for v, _, _, _ in sorted(group, key=lambda t: str(t[0].ingredient_id))
            ),
        )
        before = None
        for old in snapshot["recipes"]:
            if (
                old["product_id"] == str(first.product_id)
                and old["version"] == first.version
            ):
                oldlines = [
                    l for l in snapshot["recipe_lines"] if l["recipe_id"] == old["id"]
                ]
                candidate = domains.RecipeValue(
                    product_id=first.product_id,
                    version=old["version"],
                    effective_from=old["effective_from"],
                    effective_to=old["effective_to"],
                    yield_quantity=old["yield_quantity"],
                    yield_unit=products[str(first.product_id)]["selling_unit"],
                    process_loss_rate=old["process_loss_rate"],
                    lines=tuple(
                        domains.RecipeLineValue(
                            ingredient_id=l["ingredient_id"],
                            quantity=l["quantity"],
                            unit=l["unit"],
                        )
                        for l in sorted(oldlines, key=lambda l: l["ingredient_id"])
                    ),
                )
                if (
                    candidate.effective_from == after.effective_from
                    and candidate.effective_to == after.effective_to
                    and Decimal(candidate.yield_quantity)
                    == Decimal(after.yield_quantity)
                    and Decimal(candidate.process_loss_rate)
                    == Decimal(after.process_loss_rate)
                    and len(candidate.lines) == len(after.lines)
                    and all(
                        a.ingredient_id == b.ingredient_id
                        and a.unit == b.unit
                        and Decimal(a.quantity) == Decimal(b.quantity)
                        for a, b in zip(candidate.lines, after.lines)
                    )
                ):
                    before = candidate
                    continue
                blockers.append(notice("RECIPE_VERSION_CONFLICT", loc))
            if (
                old["product_id"] == str(first.product_id)
                and old.get("assigned", True)
                and date.fromisoformat(old["effective_from"])
                <= (first.effective_to or date.max)
                and first.effective_from
                <= (
                    date.fromisoformat(old["effective_to"])
                    if old["effective_to"]
                    else date.max
                )
            ):
                blockers.append(notice("RECIPE_PERIOD_OVERLAP", loc))
        for other, othergroup in recipe_groups.items():
            otherfirst = othergroup[0][0]
            if (
                other != key
                and other[0] == key[0]
                and otherfirst.effective_from <= (first.effective_to or date.max)
                and first.effective_from <= (otherfirst.effective_to or date.max)
            ):
                blockers.append(notice("RECIPE_PERIOD_OVERLAP", loc))
        rows.append(
            dto.PreviewRow(
                row_id=uuid4(),
                source_location=loc,
                classification=(
                    "CONFLICT" if blockers else "UNCHANGED" if before else "NEW"
                ),
                proposed_action=(
                    "BLOCKED"
                    if blockers
                    else "NO_OP" if before else "CREATE_RECIPE_VERSION"
                ),
                entity_refs=(
                    dto.EntityRef(entity="product", canonical_id=first.product_id),
                )
                + tuple(
                    dto.EntityRef(entity="ingredient", canonical_id=l.ingredient_id)
                    for l in after.lines
                ),
                before=before,
                after=after,
                provenance=prov,
                blockers=tuple(blockers),
                source_locations=tuple(x[2] for x in group),
                line_provenance=tuple(
                    dto.RecipeLineProvenance(
                        ingredient_id=value.ingredient_id, source_location=location,
                        quantity_basis=value.quantity_basis,
                        provenance={p.field: dto.ProvenanceValue(**p.model_dump(exclude={"field"})) for p in provenance},
                    )
                    for value, provenance, location, _ in group
                ),
            )
        )
    creation_rows = []
    for ident, ent in sorted(reservations.items()):
        if any(
            r.after
            and r.after.domain in {"products", "ingredients", "suppliers"}
            and any(str(ref.canonical_id) == ident for ref in r.entity_refs)
            for r in rows
        ):
            continue
        relevant = [
            r
            for r in rows
            if any(str(ref.canonical_id) == ident for ref in r.entity_refs)
        ]
        if not relevant:
            continue
        loc = relevant[0].source_location
        domain = {
            "product": "products",
            "ingredient": "ingredients",
            "supplier": "suppliers",
        }[ent.entity]
        values = ent.metadata.model_dump(mode="json")
        values[
            "source_supplier_key" if ent.entity == "supplier" else "source_business_key"
        ] = ent.source_business_key
        payload = domains.SOURCE_MODELS[domain].model_validate(values)
        old = next((r for r in snapshot[domain] if r["id"] == ident), None)
        blockers = []
        if old and any(
            not metadata_equal(k, old.get(k), v)
            for k, v in ent.metadata.model_dump(mode="json").items()
        ):
            blockers.append(notice("ENTITY_IDENTITY_CONFLICT", loc))
        if values.get("sku") and any(
            r["id"] != ident and r.get("sku") == values["sku"] for r in snapshot[domain]
        ):
            blockers.append(notice("ENTITY_IDENTITY_CONFLICT", loc))
        if values.get("sku") and any(
            e.reserved_canonical_id != ent.reserved_canonical_id
            and e.entity == ent.entity
            and getattr(e.metadata, "sku", None) == values["sku"]
            for e in reservations.values()
        ):
            blockers.append(notice("ENTITY_IDENTITY_CONFLICT", loc))
        creation = dto.PreviewRow(
            row_id=uuid4(),
            source_location=loc,
            classification="CONFLICT" if blockers else "UNCHANGED" if old else "NEW",
            proposed_action=(
                "BLOCKED"
                if blockers
                else "NO_OP" if old else "CREATE_" + ent.entity.upper()
            ),
            entity_refs=(
                dto.EntityRef(
                    entity=ent.entity, canonical_id=ent.reserved_canonical_id
                ),
            ),
            before=payload if old else None,
            after=payload,
            provenance=tuple(
                dto.FieldProvenance(
                    field=k, origin="SOURCE_EXPLICIT", value_source="IDENTITY_BINDING",
                    applied_rule_ids=("entity_proposal:" + str(ent.proposal_id),),
                )
                for k in type(ent.metadata).model_fields
            ),
            blockers=tuple(blockers),
            target_reserved_or_existing_id=ent.reserved_canonical_id,
        )
        creation_rows.append(creation)
        rows = [
            (
                r.model_copy(
                    update={"dependencies": r.dependencies + (creation.row_id,)}
                )
                if any(str(ref.canonical_id) == ident for ref in r.entity_refs)
                else r
            )
            for r in rows
        ]
    rows = creation_rows + rows
    for index, row in enumerate(rows):
        if any(str(ref.canonical_id) in reservation_conflicts for ref in row.entity_refs + row.nested_references):
            rows[index] = row.model_copy(update=dict(classification="CONFLICT", proposed_action="BLOCKED",
                blockers=row.blockers + (notice("ENTITY_METADATA_CONFLICT", row.source_location),)))
    from app.application.import_configuration_preview import finish_configurations
    from app.application.import_dependencies import finalize_dependencies
    from app.application.import_sales_groups import finish_sales
    from app.application.import_actual_receipts import finish_receipts
    rows=finish_receipts(rows,specs)
    return finalize_dependencies(finish_configurations(finish_sales(rows, specs, snapshot), specs, snapshot, normalized, now, store_timezone))
