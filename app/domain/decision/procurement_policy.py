"""procurement/2 exact Product policy. No boundary/ORM/solver dependencies."""
from fractions import Fraction as F

PATH_FOR = {'LEAN': 'LOW', 'BALANCED': 'BASE', 'PROTECTED': 'HIGH'}


def service_summary(values):
    """(minimum, equal-weight mean); omit zero-demand, never invent service=1."""
    ratios = [served / requested for requested, served in values if requested]
    return (min(ratios), sum(ratios, F(0)) / len(ratios)) if ratios else (None, None)


def shortfall(requested, served, target):
    return max(F(0), requested * target - served)


def fallback_key(summary, spend, stable):
    minimum, mean = summary
    return (-(minimum or F(0)), -(mean or F(0)), spend, stable)


def winner_key(minima, spend, stable):
    # Every candidate has identical captured requested scope: empty paths neutral.
    return (spend, *( -(v or F(0)) for v in minima), stable)
