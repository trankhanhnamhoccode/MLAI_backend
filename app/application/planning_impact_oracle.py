"""Independent exhaustive ranking of tiny captured domains; no native solver/proof."""
from fractions import Fraction as F
from itertools import product

from app.application.use_cases.procurement_v2 import evaluate_basket_v2


def q(value):
    return F(int(value.numerator),int(value.denominator))


def finite_oracle(request, result):
    domain=1
    for offer in request.offers: domain*=offer.bound.maximum_packs+1
    if domain>16: raise ValueError('ORACLE_DOMAIN_LIMIT')
    candidates=[]
    for counts in product(*(range(o.bound.maximum_packs+1) for o in request.offers)):
        candidate=evaluate_basket_v2(request,counts)
        if candidate is not None: candidates.append(candidate)
    def facts(c): return {(m.path,m.product_id):(q(m.requested),q(m.served)) for m in c.services}
    def customer(c):
        values=facts(c)
        return all(values[r.path,p][1]>=values[r.path,p][0]*F(next((o.target for o in r.overrides if o.product_id==p),r.minimum))
                   for r in request.requirements.paths for p in request.prepared.request.product_ids)
    eligible=[c for c in candidates if customer(c)]
    def stable(c):
        return (tuple((str(b.term_id),b.packs) for b in c.basket),
                tuple((str(a.lot_id),a.arrival_day,str(a.expiry_date),F(a.quantity)) for a in c.arrivals))
    for strategy in result.strategies:
        path=strategy.construction_path
        target=[c for c in eligible if all(v>=r for (p,_),(r,v) in facts(c).items() if p==path)]
        def fallback(c):
            ratios=[v/r for (p,_),(r,v) in facts(c).items() if p==path and r]
            return (-min(ratios),-sum(ratios)/len(ratios),q(c.outlay),stable(c)) if ratios else (0,0,q(c.outlay),stable(c))
        chosen=min(target,key=lambda c:(q(c.outlay),stable(c))) if target else min(eligible,key=fallback) if eligible else None
        if chosen is None:
            if strategy.customer_pass: raise ValueError('ORACLE_FALSE_CUSTOMER_PASS')
        elif strategy.candidate is None or strategy.candidate.counts!=chosen.counts:
            raise ValueError('ORACLE_RANKING_MISMATCH')
    return dict(status='FINITE_ORACLE_VERIFIED',vectors=domain,hard_valid=len(candidates),
                customer_pass=len(eligible),scope='CAPTURED_FINITE_DOMAIN_ONLY',native_proof=False)
