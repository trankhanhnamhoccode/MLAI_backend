"""Bounded exact lexical expansion, only invoked for reviewed OOXML numeric cells."""
from decimal import Decimal
import re


def ooxml_quantity(raw: str) -> str:
    # Bound syntax and exponent before Decimal construction or fixed-point output.
    if len(raw) > 200:
        raise ValueError('OOXML_NUMERIC_RESOURCE_LIMIT')
    match = re.fullmatch(r'\+?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE]([+-]?[0-9]+))?', raw)
    if not match:
        raise ValueError('INVALID_OOXML_NUMERIC_QUANTITY')
    if match[1] is not None and abs(int(match[1])) > 200:
        raise ValueError('OOXML_NUMERIC_RESOURCE_LIMIT')
    value = Decimal(raw)  # Exact, no float and no context-dependent arithmetic.
    exponent = value.as_tuple().exponent
    digits = len(value.as_tuple().digits)
    required = digits + exponent if exponent >= 0 else max(digits, -exponent) + 2
    if required > 200:
        raise ValueError('OOXML_NUMERIC_RESOURCE_LIMIT')
    result = format(value, 'f')
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return result
