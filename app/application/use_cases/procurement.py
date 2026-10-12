"""Internal snapshot-only procurement orchestration; no database/provider/filesystem."""
from datetime import timedelta
from fractions import Fraction as F
import math
import time
from typing import Callable

from app.application.contracts.procurement import (
    ProcurementInput, ProcurementResult, ProcurementCandidate, StrategyProcurementResult,
    BasketLine, ServiceMetric, RequirementGap, CandidateClassification, ConstraintCoverage,
)
from app.application.contracts.serving import ServingSimulationInput, ServingSimulationResult, HypotheticalArrival
from app.application.procurement_solver import CandidateSearch, NumericUnsupported
from app.application.use_cases.serving import simulate_serving, _quantity
from app.domain.decision.procurement import (
    Offer, pack_quantity, outlay, basket_violations, requirements, vectors,
)
from app.domain.decision.quantities import exact, ServingNumericError


def rational(value):
    return F(int(value.numerator),int(value.denominator))


def captured_offers(request: ProcurementInput) -> tuple[Offer, ...]:
    terms={t.id:t for t in request.prepared.supplier_terms}
    return tuple(Offer(o.term_id,terms[o.term_id].ingredient_id,terms[o.term_id].supplier_id,
        terms[o.term_id].unit,terms[o.term_id].pack_size_base_quantity,terms[o.term_id].pack_cost,
        terms[o.term_id].minimum_order_packs,o.bound.maximum_packs,terms[o.term_id].lead_time_days,
        terms[o.term_id].shelf_life_days,o.arrival_lot_id,o.payable_fee) for o in request.offers)


def constraint_coverage(request: ProcurementInput) -> tuple[ConstraintCoverage, ...]:
    p=request.prepared
    rows=[]
    def record(name,status,detail):
        rows.append(ConstraintCoverage(constraint=name,status=status,detail=detail))
    record('budget', 'BLOCKED' if request.budget.state=='UNKNOWN' else
           'ENFORCED' if request.budget.state=='KNOWN' else 'EXPLICIT_UNCONSTRAINED',request.budget.provenance)
    mode=request.policy.fee_mode
    fees={f.supplier_id:f.amount for f in request.supplier_fees}
    offers=captured_offers(request)
    missing=(mode=='PER_OFFER' and any(o.fee is None for o in offers)) or (
        mode=='PER_SUPPLIER_ORDER' and any(fees.get(o.supplier) is None for o in offers))
    record('payable_fees','BLOCKED' if missing else 'ENFORCED',f'Explicit {mode}; unknown is not zero')
    record('capacity','ENFORCED' if request.capacities else 'NOT_CONFIGURED','Exact-unit gross post-receipt/pre-expiry/pre-consumption')
    record('supplier_limits','ENFORCED' if request.supplier_limits else 'NOT_CONFIGURED','One-order supplier/Ingredient quantity limits; splitting supported')
    record('offer_bounds','ENFORCED','Captured finite domain only; technical limits are not supplier limits')
    safety=any(c.kind=='MIN_SAFETY_STOCK' for c in p.constraints)
    record('MIN_SAFETY_STOCK','BLOCKED' if safety else 'NOT_CONFIGURED','Configured safety semantics unsupported')
    if request.unsupported_configured_constraints:
        record('other_configured_constraints','BLOCKED',', '.join(request.unsupported_configured_constraints))
    blockers=[i.code for i in p.issues if i.kind in ('DATA_BLOCKER','HARD_VIOLATION')]
    if blockers:record('captured_issues','BLOCKED',', '.join(blockers))
    if any(o.lead>6 for o in offers):
        record('arrival_window','BLOCKED','Selected offer admission requires arrival within D+1..D+7')
    ingredients={i.ingredient_id:i for i in p.ingredients}
    if any(ingredients[o.ingredient].expiry_tracking and o.shelf is None for o in offers):
        record('purchase_expiry','BLOCKED','Tracked Ingredient needs captured shelf life; none is not invented')
    if any(ingredients[a.ingredient_id].expiry_tracking and a.expiry_date is None for a in request.arrivals):
        record('explicit_arrival_expiry','BLOCKED','Tracked arrival missing expiry')
    return tuple(rows)


