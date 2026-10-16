"""Validate retained equations and relationships, never execute an engine.

Journal classifications are retained execution evidence, not newly simulated
vectors. Only published candidates contain full serving rows to check by value.
No new optimality/certification assertion is produced by this reader.
"""
import math
from datetime import timedelta
from fractions import Fraction as F

from app.application.procurement_comparison_facts import q, option_token
from app.domain.decision.procurement_policy import PATH_FOR, service_summary, winner_key
from app.application.serving_validation import require, index


def validate_bom(result):
    from app.domain.demand.arithmetic import contribution_quantity, exact_quantity_sum
    prepared = result.prepared
    for issue in prepared.issues:
        raw = issue.model_dump()
        require(any(i.model_dump(include=set(raw)) == raw for i in result.issues), 'Captured BOM issue lost')
    if result.status != 'COMPLETE':
        if result.status=='DATA_BLOCKED':
            missing_recipe=any(not any(r.product_id==p.product_id and r.lines and r.effective_from<=p.forecast_date and
                (r.effective_to is None or p.forecast_date<=r.effective_to) for r in prepared.recipes) for p in prepared.forecast.predictions)
            require(missing_recipe or any(i.kind=='DATA_BLOCKER' for i in prepared.issues), 'BOM blocker has no retained input basis')
        else:
            require(any(i.kind=='DATA_BLOCKER' and i.code.startswith('BOM_NUMERIC_') for i in result.issues), 'Numeric BOM failure lacks numeric provenance')
        return  # The ordinary typed boundary still checks blocked shape/issues.
    require(not any(i.kind=='DATA_BLOCKER' for i in result.issues), 'Complete BOM contains a blocker')
    points = {(p.forecast_date, p.product_id): p for p in prepared.forecast.predictions}
    expected = set()
    groups = {}
    for path in result.paths:
        rows = index(path.demands, set(points), lambda r: (r.day, r.product_id), 'BOM path')
        for key, row in rows.items():
            source = points[key]
            require(row.unit == source.unit and row.quantity == getattr(source, {'LOW':'p25','BASE':'p50','HIGH':'p75'}[path.path_id]), 'BOM path differs from retained forecast')
            recipes = [r for r in prepared.recipes if r.product_id == row.product_id and r.effective_from <= row.day and (r.effective_to is None or row.day <= r.effective_to)]
            require(len(recipes) == 1 and bool(recipes[0].lines), 'BOM dated recipe absent/ambiguous')
            recipe = recipes[0]
            for line in recipe.lines:
                key = (path.path_id, row.day, row.product_id, recipe.id, line.ingredient_id)
                expected.add(key)
                matches = [c for c in result.contributions if (c.path_id,c.day,c.product_id,c.recipe_id,c.ingredient_id) == key]
                require(len(matches) == 1, 'BOM contribution missing/duplicate')
                c = matches[0]
                require(c.unit == line.unit and c.quantity == contribution_quantity(row.quantity, line.quantity, recipe.yield_quantity, recipe.process_loss_rate), 'BOM contribution equation mismatch')
                groups.setdefault((c.path_id,c.day,c.ingredient_id,c.unit), []).append(c.quantity)
    require(len(expected) == len(result.contributions), 'Foreign BOM contribution')
    totals = index(result.totals, set(groups), lambda r: (r.path_id,r.day,r.ingredient_id,r.unit), 'BOM total')
    for key, values in groups.items():
        require(totals[key].quantity == exact_quantity_sum(tuple(values)), 'BOM total does not conserve contributions')


