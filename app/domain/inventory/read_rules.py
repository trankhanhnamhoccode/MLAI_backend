"""Exact read rules. No HTTP, ORM, Pydantic, IO or inventory mutation."""

from datetime import date
from decimal import Decimal
import unicodedata

MAX_RESPONSE_BYTES = 1024 * 1024


class ReadFactError(ValueError):
    def __init__(self, representation=False):
        self.representation = representation
        super().__init__("Unavailable canonical projection")


def fold_name(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", value.replace("Đ", "D").replace("đ", "d"))
        if not unicodedata.combining(c)
    ).lower()


def decimal_text(
    value: Decimal, *, positive: bool = False, signed: bool = False, money: bool = False
) -> str:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or (not signed and value < 0)
        or (positive and value <= 0)
    ):
        raise ReadFactError()
    digits = len(value.as_tuple().digits)
    exponent = value.as_tuple().exponent
    if max(digits + max(exponent, 0), -exponent) + 3 > MAX_RESPONSE_BYTES:
        raise ReadFactError(True)
    text = format(value, "f")
    if value == 0 and text.startswith("-"):
        text = text[1:]
    integer, _, fraction = text.lstrip("-").partition(".")
    if money and (len(integer) > 18 or len(fraction) > 18):
        raise ReadFactError(True)
    return text


def lot_eligible(
    quantity: Decimal,
    received: date | None,
    expiry: date | None,
    tracked: bool,
    today: date,
) -> bool:
    return (
        quantity > 0
        and (received is None or received <= today)
        and (expiry is None and not tracked or expiry is not None and expiry >= today)
    )


def lot_status(
    quantity: Decimal,
    received: date | None,
    expiry: date | None,
    tracked: bool,
    today: date,
) -> str:
    if quantity == 0:
        return "empty"
    if expiry is not None and expiry < today:
        return "expired"
    if (
        lot_eligible(quantity, received, expiry, tracked, today)
        and expiry is not None
        and 0 <= (expiry - today).days <= 7
    ):
        return "near_expiry"
    if received is None or received > today or expiry is None:
        return "watch"
    return "stable"