def _evaluate(request, offers, counts, *, product_service_only=False):
    if len(counts)!=len(offers) or any(type(n) is not int or n<0 for n in counts):
        return None,('PACK_VECTOR_SHAPE',)
    fees=tuple((f.supplier_id,f.amount) for f in request.supplier_fees)
    if any(n>o.upper or (n and n<o.minimum) for o,n in zip(offers,counts)):
        return None,('PACK_MOQ_BOUNDS',)
    spend=outlay(offers,counts,request.policy.fee_mode,fees)
    limits=tuple((c.supplier_id,c.ingredient_id,c.maximum_quantity) for c in request.supplier_limits)
    errors=basket_violations(offers,counts,spend,request.budget.amount,limits)
    if errors:return None,errors
    arrivals=list(request.arrivals);basket=[]
    for o,n in zip(offers,counts):
        if not n:continue
        day=request.prepared.request.cutoff_date+timedelta(days=1+o.lead)
        arrivals.append(HypotheticalArrival(lot_id=o.lot_id,store_id=request.prepared.request.store_id,
            ingredient_id=o.ingredient,unit=o.unit,arrival_day=day,
            expiry_date=None if o.shelf is None else day+timedelta(days=o.shelf),quantity=pack_quantity(o.pack,n)))
        basket.append(BasketLine(term_id=o.id,supplier_id=o.supplier,ingredient_id=o.ingredient,
            unit=o.unit,packs=n,quantity=_quantity(exact(o.pack)*n)))
    evaluation=simulate_serving(ServingSimulationInput(prepared=request.prepared,arrivals=tuple(arrivals)))
    # Independent output validation via a fresh by-value reconstruction is mandatory.
    evaluation=ServingSimulationResult.model_validate(evaluation.model_dump())
    if evaluation.status=='ARITHMETIC_BLOCKED':raise NumericUnsupported('CANONICAL_SERVING_NUMERIC_BOUNDARY')
    if evaluation.status!='COMPLETE':raise ValueError('Unexpected captured blocker after admission')
    for capacity in request.capacities:
        for path in ('LOW','BASE','HIGH'):
            for delta in range(1,8):
                day=request.prepared.request.cutoff_date+timedelta(days=delta)
                gross=sum((rational(r.opening)+rational(r.arrivals) for r in evaluation.lots
                    if r.path_id==path and r.day==day and r.ingredient_id==capacity.ingredient_id),F(0))
                if gross>exact(capacity.maximum_quantity):return None,('CAPACITY',)
    services=[]
    for path in ('LOW','BASE','HIGH'):
        for product in (request.prepared.request.product_ids if product_service_only else
                        (None,*request.prepared.request.product_ids)):
            rows=[r for r in evaluation.products if r.path_id==path and (product is None or r.product_id==product)]
            requested=sum((rational(r.requested) for r in rows),F(0))
            served=sum((rational(r.fulfilled) for r in rows),F(0))
            services.append(ServiceMetric(path=path,product_id=product,requested=_quantity(requested),
                served=_quantity(served),service=None if not requested else _quantity(served/requested)))
    candidate=ProcurementCandidate(counts=counts,basket=tuple(basket),arrivals=evaluation.input.arrivals,
        outlay=_quantity(spend),currency=request.prepared.currency,hard_validity='EXACT_VALIDATED',
        evaluation=evaluation,services=tuple(services))
    return candidate,()


def evaluate_procurement_basket(request: ProcurementInput, counts: tuple[int, ...]) -> ProcurementCandidate | None:
    """Public internal fixed-basket boundary. Revalidates even model_copy/construct input."""
    request=ProcurementInput.model_validate(request)
    if any(c.status=='BLOCKED' for c in constraint_coverage(request)):
        raise ValueError('Procurement input is blocked')
    return _evaluate(request,captured_offers(request),counts)[0]