def validate_candidate(request, candidate, offers):
    from app.domain.decision.procurement import outlay, basket_violations, pack_quantity
    from app.application.contracts.serving import HypotheticalArrival
    require(len(candidate.counts) == len(offers), 'Pack vector shape mismatch')
    require(all(0 <= n <= o.upper and (not n or n >= o.minimum) for o,n in zip(offers,candidate.counts)), 'Pack/MOQ bound mismatch')
    spend = outlay(offers,candidate.counts,request.policy.fee_mode,tuple((f.supplier_id,f.amount) for f in request.supplier_fees))
    require(not basket_violations(offers,candidate.counts,spend,request.budget.amount,
        tuple((c.supplier_id,c.ingredient_id,c.maximum_quantity) for c in request.supplier_limits)), 'Retained basket violates hard constraint')
    require(q(candidate.outlay) == spend and candidate.currency == request.prepared.currency, 'Candidate outlay/currency mismatch')
    basket = {b.term_id:b for b in candidate.basket}
    require(len(basket) == len(candidate.basket) == sum(n > 0 for n in candidate.counts), 'Basket coverage mismatch')
    arrivals = list(request.arrivals)
    for offer, count in zip(offers,candidate.counts):
        if not count: continue
        line = basket.get(offer.id)
        require(line is not None and (line.supplier_id,line.ingredient_id,line.unit,line.packs,q(line.quantity)) ==
            (offer.supplier,offer.ingredient,offer.unit,count,F(offer.pack)*count), 'Basket differs from captured offer/counts')
        day = request.prepared.request.cutoff_date + timedelta(days=1+offer.lead)
        arrivals.append(HypotheticalArrival(lot_id=offer.lot_id,store_id=request.prepared.request.store_id,
            ingredient_id=offer.ingredient,unit=offer.unit,arrival_day=day,
            expiry_date=None if offer.shelf is None else day+timedelta(days=offer.shelf),quantity=pack_quantity(offer.pack,count)))
    require(candidate.arrivals == tuple(sorted(arrivals,key=lambda a:a.lot_id)) == candidate.evaluation.input.arrivals, 'Candidate arrival provenance mismatch')
    require(candidate.evaluation.input.prepared == request.prepared and candidate.evaluation.status == 'COMPLETE', 'Candidate serving capture/status mismatch')
    validate_bom(candidate.evaluation.bom)
    expected = {(path,p) for path in ('LOW','BASE','HIGH') for p in request.prepared.request.product_ids}
    services = index(candidate.services,expected,lambda r:(r.path,r.product_id),'Candidate service')
    for (path,product), metric in services.items():
        rows = [r for r in candidate.evaluation.products if r.path_id == path and r.product_id == product]
        requested = sum((q(r.requested) for r in rows),F())
        served = sum((q(r.fulfilled) for r in rows),F())
        require((q(metric.requested),q(metric.served),q(metric.service) if metric.service else None) ==
            (requested,served,served/requested if requested else None), 'Service aggregation mismatch')
    for capacity in request.capacities:
        for path in ('LOW','BASE','HIGH'):
            for delta in range(1,8):
                day = request.prepared.request.cutoff_date + timedelta(days=delta)
                gross = sum((q(r.opening)+q(r.arrivals) for r in candidate.evaluation.lots if
                    (r.path_id,r.day,r.ingredient_id) == (path,day,capacity.ingredient_id)),F())
                require(gross <= F(capacity.maximum_quantity), 'Retained capacity violation')


