"""Independent exact arithmetic for retained-array audit; no model or IO dependency."""
from dataclasses import dataclass
from fractions import Fraction as F


@dataclass(frozen=True)
class Point:
    product: str
    unit: str
    origin: str
    target: str
    partition: str
    horizon: int
    actual: F
    quantiles: tuple[F,F,F]
    interval: tuple[F,F] | None = None
    raw_crossing: bool = False


def score(points:tuple[Point,...]) -> dict:
    n=len(points)
    empty=dict(task_count=0,distinct_outcomes=0,distinct_dates=0,mae=None,wape=None,bias=None,normalized_bias=None,
        pinball=None,mean_pinball=None,quantile_coverage=None,quantile_width=None,cqr_coverage=None,cqr_width=None,
        raw_crossings=0,mixed_units=False,below_p25=None,at_or_below_p50=None,above_p75=None,median_ties=0,
        lower_ties=0,upper_ties=0,final_crossings=0,absolute_error_sum=F(0),actual_sum=F(0))
    if not n:return empty
    absolute=sum((abs(p.quantiles[1]-p.actual) for p in points),F(0))
    signed=sum((p.quantiles[1]-p.actual for p in points),F(0));actual=sum((p.actual for p in points),F(0))
    losses=tuple(sum(((q if p.actual>=p.quantiles[i] else q-1)*(p.actual-p.quantiles[i]) for p in points),F(0))/n
                 for i,q in enumerate((F(1,4),F(1,2),F(3,4))))
    intervals=tuple(p for p in points if p.interval is not None)
    return dict(task_count=n,distinct_outcomes=len({(p.product,p.target) for p in points}),distinct_dates=len({p.target for p in points}),
        mae=absolute/n,wape=absolute/actual if actual else None,bias=signed/n,normalized_bias=signed/actual if actual else None,
        pinball=losses,mean_pinball=sum(losses)/3,quantile_coverage=F(sum(p.quantiles[0]<=p.actual<=p.quantiles[2] for p in points),n),
        quantile_width=sum((p.quantiles[2]-p.quantiles[0] for p in points),F(0))/n,
        cqr_coverage=F(sum(p.interval[0]<=p.actual<=p.interval[1] for p in intervals),len(intervals)) if intervals else None,
        cqr_width=sum((p.interval[1]-p.interval[0] for p in intervals),F(0))/len(intervals) if intervals else None,
        raw_crossings=sum(p.raw_crossing for p in points),mixed_units=len({p.unit for p in points})>1,
        below_p25=F(sum(p.actual<p.quantiles[0] for p in points),n),at_or_below_p50=F(sum(p.actual<=p.quantiles[1] for p in points),n),
        above_p75=F(sum(p.actual>p.quantiles[2] for p in points),n),median_ties=sum(p.actual==p.quantiles[1] for p in points),
        lower_ties=sum(p.actual==p.quantiles[0] for p in points),upper_ties=sum(p.actual==p.quantiles[2] for p in points),
        final_crossings=sum(not p.quantiles[0]<=p.quantiles[1]<=p.quantiles[2] for p in points),absolute_error_sum=absolute,actual_sum=actual)


def sensitivity(arms:dict[str,tuple[Point,...]]) -> dict:
    """Scored-array sensitivity only; official masks and selection stay untouched."""
    holdout={a:tuple(p for p in rows if p.partition=='holdout') for a,rows in arms.items()}
    b,c=score(holdout['B']),score(holdout['C'])
    net=b['absolute_error_sum']-c['absolute_error_sum']
    contributions={h:score(tuple(p for p in holdout['B'] if p.horizon==h))['absolute_error_sum']-
                     score(tuple(p for p in holdout['C'] if p.horizon==h))['absolute_error_sum'] for h in range(1,8)}
    subsets={'official_holdout':lambda p:True,'without_horizon6':lambda p:p.horizon!=6}
    subsets.update({'leave_date_'+d:lambda p,d=d:p.target!=d for d in sorted({p.target for p in holdout['B']})})
    subsets.update({'leave_origin_'+o:lambda p,o=o:p.origin!=o for o in sorted({p.origin for p in holdout['B']})})
    return dict(net_B_minus_C_absolute_error=net,horizon_contributions=contributions,
        horizon6_share_of_net=contributions[6]/net if net else None,
        subsets={name:{a:score(tuple(p for p in rows if predicate(p))) for a,rows in holdout.items()} for name,predicate in subsets.items()})
