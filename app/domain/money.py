"""Exact monetary bounds; separate from unbounded exact quantity computation."""
from decimal import Decimal


def within_money_bounds(value: Decimal) -> bool:
    if not value.is_finite() or value < 0:
        return False
    digits, exponent = value.as_tuple().digits, value.as_tuple().exponent
    if value == 0:
        return True
    # Ignore trailing zero scale without Decimal.normalize (context can round).
    trailing = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing += 1
    return max(len(digits) + exponent, 1) <= 18 and max(-exponent - trailing, 0) <= 18
