"""Exact numeric parsing and physical source fences, independent of Menu layout."""
from decimal import localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.contracts import import_mapping as dto
from app.application.import_numeric import ooxml_quantity
from app.application.import_preview import normalize, RowBlocked
from tests.unit.test_import_recipe_basis import recipe


@pytest.mark.parametrize('raw,expected', [
    ('2.5000000000000001E-2', '0.025000000000000001'),
    ('8.0000000000000002E-3', '0.0080000000000000002'),
    ('1e-100', '0.' + '0'*99 + '1'), ('1.25', '1.25'),
    ('12E+2', '1200'), ('0', '0'), ('0.000', '0'),
])
def test_exact_expansion_independent_of_decimal_context(raw, expected):
    with localcontext() as context:
        context.prec = 2
        assert ooxml_quantity(raw) == expected


@pytest.mark.parametrize('raw,code', [
    ('-0.1', 'INVALID_OOXML_NUMERIC_QUANTITY'), ('-1e-2', 'INVALID_OOXML_NUMERIC_QUANTITY'),
    ('NaN', 'INVALID_OOXML_NUMERIC_QUANTITY'), ('Infinity', 'INVALID_OOXML_NUMERIC_QUANTITY'),
    ('1,2', 'INVALID_OOXML_NUMERIC_QUANTITY'), ('20%', 'INVALID_OOXML_NUMERIC_QUANTITY'),
    ('1e999999999', 'OOXML_NUMERIC_RESOURCE_LIMIT'), ('1e-999999999', 'OOXML_NUMERIC_RESOURCE_LIMIT'),
    ('1e200', 'OOXML_NUMERIC_RESOURCE_LIMIT'), ('1e-199', 'OOXML_NUMERIC_RESOURCE_LIMIT'),
    ('1'*201, 'OOXML_NUMERIC_RESOURCE_LIMIT'),
])
def test_invalid_or_unbounded_numeric_input(raw, code):
    with pytest.raises(ValueError, match=code):
        ooxml_quantity(raw)


def normalization_case(raw, *, kind='numeric', formula=False, epoch='1900', enabled=True):
    record = recipe()
    record.update(quantity=raw, quantity_basis='PER_SERVING', yield_quantity='1')
    fields = list(record)
    spec = dto.ProfileSpec(scope=dto.ProfileScope(source_system_key='NUMERIC', report_type='RECIPES'),
        schema='recipes', structure=dto.Structure(sheet_roles=('recipes',), header_rules=tuple(fields), schema_signature='synthetic'),
        field_bindings=tuple(dto.FieldBinding(source_column_index=i, source_header=key,
            target_field='recipes.'+key, requiredness='required', ignored=False) for i,key in enumerate(fields)),
        normalizations=(dto.Normalization(rule_id='reviewed_numeric', kind='numeric_format', fields=('quantity',),
            parameter='OOXML_FINITE_DECIMAL', evidence_reference='Independent synthetic rule'),) if enabled else (),
        source_provenance=dto.SourceProvenance(declared_by=uuid4(), evidence_references=('synthetic',)))
    source = dict(excel_date_system=epoch, cells=[dict(column_index=i,
        raw=str(value) if value is not None else None,
        kind=kind if key=='quantity' else 'text', formula=formula if key=='quantity' else False)
        for i,(key,value) in enumerate(record.items())])
    return source, spec


def test_numeric_normalization_retains_raw_and_approved_rule():
    raw='2.5000000000000001E-2'
    source,spec=normalization_case(raw)
    value,provenance=normalize(source,spec)
    assert value.quantity=='0.025000000000000001'
    quantity=next(p for p in provenance if p.field=='quantity')
    assert quantity.source_value==raw and quantity.source_column_index is not None
    assert quantity.origin=='DETERMINISTIC_DERIVED'
    assert quantity.applied_rule_ids==('reviewed_numeric','recipe:per_serving_times_yield')


@pytest.mark.parametrize('extra', [dict(kind='text'),dict(formula=True),dict(epoch=None),dict(kind='error')])
def test_physical_numeric_source_required(extra):
    source,spec=normalization_case('1e-2',**extra)
    with pytest.raises(RowBlocked,match='OOXML_NUMERIC_SOURCE_REQUIRED|SOURCE_CELL_ERROR'):
        normalize(source,spec)


@pytest.mark.parametrize('raw', ['0','0e1','-1e-2'])
def test_numeric_rule_does_not_bypass_positive_recipe_quantity(raw):
    source,spec=normalization_case(raw)
    with pytest.raises(RowBlocked,match='INVALID_SOURCE_VALUE|INVALID_OOXML_NUMERIC_QUANTITY'):
        normalize(source,spec)


def test_opt_in_does_not_change_legacy_lexical_contract():
    source,spec=normalization_case('0.125',kind='text',epoch=None,enabled=False)
    assert normalize(source,spec)[0].quantity=='0.125'
    source,spec=normalization_case('1e-2',enabled=False)
    with pytest.raises(RowBlocked,match='INVALID_SOURCE_VALUE'):
        normalize(source,spec)


@pytest.mark.parametrize('fields,parameter', [(('yield_quantity',),'OOXML_FINITE_DECIMAL'),
    (('quantity','price'),'OOXML_FINITE_DECIMAL'),(('quantity',),'arbitrary')])
def test_rule_is_fixed_to_recipe_quantity(fields,parameter):
    with pytest.raises(ValidationError,match='OOXML_RECIPE_QUANTITY_SCOPE_REQUIRED'):
        dto.Normalization(rule_id='invalid',kind='numeric_format',fields=fields,parameter=parameter,evidence_reference='synthetic')
