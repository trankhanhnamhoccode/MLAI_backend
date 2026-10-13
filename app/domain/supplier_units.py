"""Exact physical unit ratios and whole-pack purchase conditions; no IO or defaults."""
from fractions import Fraction


def physical_factor(source: str, target: str) -> Fraction:
    # Discrete ingredient quantities can retain an exact count label; no alias ratio.
    if source == target and source in {"piece", "pcs", "unit", "each", "cái"}:
        return Fraction(1)
    scales = {"mg": ("mass", Fraction(1, 1000)), "g": ("mass", Fraction(1)),
        "kg": ("mass", Fraction(1000)), "ml": ("volume", Fraction(1)),
        "mL": ("volume", Fraction(1)), "l": ("volume", Fraction(1000)),
        "L": ("volume", Fraction(1000))}
    left, right = scales.get(source), scales.get(target)
    if left is None or right is None:
        raise ValueError("UNSUPPORTED_SUPPLIER_UNIT_CONVERSION")
    if left[0] != right[0]:
        raise ValueError("INCOMPATIBLE_SUPPLIER_UNIT_CONVERSION")
    return left[1] / right[1]


def pack_price(price: Fraction, pack_quantity: Fraction, denominator_quantity: Fraction) -> Fraction:
    if price < 0 or pack_quantity <= 0 or denominator_quantity <= 0:
        raise ValueError("INVALID_SUPPLIER_QUANTITY")
    return price * pack_quantity / denominator_quantity


def physical_moq_packs(quantity: Fraction, pack_quantity: Fraction) -> int:
    if quantity <= 0 or pack_quantity <= 0:
        raise ValueError("INVALID_SUPPLIER_QUANTITY")
    ratio = quantity / pack_quantity
    return -(-ratio.numerator // ratio.denominator)
