"""serving_fefo/1 exact state and one-way Decimal display boundary."""
from decimal import (Context, Decimal, MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN,
                     Underflow, Overflow, InvalidOperation, DivisionByZero, DecimalException, localcontext)
from fractions import Fraction

MAX_DIGITS = 1000


class ServingNumericError(ValueError):
    """Controlled numeric inability, never an approximate successful result."""


def checked(value: Fraction) -> Fraction:
    # Bound before decimal string conversion, including Python's int-string guard.
    if abs(value.numerator).bit_length() > MAX_DIGITS*4 or value.denominator.bit_length() > MAX_DIGITS*4:
        raise ServingNumericError('Exact rational quantity exceeds serving_fefo/1 capacity')
    if len(str(abs(value.numerator))) > MAX_DIGITS or len(str(value.denominator)) > MAX_DIGITS:
        raise ServingNumericError('Exact rational quantity exceeds serving_fefo/1 capacity')
    return value


def exact(value: Decimal) -> Fraction:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError('Serving requires finite nonnegative Decimal source values')
    if value == 0:
        return Fraction(0)
    sign, digits, exponent = value.as_tuple()
    while len(digits) > 1 and digits[-1] == 0:
        digits, exponent = digits[:-1], exponent + 1
    if len(digits) > MAX_DIGITS or abs(exponent) > MAX_DIGITS:
        raise ServingNumericError('Decimal expansion exceeds serving_fefo/1 capacity')
    return checked(Fraction(Decimal((sign, digits, exponent))))


def display(value: Fraction) -> Decimal:
    checked(value)
    context = Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN,
                      traps=[InvalidOperation, DivisionByZero, Overflow, Underflow])
    try:
        with localcontext(context):
            result = Decimal(value.numerator) / Decimal(value.denominator)
    except DecimalException as error:
        raise ServingNumericError('Quantity cannot cross the Decimal display boundary') from error
    if not result.is_finite() or (value > 0 and result == 0):
        raise ServingNumericError('Positive quantity cannot become nonfinite or zero')
    return result
