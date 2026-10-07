"""Observed-target metrics only; no database, model, filesystem or boundary dependency."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, Context, localcontext
from uuid import UUID


@dataclass(frozen=True)
class ScoredPrediction:
    origin: date
    product_id: UUID
    horizon: int
    actual: Decimal
    quantiles: tuple[Decimal, Decimal, Decimal]
    raw_crossing: bool = False


def metric_values(points: tuple[ScoredPrediction, ...]) -> dict:
    n = len(points)
    if not n:
        return dict(sample_count=0, mae_p50=None, wape=None, pinball_p25=None,
            pinball_p50=None, pinball_p75=None, mean_pinball=None, coverage=None,
            mean_interval_width=None, raw_crossings=0, post_crossings=0)
    with localcontext(Context(prec=40)):
        abs_error = sum((abs(p.actual-p.quantiles[1]) for p in points), Decimal(0))
        actual_sum = sum((p.actual for p in points), Decimal(0))
        losses = []
        for index, q in enumerate((Decimal('.25'),Decimal('.50'),Decimal('.75'))):
            errors = tuple(p.actual-p.quantiles[index] for p in points)
            losses.append(sum((max(q*e, (q-1)*e) for e in errors), Decimal(0))/n)
        return dict(sample_count=n, mae_p50=abs_error/n,
            wape=abs_error/actual_sum if actual_sum else None,
            pinball_p25=losses[0], pinball_p50=losses[1], pinball_p75=losses[2],
            mean_pinball=sum(losses)/3,
            coverage=Decimal(sum(p.quantiles[0] <= p.actual <= p.quantiles[2] for p in points))/n,
            mean_interval_width=sum((p.quantiles[2]-p.quantiles[0] for p in points),Decimal(0))/n,
            raw_crossings=sum(p.raw_crossing for p in points),
            post_crossings=sum(not p.quantiles[0] <= p.quantiles[1] <= p.quantiles[2] for p in points))
