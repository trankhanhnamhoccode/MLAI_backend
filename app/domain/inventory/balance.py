"""Exact lot balance arithmetic. No ORM, transport, filesystem or provider."""
from decimal import Decimal, localcontext


class InvalidInventoryBalance(ValueError):
    """A supplied delta cannot produce a valid current nonnegative balance."""


def corrected_balance(current: Decimal, delta: Decimal) -> Decimal:
    if not current.is_finite() or not delta.is_finite() or current < 0 or delta == 0:
        raise InvalidInventoryBalance('Current balance must be finite/nonnegative and delta finite/nonzero')
    # NUMERIC has no fixed scale: ambient Decimal precision must not round a change.
    scale = min(current.as_tuple().exponent, delta.as_tuple().exponent)
    precision = max(current.adjusted(), delta.adjusted()) - scale + 2
    with localcontext() as context:
        context.prec = max(1, precision)
        result = current + delta
    if result < 0:
        raise InvalidInventoryBalance('Adjustment would produce a negative balance')
    return result
