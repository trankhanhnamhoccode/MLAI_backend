"""Explicit batch-only unknown SKU, never a missing-field default."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.application.contracts.import_field_values import (
    SharedValueResolution, ImportValueRequirement, allowed_scopes,
)
from app.application.import_descriptors import options
from app.application.import_preview import normalize, RowBlocked
from tests.unit.test_import_field_values import declared, spec, row


def test_unknown_sku_is_required_nullable_and_batch_only_with_provenance():
    option = next(o for o in options('products') if o.key == 'products.sku')
    assert option.requiredness == 'required' and option.nullable
    assert option.allowed_shared_scopes == ('IMPORT_VALUE',)
    assert allowed_scopes('ingredients.sku') == ()
    s = spec('products', ('source_business_key','name','selling_unit','price','active'),
        (ImportValueRequirement(target_field='products.sku'),))
    declaration = declared('products.sku', None)
    facts, provenance = normalize(row('P','Explicit item','cup','10000','false'),s,(declaration,))
    assert facts.sku is None and facts.active is False
    p = next(p for p in provenance if p.field == 'sku')
    assert p.value_source == 'IMPORT_VALUE' and p.source_value is None
    assert p.declaration_id == declaration.declaration_id
    assert 'value' not in s.shared_field_bindings[0].model_dump()
    with pytest.raises(RowBlocked,match='MISSING_IMPORT_VALUE'):
        normalize(row('P','Explicit item','cup','10000','false'),s)


@pytest.mark.parametrize('scope,value', [
    ('PROFILE_CONSTANT',None), ('IMPORT_VALUE',''), ('IMPORT_VALUE',' '),
    ('IMPORT_VALUE','KNOWN-SKU'), ('IMPORT_VALUE',False), ('IMPORT_VALUE',0),
])
def test_sku_shared_declaration_is_only_explicit_unknown(scope,value):
    with pytest.raises(ValidationError):
        SharedValueResolution(target_field='products.sku',scope=scope,value=value,
            evidence_reference='Explicit scoped decision')


def test_missing_declaration_value_cannot_become_null():
    with pytest.raises(ValidationError):
        SharedValueResolution(target_field='products.sku',scope='IMPORT_VALUE',
            evidence_reference='Missing value is not explicit unknown')
