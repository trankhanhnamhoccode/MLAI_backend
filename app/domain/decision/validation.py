"""Pure S3.1 invariants, not a candidate generator, simulator or selector."""
from datetime import date, timedelta
from decimal import Context, Decimal, MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

STRATEGIES = ('LEAN', 'BALANCED', 'PROTECTED')
PATHS = ('LOW', 'BASE', 'HIGH')
POLICY_V1 = (Decimal('.95'), Decimal('.90'), Decimal('0'), Decimal('.5'), Decimal('1'))
DECIMAL_PRECISION = 50


def exact_equal(total: Decimal, *parts: Decimal) -> bool:
    """Exact conservation checks are independent of the caller's Decimal context."""
    return Fraction(total) == sum((Fraction(p) for p in parts), Fraction())


def exact_product(total: Decimal, first: Decimal, second: Decimal | int) -> bool:
    return Fraction(total) == Fraction(first) * Fraction(second)


def unique_coverage(actual: tuple, expected: set, label: str) -> None:
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError(f'{label} must have exact unique coverage')


def arrival_date(order_date: date, lead_time_days: int) -> date:
    try:
        return order_date + timedelta(days=lead_time_days)
    except (OverflowError, ValueError) as error:
        raise ValueError('Arrival date outside supported date range') from error


def service_ratio(fulfilled: Decimal, requested: Decimal) -> Decimal | None:
    """Validate a supplied metric: zero denominator is undefined, not service=1."""
    if requested == 0:
        return None
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN,
                             Emax=MAX_EMAX, Emin=MIN_EMIN)):
        return fulfilled / requested
