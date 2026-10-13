"""Independent procurement output consistency checks; does not rerun simulation/search."""
from datetime import timedelta
from fractions import Fraction as F
from app.domain.decision.procurement import Offer, outlay, basket_violations, requirements, pack_quantity


def q(value):
    return F(int(value.numerator),int(value.denominator))


def validate_candidate(request,candidate):
    terms={t.id:t for t in request.prepared.supplier_terms}
    offers=tuple(Offer(o.term_id,terms[o.term_id].ingredient_id,terms[o.term_id].supplier_id,terms[o.term_id].unit,
        terms[o.term_id].pack_size_base_quantity,terms[o.term_id].pack_cost,terms[o.term_id].minimum_order_packs,
        o.bound.maximum_packs,terms[o.term_id].lead_time_days,terms[o.term_id].shelf_life_days,o.arrival_lot_id,o.payable_fee)
        for o in request.offers)
    spend=outlay(offers,candidate.counts,request.policy.fee_mode,tuple((f.supplier_id,f.amount) for f in request.supplier_fees))
    errors=basket_violations(offers,candidate.counts,spend,request.budget.amount,
        tuple((c.supplier_id,c.ingredient_id,c.maximum_quantity) for c in request.supplier_limits))
    if errors or q(candidate.outlay)!=spend or candidate.currency!=request.prepared.currency:
        raise ValueError('Candidate pack/outlay/supplier/budget mismatch')
    expected=[];arrivals=list(request.arrivals)
    from app.application.contracts.serving import HypotheticalArrival
    for o,n in zip(offers,candidate.counts):
        if not n:continue
        expected.append((o.id,o.supplier,o.ingredient,o.unit,n,F(o.pack)*n))
        day=request.prepared.request.cutoff_date+timedelta(days=1+o.lead)
        arrivals.append(HypotheticalArrival(lot_id=o.lot_id,store_id=request.prepared.request.store_id,ingredient_id=o.ingredient,
            unit=o.unit,arrival_day=day,expiry_date=None if o.shelf is None else day+timedelta(days=o.shelf),quantity=pack_quantity(o.pack,n)))
    actual=[(b.term_id,b.supplier_id,b.ingredient_id,b.unit,b.packs,q(b.quantity)) for b in candidate.basket]
    if expected!=actual or tuple(sorted(arrivals,key=lambda a:a.lot_id))!=candidate.arrivals:
        raise ValueError('Candidate basket/arrival identity mismatch')
    e=candidate.evaluation
    if e.status!='COMPLETE' or e.input.prepared!=request.prepared or e.input.arrivals!=candidate.arrivals:
        raise ValueError('Candidate requires captured-input full validated serving')
    metrics=[]
    for path in ('LOW','BASE','HIGH'):
        for product in (None,*request.prepared.request.product_ids):
            rows=[r for r in e.products if r.path_id==path and (product is None or r.product_id==product)]
            requested=sum((q(r.requested) for r in rows),F(0));served=sum((q(r.fulfilled) for r in rows),F(0))
            metrics.append((path,product,requested,served,None if not requested else served/requested))
    actual=[(m.path,m.product_id,q(m.requested),q(m.served),None if m.service is None else q(m.service)) for m in candidate.services]
    if actual!=metrics:raise ValueError('Candidate service metrics mismatch')
    for c in request.capacities:
        totals={}
        for lot in e.lots:
            if lot.ingredient_id==c.ingredient_id:
                key=lot.path_id,lot.day
                totals[key]=totals.get(key,F(0))+q(lot.opening)+q(lot.arrivals)
        if any(v>F(c.maximum_quantity) for v in totals.values()):raise ValueError('Candidate violates enabled gross capacity')


def validate_result(result):
    request=result.input
    if tuple(r.rule for r in result.strategies)!=request.policy.rules:
        raise ValueError('Result must preserve all three policy construction rules')
    statuses={r.execution for r in result.strategies}
    expected=next((s for s in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED','INCOMPLETE') if s in statuses),'FINISHED')
    if result.execution!=expected:raise ValueError('Overall execution cannot hide incomplete/error strategy')
    blocked=any(c.status=='BLOCKED' for c in result.coverage)
    if (result.readiness=='BLOCKED')!=blocked:raise ValueError('Coverage/readiness mismatch')
    from app.application.use_cases.procurement import constraint_coverage
    if result.coverage!=constraint_coverage(request):raise ValueError('Constraint coverage must reflect captured input')
    if blocked and any(r.execution!='BLOCKED' for r in result.strategies):raise ValueError('Blocked input cannot execute strategies')
    size=1
    for offer in request.offers:size*=offer.bound.maximum_packs+1
    for row in result.strategies:
        if row.domain_size!=size:raise ValueError('Proof domain differs from captured finite bounds')
        if row.execution=='BLOCKED' and (row.best_target_met or row.best_available):raise ValueError('Blocked result cannot propose basket')
        for candidate in (row.best_target_met,row.best_available):
            if candidate is not None:validate_candidate(request,candidate)
        chosen=row.best_target_met or row.best_available
        if row.best_target_met is not None and row.best_available is not None:
            raise ValueError('Target-met and miss-only fallback are separate')
        targets=((None,row.rule.target),)+tuple((f.product_id,f.target) for f in row.rule.floors)
        expected_gaps=[]
        if chosen:
            for product,target in targets:
                metric=next(m for m in chosen.services if m.path==row.rule.path and m.product_id==product)
                expected_gaps.append((product,target,requirements(q(metric.served),q(metric.requested),target)))
            if row.target_met != all(g[2]==0 for g in expected_gaps):raise ValueError('Exact target status mismatch')
        actual=[(g.product_id,g.target,q(g.shortfall_quantity)) for g in row.requirement_gaps]
        if expected_gaps!=actual:raise ValueError('Exact floor/aggregate requirement gaps mismatch')
        if row.search_complete:
            seen={j.counts for j in row.journal if j.stage=='ENUMERATION'}
            if row.execution!='FINISHED' or len(seen)!=size or any(len(v)!=len(request.offers) or any(n>o.bound.maximum_packs for n,o in zip(v,request.offers)) for v in seen):
                raise ValueError('Complete enumeration needs entire finite domain classification')
            exists=any(j.stage=='ENUMERATION' and j.classification=='TARGET_MET' for j in row.journal)
            if row.target_met!=exists:raise ValueError('Enumeration target evidence contradicts outcome')