def gaps(candidate, rule):
    targets=((None,rule.target),)+tuple((f.product_id,f.target) for f in rule.floors)
    return tuple(RequirementGap(product_id=product,target=target,
        shortfall_quantity=_quantity(requirements(rational(metric.served),rational(metric.requested),target)))
        for product,target in targets
        for metric in candidate.services if metric.path==rule.path and metric.product_id==product)


def passing(candidate,rule):
    return all(rational(g.shortfall_quantity)==0 for g in gaps(candidate,rule))


def _key(candidate,rule,primary):
    vector=candidate.counts
    spend=rational(candidate.outlay)
    if primary:return spend,vector
    served=next(rational(m.served) for m in candidate.services if m.path==rule.path and m.product_id is None)
    return -served,spend,vector


def execute_procurement(request: ProcurementInput,
                        search_factory: Callable[[ProcurementInput, tuple[Offer, ...]], CandidateSearch]) -> ProcurementResult:
    started=time.perf_counter()
    request=ProcurementInput.model_validate(request)
    seconds=float(request.policy.computation_seconds)
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('Unsupported deadline range')
    deadline=started+seconds
    offers=captured_offers(request); coverage=constraint_coverage(request)
    blocked=any(c.status=='BLOCKED' for c in coverage)
    size=math.prod(o.upper+1 for o in offers)
    cache={}; results=[]
    for index,rule in enumerate(request.policy.rules):
        # Equal share of remaining time for remaining strategies; unused time carries forward.
        now=time.perf_counter(); local=now+max(0,deadline-now)/(3-index)
        journal=[]; excluded=set(); excluded_fallback=set(); solver=[]; best=None; available=None
        complete=False; scanned=0; diagnostic=None
        execution='BLOCKED' if blocked else 'INCOMPLETE'; reason='INPUT_BLOCKED' if blocked else 'DEADLINE'

        def check(counts,stage):
            nonlocal best,available
            if counts not in cache:
                if time.perf_counter()>=local:return None
                cache[counts]=_evaluate(request,offers,counts)
            candidate,errors=cache[counts]
            is_pass=candidate is not None and passing(candidate,rule)
            journal.append(CandidateClassification(counts=counts,stage=stage,
                classification='HARD_REJECTED' if candidate is None else 'TARGET_MET' if is_pass else 'HARD_VALID_TARGET_MISS',reasons=errors))
            # Classification is recorded before cut/search, also when using cached evaluation.
            if candidate:
                if is_pass and (best is None or _key(candidate,rule,True)<_key(best,rule,True)):best=candidate
                if available is None or _key(candidate,rule,False)<_key(available,rule,False):available=candidate
            return candidate,errors

        try:
            if not blocked:
                check(tuple(0 for _ in offers),'ZERO_BASELINE')
                if time.perf_counter()<local:
                    search=search_factory(request,offers)
                    reserve=float(request.policy.validation_reserve_seconds)
                    phase='TARGET'
                    for iteration in range(request.policy.max_solves_per_strategy):
                        if time.perf_counter()>=local-reserve:reason='DEADLINE_SEARCH';break
                        proposal=search.solve(rule,phase,local-reserve)
                        solver.append(proposal.evidence)
                        if proposal.evidence.status in (3,4):raise RuntimeError('MODEL_OR_TECHNICAL_STATUS')
                        vector=proposal.counts
                        if vector is None:
                            if phase=='TARGET':phase='FALLBACK_SERVICE';reason='ENCODED_NO_CANDIDATE_NOT_EXACT_PROOF';continue
                            reason='SOLVER_NO_FALLBACK_INCUMBENT';break
                        if vector in (excluded if phase=='TARGET' else excluded_fallback):
                            raise RuntimeError('REPEATED_EXCLUDED_VECTOR')
                        evaluated=check(vector,'MILP_TARGET' if phase=='TARGET' else 'MILP_FALLBACK')
                        if evaluated is None:reason='DEADLINE_UNVALIDATED_CANDIDATE';break
                        candidate,errors=evaluated
                        if candidate and phase=='TARGET' and passing(candidate,rule):
                            execution='INCOMPLETE' if proposal.evidence.status==1 else 'FINISHED'
                            reason='SOLVER_LIMIT_VALIDATED_TARGET_MET' if proposal.evidence.status==1 else 'TARGET_MET_OPTIMUM_UNPROVEN';break
                        if candidate and phase=='FALLBACK_SERVICE':
                            phase='FALLBACK_COST';reason='FALLBACK_SERVICE_INCUMBENT';continue
                        if candidate and phase=='FALLBACK_COST':
                            execution='INCOMPLETE' if proposal.evidence.status==1 else 'FINISHED'
                            reason='SOLVER_LIMIT_VALIDATED_FALLBACK' if proposal.evidence.status==1 else 'FALLBACK_VALIDATED_OPTIMUM_UNPROVEN';break
                        search.exclude(vector,phase=phase,hard_invalid=candidate is None)
                        excluded.add(vector)
                        if candidate is None or phase!='TARGET':excluded_fallback.add(vector)
                    else:reason='BOUNDED_SEARCH_LIMIT'
                    if request.policy.certification=='EXACT_ENUMERATION' and size<=request.policy.certification_vector_limit:
                        for vector in vectors(tuple(o.upper for o in offers)):
                            if time.perf_counter()>=local or check(vector,'ENUMERATION') is None:
                                reason='DEADLINE_CERTIFICATION';execution='INCOMPLETE';break
                            scanned+=1
                        else:
                            complete=True;execution='FINISHED';reason='EXACT_FINITE_DOMAIN_CERTIFIED'
                    elif request.policy.certification=='EXACT_ENUMERATION':
                        reason+='; CERTIFICATION_DOMAIN_LIMIT'
                if time.perf_counter()>local and not complete:
                    execution='INCOMPLETE';reason='DEADLINE_AFTER_VALIDATION'
        except (NumericUnsupported,ServingNumericError) as error:
            if getattr(error,'solver_evidence',None) is not None:
                solver.append(error.solver_evidence)
            execution='NUMERIC_UNSUPPORTED';reason='NUMERIC_ADMISSION_OR_EVALUATION';diagnostic=f'{type(error).__name__}: {error}'
        except Exception as error:
            # Explicit technical outcome; retain validated evidence without claiming success.
            execution='ERROR';reason='EXECUTION_ERROR';diagnostic=f'{type(error).__name__}: {error}'
        chosen=best or available
        results.append(StrategyProcurementResult(rule=rule,execution=execution,termination=reason,
            target_met=best is not None,target_feasibility='PASS_EXISTS' if best else 'NO_PASS_CERTIFIED' if complete else 'UNKNOWN',
            best_target_met=best,best_available=available if best is None else None,
            requirement_gaps=() if chosen is None else gaps(chosen,rule),
            proof='COMPLETE_EXACT_ENUMERATION' if complete else 'UNPROVEN',proof_scope='CAPTURED_FINITE_DOMAIN_ONLY',
            search_complete=complete,domain_size=size,enumerated_vectors=scanned,solver=tuple(solver),journal=tuple(journal),
            excluded=tuple(sorted(excluded)),diagnostic=diagnostic))
    statuses={r.execution for r in results}
    execution=next((s for s in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED','INCOMPLETE') if s in statuses),'FINISHED')
    elapsed=time.perf_counter()-started
    result=ProcurementResult(semantics_version='procurement/1',input=request,execution=execution,
        readiness='BLOCKED' if blocked else 'READY_FOR_INTERNAL_PROCUREMENT',coverage=coverage,strategies=tuple(results),
        elapsed_seconds=elapsed,deadline_overrun_seconds=max(0,elapsed-seconds),unique_exact_evaluations=len(cache),decision_readiness='NOT_ASSESSED')
    # Include final aggregate validation in wall time. Only measured timing fields
    # change after validation; no candidate/evidence or business status is bypassed.
    elapsed=time.perf_counter()-started
    return result.model_copy(update={'elapsed_seconds':elapsed,'deadline_overrun_seconds':max(0,elapsed-seconds)})
