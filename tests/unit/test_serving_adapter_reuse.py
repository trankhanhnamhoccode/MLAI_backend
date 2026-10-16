"""Differential legacy boundary checks, independent of deadline-bound search."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
from fractions import Fraction
import pytest
from pydantic import TypeAdapter,ValidationError
from app.application.contracts.common import NonnegativeDecimal
from app.application.contracts.serving import Quantity
from app.application.use_cases import serving
from app.domain.decision.quantities import checked,display,ServingNumericError


def legacy_quantity(value):
    checked(value);view=display(value)
    try:TypeAdapter(NonnegativeDecimal).validate_python(view)
    except ValidationError as error:
        if any(e['type']!='finite_number' for e in error.errors()):raise
        raise ServingNumericError('Decimal display exceeds existing contract finite-number range') from error
    return Quantity(numerator=str(value.numerator),denominator=str(value.denominator),decimal_view=view)


def outcome(function,value):
    try:return ('ok',function(value))
    except Exception as error:
        codes=tuple(e['type'] for e in error.errors()) if isinstance(error,ValidationError) else ()
        return ('error',type(error),codes)


@pytest.mark.parametrize('value',[Fraction(0),Fraction(1),Fraction(1,3),Fraction(10**300),
    Fraction(1,10**300),Fraction(-1),Fraction(10**1001),None,True,1,'1',
    Decimal('NaN'),Decimal('Infinity'),Decimal('-Infinity'),float('nan')])
def test_quantity_old_new_outputs_and_error_classes(value):
    assert outcome(serving._quantity,value)==outcome(legacy_quantity,value)


@pytest.mark.parametrize('value',[Decimal('0'),Decimal('-0'),Decimal('1.25'),'1.25',1,
    Decimal('-1'),Decimal('NaN'),Decimal('Infinity'),Decimal('-Infinity'),None,True,1.25,'bad'])
def test_static_decimal_schema_rejects_same_invalid_inputs(value):
    old=TypeAdapter(NonnegativeDecimal)
    assert outcome(serving._NONNEGATIVE_DECIMAL_ADAPTER.validate_python,value)==outcome(old.validate_python,value)


def test_reused_validator_has_no_value_cache_or_thread_decimal_context_leakage(monkeypatch):
    values=[Fraction(n,7) for n in range(40)]
    expected=[legacy_quantity(v) for v in values]
    def forbidden(*args,**kwargs):raise AssertionError('No per-call TypeAdapter construction')
    monkeypatch.setattr(serving,'TypeAdapter',forbidden)
    def call(item):
        index,value=item
        with localcontext() as context:
            context.prec=3+index%10
            return serving._quantity(value)
    with ThreadPoolExecutor(max_workers=4) as pool:actual=list(pool.map(call,enumerate(values)))
    assert actual==expected
    assert [serving._quantity(v) for v in reversed(values)]==list(reversed(expected))
