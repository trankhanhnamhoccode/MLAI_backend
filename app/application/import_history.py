"""Deterministic record-only preview and exact source-unit normalization."""
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from app.application.contracts.import_history import HISTORY_MODELS, PurchaseHistorySource


def normalize_history(values, spec, provenance):
    from app.application.import_preview import RowBlocked, exact_text, derived_provenance
    from app.domain.supplier_units import physical_factor
    value = HISTORY_MODELS[spec.schema].model_validate(values)
    if not hasattr(value, 'unit'):
        return value, tuple(provenance)
    rules = [c for c in spec.conversions if c.from_unit == value.unit]
    if len(rules) > 1:
        raise RowBlocked('AMBIGUOUS_CONVERSION')
    unit = rules[0].to_unit if rules else value.unit

    def scale(source_unit):
        matches = [c for c in spec.conversions if c.from_unit == source_unit]
        if len(matches) > 1:
            raise RowBlocked('AMBIGUOUS_CONVERSION')
        if source_unit == unit and not matches:
            return Fraction(1), ()
        if not matches:
            raise RowBlocked('HISTORY_UNIT_CONVERSION_REQUIRED')
        c = matches[0]
        try:
            expected = physical_factor(source_unit, unit)
        except ValueError as error:
            raise RowBlocked(str(error).replace('SUPPLIER','HISTORY')) from None
        factor = Fraction(Decimal(c.factor.numerator)) / Fraction(Decimal(c.factor.denominator))
        if c.to_unit != unit or factor != expected:
            raise RowBlocked('INVALID_HISTORY_UNIT_FACTOR')
        return factor, ('conversion:' + c.evidence_reference,)

    def replace(field, result, ids):
        original = derived_provenance(provenance, field, ids)
        provenance[:] = [p for p in provenance if p.field != field] + [original]
        values[field] = result

    factor, ids = scale(value.unit)
    if ids:
        replace('quantity', exact_text(Fraction(Decimal(value.quantity)) * factor), ids)
        replace('unit', unit, ids)
    if isinstance(value, PurchaseHistorySource) and value.price_basis == 'PER_QUANTITY':
        price_factor, price_ids = scale(value.price_unit)
        if price_ids:
            replace('price_quantity', exact_text(Fraction(Decimal(value.price_quantity)) * price_factor), price_ids)
            replace('price_unit', unit, price_ids)
    for field in ('quantity', 'price', 'price_quantity'):
        if values.get(field) is not None:
            canonical = exact_text(Fraction(Decimal(values[field])))
            if canonical != values[field]:
                replace(field, canonical, ('history:canonical_decimal',))
    return HISTORY_MODELS[spec.schema].model_validate(values), tuple(provenance)


def latest_record(records, value, scope):
    matches = [r for r in records if r['domain'] == value.domain
        and r['source_system_key'] == scope.source_system_key
        and r['report_type'] == scope.report_type
        and r['source_record_key'] == value.source_record_key]
    return max(matches, key=lambda r: r['version'], default=None)


def history_identity(value):
    """Immutable identity differs per domain; never aggregate quantities across rows."""
    fields = {
        'calendar_events': (),
        'promotion_observations': ('product_id', 'sales_date'),
        'usage_history': ('ingredient_id', 'usage_date'),
        'purchase_history': ('ingredient_id', 'supplier_id'),
    }[value.domain]
    return tuple(getattr(value, f) for f in fields)


def preview_history(value, spec, snapshot, normalized, today, now, entity, block, warn,
                    ingredients, products, suppliers):
    if hasattr(value, 'ingredient_id'):
        ingredient = entity('ingredient', value.ingredient_id, ingredients)
        if ingredient and value.unit != ingredient['base_unit']:
            block('UNIT_MISMATCH')
    if hasattr(value, 'product_id'):
        entity('product', value.product_id, products)
    if getattr(value, 'supplier_id', None) is not None:
        entity('supplier', value.supplier_id, suppliers)
    if value.domain == 'calendar_events':
        if value.declared_at > now:
            block('FUTURE_DECLARATION_NOT_KNOWN')
        warn('CALENDAR_NOT_FORECAST_FEATURE')
    else:
        dates = ('sales_date', 'usage_date', 'order_date', 'received_date', 'report_date')
        if any(getattr(value, f, None) and getattr(value, f) > today for f in dates):
            block('FUTURE_HISTORY_NOT_OBSERVED')
        timestamp = getattr(value, 'observed_at', None)
        if timestamp and timestamp > now:
            block('FUTURE_HISTORY_NOT_OBSERVED')
    if isinstance(value, PurchaseHistorySource):
        if value.currency != snapshot['stores'][0]['currency']:
            block('CURRENCY_MISMATCH')
        if value.price_basis == 'PER_QUANTITY' and value.price_unit != value.unit:
            block('PRICE_UNIT_MISMATCH')
        if any(d and d > value.report_date for d in (value.order_date, value.received_date)):
            block('HISTORY_AFTER_REPORT_DATE')
    for other, _, _, other_spec in normalized:
        if other is value or other.domain != value.domain:
            continue
        if (other_spec.scope.source_system_key, other_spec.scope.report_type, other.source_record_key) == (
            spec.scope.source_system_key, spec.scope.report_type, value.source_record_key):
            block('DUPLICATE_HISTORY_IDENTITY' if other == value else 'CONFLICTING_HISTORY_IDENTITY')
    old = latest_record(snapshot.get('import_history_records', ()), value, spec.scope)
    before = HISTORY_MODELS[value.domain].model_validate(old['payload']) if old else None
    if before and history_identity(before) != history_identity(value):
        block('SOURCE_IDENTITY_CONFLICT')
    warn('RECORDED_HISTORY_ONLY')
    if before == value:
        return before, 'UNCHANGED', 'NO_OP', False, UUID(old['id'])
    if before:
        return before, 'CHANGED', 'CORRECT_HISTORY_RECORD', True, None
    return None, 'NEW', 'CREATE_HISTORY_RECORD', False, None
