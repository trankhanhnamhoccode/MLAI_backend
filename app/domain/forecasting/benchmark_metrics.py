"""E3 mathematical metrics on paired tasks; no ORM/Pydantic/native/filesystem."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class Score:
    store: str
    product: str
    target: date
    unit: str
    actual: Decimal
    quantiles: tuple[Decimal, Decimal, Decimal]
    cqr: tuple[Decimal, Decimal] | None = None
    crossing: bool = False


def metrics(rows: tuple[Score, ...]) -> dict:
    if not rows:
        return {'task_count': 0, 'distinct_outcomes': 0, 'distinct_dates': 0,
                'mae': None, 'wape': None, 'bias': None, 'normalized_bias': None,
                'pinball': None, 'mean_pinball': None, 'quantile_coverage': None,
                'quantile_width': None, 'cqr_coverage': None, 'cqr_width': None, 'raw_crossings': 0,
                'mixed_units': False}
    with localcontext() as ctx:
        ctx.prec = 40
        n = Decimal(len(rows))
        abs_errors = sum((abs(r.quantiles[1]-r.actual) for r in rows), Decimal(0))
        signed = sum((r.quantiles[1]-r.actual for r in rows), Decimal(0))
        actual = sum((r.actual for r in rows), Decimal(0))
        losses = tuple(sum((max(q*(r.actual-r.quantiles[i]), (q-1)*(r.actual-r.quantiles[i]))
                            for r in rows), Decimal(0))/n
                       for i, q in enumerate((Decimal('.25'), Decimal('.50'), Decimal('.75'))))
        intervals = tuple(r for r in rows if r.cqr is not None)
        return {'task_count': len(rows), 'distinct_outcomes': len({(r.store,r.product,r.target) for r in rows}),
            'distinct_dates': len({r.target for r in rows}), 'mixed_units': len({r.unit for r in rows}) > 1,
            'mae': abs_errors/n, 'wape': abs_errors/actual if actual else None,
            'bias': signed/n, 'normalized_bias': signed/actual if actual else None,
            'pinball': losses, 'mean_pinball': sum(losses)/3,
            'quantile_coverage': Decimal(sum(r.quantiles[0] <= r.actual <= r.quantiles[2] for r in rows))/n,
            'quantile_width': sum((r.quantiles[2]-r.quantiles[0] for r in rows), Decimal(0))/n,
            'cqr_coverage': Decimal(sum(r.cqr[0] <= r.actual <= r.cqr[1] for r in intervals))/len(intervals) if intervals else None,
            'cqr_width': sum((r.cqr[1]-r.cqr[0] for r in intervals), Decimal(0))/len(intervals) if intervals else None,
            'raw_crossings': sum(r.crossing for r in rows)}
