"""Only reviewed Product IDs, typed values and exact per-target coverage."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.application.contracts.import_field_values import ProductValuesResolution, ImportValueRequirement
from app.application.import_product_values import validate_product_coverage, ProductValuesError


@pytest.mark.parametrize('target,value', [('products.sku',None),('products.sku','SKU-L'),
    ('products.active',True),('products.active',False)])
def test_typed_product_values(target,value):
    ident=uuid4()
    declaration=ProductValuesResolution(target_field=target,values=[dict(product_id=ident,value=value)],evidence_reference='explicit')
    validate_product_coverage(declaration,{ident})
    rule=ImportValueRequirement(version='product_field_value/1',target_field=target)
    assert 'values' not in rule.model_dump() and 'value' not in rule.model_dump()


@pytest.mark.parametrize('target,value', [('products.sku',''),('products.sku',' '),('products.sku',True),
    ('products.sku','x'*65),('products.active',None),('products.active',1),('products.active','false'),
    ('ingredients.sku',None),('products.price','100')])
def test_forbidden_product_declarations(target,value):
    with pytest.raises(ValidationError):
        ProductValuesResolution(target_field=target,values=[dict(product_id=uuid4(),value=value)],evidence_reference='explicit')


@pytest.mark.parametrize('kind,code', [('missing','PRODUCT_VALUES_MISSING'),('extra','PRODUCT_VALUES_OUT_OF_SCOPE'),
    ('duplicate','PRODUCT_VALUES_DUPLICATE_ID'),('conflicting','PRODUCT_VALUES_CONFLICT')])
def test_exact_product_coverage(kind,code):
    a,b=uuid4(),uuid4()
    values=[dict(product_id=a,value=False)]
    if kind=='extra': values.append(dict(product_id=uuid4(),value=True))
    if kind in ('duplicate','conflicting'): values.append(dict(product_id=a,value=kind=='conflicting'))
    declaration=ProductValuesResolution(target_field='products.active',values=values,evidence_reference='explicit')
    with pytest.raises(ProductValuesError,match=code):validate_product_coverage(declaration,{a,b})


def test_multiple_source_rows_for_one_resolved_product_cannot_declare_different_status():
    from app.application.import_product_values import resolved_product_ids
    from app.application.contracts.import_mapping import FieldBinding, IdentityRule
    ident=uuid4()
    bindings=[FieldBinding(source_column_index=0,source_header='source key',target_field='products.source_business_key',requiredness='required',ignored=False)]
    identities=[IdentityRule(entity='product',source_token=token,canonical_id=ident) for token in ('A','B')]
    rows=[dict(cells=[dict(column_index=0,raw=token)]) for token in ('A','B')]
    expected=resolved_product_ids(rows,bindings,identities,())
    assert expected=={ident}
    declaration=ProductValuesResolution(target_field='products.active',values=[
        dict(product_id=ident,value=True),dict(product_id=ident,value=False)],evidence_reference='Conflicting source-row decisions')
    with pytest.raises(ProductValuesError,match='PRODUCT_VALUES_CONFLICT'):
        validate_product_coverage(declaration,expected)
