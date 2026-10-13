"""Snapshot-only procurement/2. Effective inputs; no DB/default/provider lookup."""
import math
import time
from fractions import Fraction as F
from decimal import Decimal
from typing import Callable
from app.application.contracts.procurement_v2 import (
    ProcurementInputV2, ProcurementResultV2, StrategyResultV2, ProductGap, EvaluationEvidence,
)
from app.application.procurement_solver import NumericUnsupported
from app.application.procurement_solver_v2 import ProductCandidateSearch
from app.application.use_cases.procurement import captured_offers, constraint_coverage, _evaluate, rational
from app.application.use_cases.serving import _quantity
from app.domain.decision.procurement import vectors
from app.domain.decision.procurement_policy import PATH_FOR, service_summary, shortfall, fallback_key
from app.domain.decision.quantities import exact, ServingNumericError


def candidate_gaps(request, candidate, construction_path=None):
    metrics={(m.path,m.product_id):m for m in candidate.services}
    targets=[]
    if construction_path:
        targets=[(construction_path,p,Decimal(1)) for p in request.prepared.request.product_ids]
    else:
        for requirement in request.requirements.paths:
            overrides={p.product_id:p.target for p in requirement.overrides}
            targets.extend((requirement.path,p,overrides.get(p,requirement.minimum))
                           for p in request.prepared.request.product_ids)
    return tuple(ProductGap(path=path,product_id=p,target=target,
        shortfall_quantity=_quantity(shortfall(rational(metrics[path,p].requested),
                                              rational(metrics[path,p].served),exact(target))))
        for path,p,target in targets)


def passed(gaps):
    return all(rational(g.shortfall_quantity)==0 for g in gaps)


def summary(candidate,path):
    return service_summary((rational(m.requested),rational(m.served))
                           for m in candidate.services if m.path==path)


def candidate_key(candidate,path,target):
    # Offer order is canonical UUID order; context/arrivals fixed within this input.
    stable=stable_basket(candidate)
    return ((rational(candidate.outlay),stable) if target else
            fallback_key(summary(candidate,path),rational(candidate.outlay),stable))


def stable_basket(candidate):
    return (tuple((str(b.term_id),b.packs) for b in candidate.basket),
            tuple((str(a.lot_id),a.arrival_day,str(a.expiry_date),exact(a.quantity)) for a in candidate.arrivals))


def evaluate_basket_v2(request: ProcurementInputV2, counts: tuple[int,...]):
    request=ProcurementInputV2.model_validate(request)
    if any(c.status=='BLOCKED' for c in constraint_coverage(request)):
        raise ValueError('procurement/2 input blocked')
    return _evaluate(request,captured_offers(request),counts,product_service_only=True)[0]


