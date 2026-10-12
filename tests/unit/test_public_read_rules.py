from datetime import date
from decimal import Decimal, localcontext
import pytest
from app.domain.inventory.read_rules import (
    decimal_text,
    fold_name,
    lot_status,
    ReadFactError,
)


@pytest.mark.parametrize(
    "value",
    [
        True,
        1.2,
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-1"),
    ],
)
def test_invalid_quantity(value):
    with pytest.raises(ReadFactError):
        decimal_text(value)


def test_exact_quantity_independent_context_and_money_limits():
    with localcontext() as ctx:
        ctx.prec = 2
        assert (
            decimal_text(Decimal("1000.123456789012345678901"))
            == "1000.123456789012345678901"
        )
        assert decimal_text(Decimal("-0.00"), signed=True) == "0.00"
        assert decimal_text(Decimal("1e-100")) == "0." + "0" * 99 + "1"
        assert (
            decimal_text(Decimal("999999999999999999.123456789012345678"), money=True)
            == "999999999999999999.123456789012345678"
        )
    for v in ["1e18", "1e-19"]:
        with pytest.raises(ReadFactError) as e:
            decimal_text(Decimal(v), money=True)
        assert e.value.representation
    with pytest.raises(ReadFactError):
        decimal_text(Decimal("1e-2000000"))


def test_search_and_expiry_exact_boundaries():
    assert fold_name("\u0110\u00c1 \u0111\u00e1 Su\u031b\u0303a") == "da da sua"
    today = date(2026, 10, 10)
    assert lot_status(Decimal("1"), today, today, True, today) == "near_expiry"
    assert (
        lot_status(Decimal("1"), today, date(2026, 10, 17), True, today)
        == "near_expiry"
    )
    assert lot_status(Decimal("1"), today, date(2026, 10, 18), True, today) == "stable"
    assert lot_status(Decimal("0"), today, date(2026, 10, 9), True, today) == "empty"
    assert lot_status(Decimal("1"), None, None, False, today) == "watch"


def test_extreme_date_no_addition_overflow():
    assert lot_status(Decimal("1"), date.max, date.max, True, date.max) == "near_expiry"
    assert lot_status(Decimal("1"), date.min, date.min, True, date.min) == "near_expiry"
