"""Causal plain-Python features. None means unobserved; zero is an observed value."""
from datetime import date, timedelta
from decimal import Decimal, Context, localcontext

FEATURE_NAMES = ('product_code', 'horizon', 'origin_weekday', 'target_weekday',
                 'target_month', 'lag0', 'lag1', 'lag7', 'mean7', 'count7', 'mean28', 'count28')


def feature_values(history: tuple[tuple[date, Decimal], ...], origin: date,
                   horizon: int, product_code: int) -> tuple[int | Decimal | None, ...]:
    if not 1 <= horizon <= 7:
        raise ValueError('Horizon must be 1..7')
    target = origin + timedelta(days=horizon)
    known = {day: quantity for day, quantity in history if day <= origin}
    lags = tuple(known.get(origin - timedelta(days=lag)) if origin.toordinal() > lag
                 else None for lag in (0, 1, 7))
    rolling = []
    # Fixed feature arithmetic context, independent of caller Decimal precision.
    with localcontext(Context(prec=40)):
        for window in (7, 28):
            values = [quantity for day, quantity in known.items()
                      if 0 <= (origin - day).days < window]
            rolling.extend((sum(values, Decimal(0)) / len(values) if values else None, len(values)))
    return (product_code, horizon, origin.weekday(), target.weekday(), target.month, *lags, *rolling)
