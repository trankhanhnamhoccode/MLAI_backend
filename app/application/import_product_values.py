"""Product-ID declaration scope, independent of persistence and matching policy."""
from uuid import UUID
from collections.abc import Sequence
from app.application.contracts.import_mapping import FieldBinding, IdentityRule, EntityReservation
from app.application.contracts.import_field_values import ProductImportValue, ProductValuesResolution


class ProductValuesError(ValueError):
    pass


def resolved_product_ids(rows: Sequence[dict], bindings: Sequence[FieldBinding],
        identities: Sequence[IdentityRule], reservations: Sequence[EntityReservation]) -> set[UUID]:
    column = next((b.source_column_index for b in bindings
        if not b.ignored and b.target_field == 'products.source_business_key'), None)
    if column is None:
        raise ProductValuesError('PRODUCT_IDENTITY_UNRESOLVED')
    links = {}
    for rule in identities:
        if rule.entity == 'product':
            links.setdefault(rule.source_token, set()).add(rule.canonical_id)
    for entity in reservations:
        if entity.entity == 'product':
            links.setdefault(entity.source_business_key, set()).add(entity.reserved_canonical_id)
    result = set()
    for row in rows:
        token = next((c['raw'] for c in row['cells'] if c['column_index'] == column), None)
        candidates = links.get(token, set())
        if len(candidates) != 1:
            raise ProductValuesError('PRODUCT_IDENTITY_UNRESOLVED')
        result.update(candidates)
    if not result:
        raise ProductValuesError('PRODUCT_IDENTITY_UNRESOLVED')
    return result


def validate_product_coverage(declaration: ProductImportValue | ProductValuesResolution,
        expected: set[UUID]) -> None:
    seen = {}
    for item in declaration.values:
        if item.product_id in seen:
            raise ProductValuesError('PRODUCT_VALUES_DUPLICATE_ID' if seen[item.product_id] == item.value
                else 'PRODUCT_VALUES_CONFLICT')
        seen[item.product_id] = item.value
    if set(seen) - expected:
        raise ProductValuesError('PRODUCT_VALUES_OUT_OF_SCOPE')
    if expected - set(seen):
        raise ProductValuesError('PRODUCT_VALUES_MISSING')


def value_for_product(declaration: ProductImportValue, product_id: str | UUID) -> str | bool | None:
    matches = [item for item in declaration.values if item.product_id == UUID(str(product_id))]
    if not matches:
        raise ProductValuesError('PRODUCT_VALUES_MISSING')
    if len(matches) != 1:
        raise ProductValuesError('PRODUCT_VALUES_CONFLICT' if len({item.value for item in matches}) > 1
            else 'PRODUCT_VALUES_DUPLICATE_ID')
    return matches[0].value
