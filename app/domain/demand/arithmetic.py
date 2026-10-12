"""dated_bom/1 arithmetic: rational contribution, exact exported-quantity sums."""
from datetime import date
from decimal import (
    Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN,
    Overflow, ROUND_HALF_EVEN, Underflow, localcontext,
)
from fractions import Fraction
from uuid import UUID

PRECISION = 50
MAX_WORK_DIGITS = 10_000  # Technical capacity, never a business quantity threshold.


class BOMArithmeticError(ValueError):
    def __init__(self, code: str, message: str, *, path_id: str | None = None,
                 product_id: UUID | None = None, day: date | None = None,
                 ingredient_id: UUID | None = None) -> None:
        self.code, self.path_id, self.product_id = code, path_id, product_id
        self.day, self.ingredient_id = day, ingredient_id
        super().__init__(message)


def _context(precision: int) -> Context:
    context = Context(prec=precision, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)
    context.traps[Underflow] = True
    return context


def _parts(value: Decimal) -> tuple[int, int]:
    """Coefficient and power separately; never expand a huge quantity exponent."""
    digits = list(value.as_tuple().digits)
    exponent = value.as_tuple().exponent
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if len(digits) > MAX_WORK_DIGITS:
        raise BOMArithmeticError('BOM_NUMERIC_CAPACITY', 'Source significant coefficient exceeds BOM capacity')
    return int(Decimal((0, tuple(digits), 0))), exponent


def _divide_scaled(coefficient: Fraction, exponent: int) -> Decimal:
    n_digits = Decimal(coefficient.numerator).as_tuple().digits
    d_digits = Decimal(coefficient.denominator).as_tuple().digits
    # Distribute the power between exact operands so neither constructor overflows
    # merely because an intermediate numerator has more digits than the final ratio.
    n_upper, d_upper = MAX_EMAX-len(n_digits)+1, MAX_EMAX-len(d_digits)+1
    n_exp = min(max(exponent, MIN_EMIN), n_upper)
    d_exp = n_exp-exponent
    if not MIN_EMIN <= d_exp <= d_upper:
        d_exp = min(max(d_exp, MIN_EMIN), d_upper)
        n_exp = exponent+d_exp
    if not MIN_EMIN <= n_exp <= n_upper:
        code = 'BOM_NUMERIC_OVERFLOW' if exponent > 0 else 'BOM_NUMERIC_UNDERFLOW'
        raise BOMArithmeticError(code, 'Quantity outside supported Decimal exponent range')
    try:
        numerator = Decimal((0, n_digits, n_exp))
        denominator = Decimal((0, d_digits, d_exp))
        with localcontext(_context(PRECISION)):
            result = numerator / denominator  # The single contribution rounding boundary.
    except Overflow as error:
        raise BOMArithmeticError('BOM_NUMERIC_OVERFLOW', 'Contribution exceeds Decimal exponent range') from error
    except Underflow as error:
        raise BOMArithmeticError('BOM_NUMERIC_UNDERFLOW', 'Contribution would lose precision by underflow') from error
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise BOMArithmeticError('BOM_NUMERIC_INVALID', 'Contribution cannot be represented as finite Decimal') from error
    if not result.is_finite() or result <= 0:
        raise BOMArithmeticError('BOM_NUMERIC_INVALID', 'Positive contribution cannot become nonfinite or zero')
    return result


def contribution_quantity(demand: Decimal, line: Decimal, yield_quantity: Decimal,
                          loss: Decimal) -> Decimal:
    values = (demand, line, yield_quantity, loss)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        raise ValueError('BOM requires finite Decimal values')
    if demand < 0 or line <= 0 or yield_quantity <= 0 or not 0 <= loss < 1:
        raise ValueError('Invalid BOM demand/yield/line/loss')
    if demand == 0:
        return Decimal(0)
    q, qe = _parts(demand)
    l, le = _parts(line)
    y, ye = _parts(yield_quantity)
    if loss == 0:
        remaining = Fraction(1)
    else:
        c, e = _parts(loss)
        if -e > MAX_WORK_DIGITS:
            raise BOMArithmeticError('BOM_NUMERIC_CAPACITY', 'Loss scale exceeds exact rational BOM capacity')
        remaining = 1-Fraction(c, 10**(-e))
    coefficient = Fraction(q*l, y)/remaining
    return _divide_scaled(coefficient, qe+le-ye)


def exact_quantity_sum(values: tuple[Decimal, ...]) -> Decimal:
    """Conserve exported Decimal contributions, with no second precision50 cap."""
    if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in values):
        raise ValueError('BOM totals require finite nonnegative Decimal contributions')
    nonzero = tuple(v for v in values if v != 0)
    if not nonzero:
        return Decimal(0)
    needed = (max(v.adjusted() for v in nonzero)-min(v.as_tuple().exponent for v in nonzero)
              +1+len(str(len(nonzero)))+1)
    precision = max(PRECISION, needed)
    if precision > MAX_WORK_DIGITS:
        raise BOMArithmeticError('BOM_NUMERIC_CAPACITY', 'Exact aggregate digit span exceeds BOM capacity')
    context = _context(precision)
    context.traps[Inexact] = True
    try:
        with localcontext(context):
            result = sum(nonzero, Decimal(0))
    except Overflow as error:
        raise BOMArithmeticError('BOM_NUMERIC_OVERFLOW', 'Aggregate exceeds Decimal exponent range') from error
    except (Underflow, Inexact, InvalidOperation) as error:
        raise BOMArithmeticError('BOM_NUMERIC_INVALID', 'Aggregate cannot preserve exact contributions') from error
    if not result.is_finite() or result <= 0:
        raise BOMArithmeticError('BOM_NUMERIC_INVALID', 'Positive aggregate cannot become nonfinite or zero')
    return result