def execute_procurement_v2(request: ProcurementInputV2,
                          search_factory: Callable[...,ProductCandidateSearch]) -> ProcurementResultV2:
    start=time.perf_counter()
    request=ProcurementInputV2.model_validate(request)
    seconds=float(request.policy.computation_seconds)
    if not math.isfinite(seconds) or seconds<=0:
        raise ValueError('Unsupported deadline')
    deadline=start+seconds
    offers=captured_offers(request)
    coverage=constraint_coverage(request)
    blocked=any(c.status=='BLOCKED' for c in coverage)
    size=math.prod(o.upper+1 for o in offers)
    cache={};results=[]
    for index,strategy in enumerate(('LEAN','BALANCED','PROTECTED')):
        now=time.perf_counter()
        local=now+max(0,deadline-now)/(3-index)
        path=PATH_FOR[strategy]
        best=None;fallback=None;reference=None
        journal=[];solver=[];complete=False;scanned=0;diagnostic=None
        execution='BLOCKED' if blocked else 'INCOMPLETE'
        reason='INPUT_BLOCKED' if blocked else 'DEADLINE'

        def check(counts,stage):
            nonlocal best,fallback,reference
            if counts not in cache:
                if time.perf_counter()>=local:return None
                evaluated=_evaluate(request,offers,counts,product_service_only=True)
            else:
                evaluated=cache[counts]
            candidate,errors=evaluated
            customer=candidate is not None and passed(candidate_gaps(request,candidate))
            construction=candidate is not None and passed(candidate_gaps(request,candidate,path))
            # Only cache fully classified exact facts. Numeric classification can
            # fail after a fixed basket evaluated successfully; it is not evidence.
            cache[counts]=evaluated
            journal.append(EvaluationEvidence(counts=counts,stage=stage,hard_valid=candidate is not None,
                customer_pass=customer,construction_pass=construction,reasons=errors))
            if candidate:
                if customer:
                    if construction and (best is None or candidate_key(candidate,path,True)<candidate_key(best,path,True)):
                        best=candidate
                    if fallback is None or candidate_key(candidate,path,False)<candidate_key(fallback,path,False):
                        fallback=candidate
                elif reference is None:
                    reference=candidate  # Reference only, expressly NOT best_available.
            return candidate,customer,construction

        try:
            if not blocked:
                for requirement in request.requirements.paths:
                    exact(requirement.minimum)
                    for override in requirement.overrides:exact(override.target)
                check(tuple(0 for _ in offers),'ZERO_BASELINE')
                if best is not None and rational(best.outlay)==0:
                    execution='FINISHED';reason='ZERO_PURCHASE_TARGET_PASS_UNPROVEN'
                elif time.perf_counter()<local:
                    search=search_factory(request,offers)
                    phase='TARGET';excluded=set()
                    for _ in range(request.policy.max_solves_per_strategy):
                        reserve=float(request.policy.validation_reserve_seconds)
                        if time.perf_counter()>=local-reserve:
                            reason='SEARCH_DEADLINE';break
                        proposal=search.solve(strategy,phase,local-reserve)
                        solver.append(proposal.evidence)
                        if proposal.evidence.status in (3,4):
                            raise RuntimeError('MODEL_OR_TECHNICAL_STATUS')
                        counts=proposal.counts
                        if counts is None:
                            if proposal.evidence.status==1:
                                reason='SEARCH_LIMIT_NO_INCUMBENT';break
                            if phase=='TARGET':phase='FALLBACK_MIN';continue
                            reason='ENCODED_NO_CUSTOMER_INCUMBENT_NOT_PROOF';break
                        if (phase,counts) in excluded:
                            raise RuntimeError('REPEATED_EXCLUDED_VECTOR')
                        evaluated=check(counts,phase)
                        if evaluated is None:reason='DEADLINE_BEFORE_VALIDATION';break
                        candidate,customer,construction=evaluated
                        acceptable=customer and (construction if phase=='TARGET' else True)
                        if acceptable:
                            search.accept(strategy,phase,candidate)
                            if phase in ('TARGET','FALLBACK_COST'):
                                execution='INCOMPLETE' if proposal.evidence.status==1 else 'FINISHED'
                                reason='VALIDATED_INCUMBENT_UNPROVEN';break
                            phase={'FALLBACK_MIN':'FALLBACK_MEAN','FALLBACK_MEAN':'FALLBACK_COST'}[phase]
                            continue
                        # Only this exact integer vector is excluded, not its neighborhood.
                        search.exclude(counts,phase=phase,hard_invalid=candidate is None,
                                       customer_invalid=not customer)
                        excluded.add((phase,counts))
                    else:
                        reason='SEARCH_ITERATION_LIMIT'
                if request.policy.certification=='EXACT_ENUMERATION' and size<=request.policy.certification_vector_limit:
                    for counts in vectors(tuple(o.upper for o in offers)):
                        if time.perf_counter()>=local or check(counts,'EXACT_ENUMERATION') is None:
                            execution='INCOMPLETE';reason='CERTIFICATION_DEADLINE';break
                        scanned+=1
                    else:
                        complete=True;execution='FINISHED';reason='CAPTURED_FINITE_DOMAIN_CERTIFIED'
        except (NumericUnsupported,ServingNumericError) as error:
            execution='NUMERIC_UNSUPPORTED';reason='NUMERIC_ADMISSION_OR_EVALUATION'
            diagnostic=f'{type(error).__name__}: {error}'
            if getattr(error,'solver_evidence',None) is not None:solver.append(error.solver_evidence)
        except Exception as error:
            execution='ERROR';reason='EXECUTION_ERROR';diagnostic=f'{type(error).__name__}: {error}'
        chosen=best or fallback or reference
        cg=() if chosen is None else candidate_gaps(request,chosen)
        tg=() if chosen is None else candidate_gaps(request,chosen,path)
        results.append(StrategyResultV2(strategy=strategy,construction_path=path,execution=execution,
            termination=reason,candidate=chosen,
            selection_kind='TARGET' if best else 'CUSTOMER_PASS_FALLBACK' if fallback else
                'REFERENCE_NOT_RANKED' if reference else 'NONE',
            customer_pass=chosen is not None and passed(cg),construction_pass=chosen is not None and passed(tg),
            customer_gaps=cg,construction_gaps=tg,
            customer_feasibility='PASS_EXISTS' if best or fallback else 'NO_PASS_CERTIFIED' if complete else 'UNKNOWN',
            construction_feasibility='PASS_EXISTS' if best else 'NO_PASS_CERTIFIED' if complete else 'UNKNOWN',
            proof='COMPLETE_EXACT_ENUMERATION' if complete else 'UNPROVEN',
            proof_scope='CAPTURED_FINITE_DOMAIN_ONLY',search_complete=complete,domain_size=size,
            enumerated_vectors=scanned,solver=tuple(solver),journal=tuple(journal),diagnostic=diagnostic))
    statuses={r.execution for r in results}
    execution=next((s for s in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED','INCOMPLETE') if s in statuses),'FINISHED')
    elapsed=time.perf_counter()-start
    result=ProcurementResultV2(semantics_version='procurement/2',input=request,execution=execution,
        coverage=coverage,strategies=tuple(results),elapsed_seconds=elapsed,
        deadline_overrun_seconds=max(0,elapsed-seconds),unique_exact_evaluations=len(cache))
    elapsed=time.perf_counter()-start
    return result.model_copy(update={'elapsed_seconds':elapsed,'deadline_overrun_seconds':max(0,elapsed-seconds)})