def validate_procurement(result):
    from app.application.use_cases.procurement import captured_offers, constraint_coverage
    from app.application.use_cases.procurement_v2 import candidate_gaps, passed
    request = result.input
    require(tuple(r.strategy for r in result.strategies) == ('LEAN','BALANCED','PROTECTED'), 'Strategy coverage mismatch')
    require(result.coverage == constraint_coverage(request), 'Constraint coverage mismatch')
    offers = captured_offers(request)
    bounds = tuple(o.upper for o in offers)
    size = math.prod(n+1 for n in bounds)
    blocked = any(c.status == 'BLOCKED' for c in result.coverage)
    shared = {}
    for row in result.strategies:
        require(row.construction_path == PATH_FOR[row.strategy] and row.domain_size == size, 'Strategy domain/path mismatch')
        if blocked:
            require(not row.candidate and not row.journal and row.execution == 'BLOCKED' and not row.solver and
                not row.search_complete and row.proof == 'UNPROVEN' and not row.enumerated_vectors and
                not row.customer_pass and not row.construction_pass and not row.customer_gaps and not row.construction_gaps and
                row.customer_feasibility == row.construction_feasibility == 'UNKNOWN' and row.selection_kind == 'NONE', 'Blocked input asserts computation')
            continue
        candidate = row.candidate
        if candidate:
            validate_candidate(request,candidate,offers)
            cg,tg = candidate_gaps(request,candidate),candidate_gaps(request,candidate,row.construction_path)
            require((row.customer_gaps,row.construction_gaps,row.customer_pass,row.construction_pass) == (cg,tg,passed(cg),passed(tg)), 'Candidate requirements mismatch')
        else:
            require(not row.customer_gaps and not row.construction_gaps and not row.customer_pass and not row.construction_pass, 'Absent candidate claims service')
        kind = 'NONE' if not candidate else 'TARGET' if row.customer_pass and row.construction_pass else 'CUSTOMER_PASS_FALLBACK' if row.customer_pass else 'REFERENCE_NOT_RANKED'
        require(row.selection_kind == kind, 'Selection kind mismatch')
        require(row.search_complete == (row.proof == 'COMPLETE_EXACT_ENUMERATION'), 'Proof completeness mismatch')
        require(row.execution != 'ERROR' or bool(row.diagnostic), 'Error diagnostic absent')
        for entry in row.journal:
            require(len(entry.counts) == len(bounds) and all(0 <= n <= b for n,b in zip(entry.counts,bounds)), 'Journal vector outside finite domain')
            require((entry.hard_valid and not entry.reasons) or (not entry.hard_valid and bool(entry.reasons)), 'Journal validity/reasons inconsistent')
            require(entry.hard_valid or (not entry.customer_pass and not entry.construction_pass), 'Rejected vector claims service')
            value = (entry.hard_valid,entry.customer_pass,entry.reasons)
            require(entry.counts not in shared or shared[entry.counts] == value, 'Cross-strategy journal contradiction')
            shared[entry.counts] = value
            if candidate and entry.counts == candidate.counts:
                require((entry.hard_valid,entry.customer_pass,entry.construction_pass) == (True,row.customer_pass,row.construction_pass), 'Candidate/journal classification mismatch')
        if candidate:
            require(any(e.counts == candidate.counts for e in row.journal), 'Candidate missing journal provenance')
        customer = any(e.hard_valid and e.customer_pass for e in row.journal)
        both = any(e.hard_valid and e.customer_pass and e.construction_pass for e in row.journal)
        require(row.customer_feasibility == ('PASS_EXISTS' if customer else 'NO_PASS_CERTIFIED' if row.search_complete else 'UNKNOWN'), 'Customer feasibility mismatch')
        require(row.construction_feasibility == ('PASS_EXISTS' if both else 'NO_PASS_CERTIFIED' if row.search_complete else 'UNKNOWN'), 'Construction feasibility mismatch')
        enumerated = {e.counts for e in row.journal if e.stage == 'EXACT_ENUMERATION'}
        require(row.enumerated_vectors == len(enumerated), 'Enumeration count mismatch')
        if row.search_complete:
            require(row.execution == 'FINISHED' and len(enumerated) == size, 'Finite certificate coverage incomplete')
    statuses = {r.execution for r in result.strategies}
    expected = next((s for s in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED','INCOMPLETE') if s in statuses),'FINISHED')
    require(result.execution == expected and result.unique_exact_evaluations == len(shared), 'Execution/journal count mismatch')
    require(math.isfinite(result.elapsed_seconds) and result.elapsed_seconds >= 0 and
        result.deadline_overrun_seconds == max(0,result.elapsed_seconds-float(request.policy.computation_seconds)), 'Timing evidence mismatch')


def validate_selection(selection):
    """Check recorded eligibility and pairwise key inequalities; never run selector."""
    from app.application.use_cases.procurement_v2 import candidate_gaps, passed, stable_basket
    comparison = selection.comparison
    candidates = {option_token(comparison.source.input,r.candidate):r.candidate for r in comparison.source.strategies if r.candidate}
    eligible = []
    rejected = {}
    keys = {}
    for option in comparison.options:
        candidate = candidates[option.token]
        reasons = []
        if any(i.kind in ('DATA_BLOCKER','HARD_VIOLATION') for i in option.issues): reasons.append('RELATED_BLOCKER')
        if not passed(candidate_gaps(comparison.source.input,candidate)): reasons.append('CUSTOMER_REQUIREMENTS_NOT_MET')
        if reasons: rejected[option.token] = tuple(reasons)
        else:
            eligible.append(option.token)
            minima = tuple(service_summary((q(p.requested),q(p.fulfilled)) for p in option.products if p.path == path)[0] for path in ('HIGH','BASE','LOW'))
            keys[option.token] = winner_key(minima,q(option.outlay.total),stable_basket(candidate))
    require(len(selection.eligible_tokens) == len(set(selection.eligible_tokens)) and set(selection.eligible_tokens) == set(eligible), 'Eligibility mismatch')
    require({r.option_token:r.reasons for r in selection.rejected} == rejected and len(selection.rejected) == len(rejected), 'Rejection reasons mismatch')
    require(selection.reason == ('WINNER_FOUND' if eligible else 'NO_ELIGIBLE_CANDIDATE'), 'Winner reason mismatch')
    if not eligible:
        require(selection.winner_token is None, 'No-winner invariant violated')
    else:
        require(selection.winner_token == selection.eligible_tokens[0], 'Winner does not reference first eligible option')
        require(all(keys[a] <= keys[b] for a,b in zip(selection.eligible_tokens,selection.eligible_tokens[1:])), 'Retained selector ordering inconsistent')
