"""Reconcile v2 candidates/proof against captured exact facts, never solver views."""
import math
from app.application.use_cases.procurement import _evaluate, captured_offers, constraint_coverage, rational
from app.domain.decision.procurement import vectors
from app.domain.decision.procurement_policy import PATH_FOR


def validate_result(result):
    from app.application.use_cases.procurement_v2 import candidate_gaps, passed, candidate_key
    request=result.input
    if tuple(r.strategy for r in result.strategies)!=('LEAN','BALANCED','PROTECTED'):
        raise ValueError('Exactly three ordered strategy results required')
    if result.coverage!=constraint_coverage(request):raise ValueError('Coverage mismatch')
    blocked=any(c.status=='BLOCKED' for c in result.coverage)
    offers=captured_offers(request);bounds=tuple(o.upper for o in offers)
    size=math.prod(n+1 for n in bounds);cache={}
    def evaluate(counts):
        if counts not in cache:cache[counts]=_evaluate(request,offers,counts,product_service_only=True)
        return cache[counts][0]
    for row in result.strategies:
        if row.construction_path!=PATH_FOR[row.strategy] or row.domain_size!=size:
            raise ValueError('Strategy domain/path mismatch')
        if blocked:
            if row.candidate or row.journal or row.execution!='BLOCKED':raise ValueError('Blocked input cannot compute')
            if (row.search_complete or row.proof!='UNPROVEN' or row.enumerated_vectors or row.customer_pass
                    or row.construction_pass or row.customer_gaps or row.construction_gaps
                    or row.customer_feasibility!='UNKNOWN' or row.construction_feasibility!='UNKNOWN'
                    or row.selection_kind!='NONE' or row.solver):
                raise ValueError('Blocked result cannot manufacture feasibility/proof')
            continue
        candidate=row.candidate
        if candidate is not None:
            actual=evaluate(candidate.counts)
            if actual!=candidate:raise ValueError('Candidate does not reconcile with exact captured evaluation')
            cg=candidate_gaps(request,candidate);tg=candidate_gaps(request,candidate,row.construction_path)
            if (row.customer_gaps,row.construction_gaps,row.customer_pass,row.construction_pass)!=(cg,tg,passed(cg),passed(tg)):
                raise ValueError('Customer/construction eligibility mismatch')
        elif row.customer_gaps or row.construction_gaps or row.customer_pass or row.construction_pass:
            raise ValueError('Absent candidate cannot assert service')
        expected_kind=('NONE' if candidate is None else 'TARGET' if row.customer_pass and row.construction_pass else
                       'CUSTOMER_PASS_FALLBACK' if row.customer_pass else 'REFERENCE_NOT_RANKED')
        if row.selection_kind!=expected_kind:raise ValueError('Candidate selection kind mismatch')
        if row.search_complete!=(row.proof=='COMPLETE_EXACT_ENUMERATION'):
            raise ValueError('Exact proof must be complete')
        if row.execution=='ERROR' and not row.diagnostic:raise ValueError('Technical error must retain diagnostic')
        checked=[]
        for entry in row.journal:
            c=evaluate(entry.counts)
            customer=c is not None and passed(candidate_gaps(request,c))
            construction=c is not None and passed(candidate_gaps(request,c,row.construction_path))
            if (entry.hard_valid,entry.customer_pass,entry.construction_pass)!=(c is not None,customer,construction):
                raise ValueError('Evaluation journal classification mismatch')
            if entry.reasons!=cache[entry.counts][1]:raise ValueError('Exact rejection reasons mismatch')
            if c and customer:checked.append(c)
        both=[c for c in checked if passed(candidate_gaps(request,c,row.construction_path))]
        if row.customer_feasibility!=('PASS_EXISTS' if checked else 'NO_PASS_CERTIFIED' if row.search_complete else 'UNKNOWN'):
            raise ValueError('Customer-domain feasibility mismatch')
        if row.construction_feasibility!=('PASS_EXISTS' if both else 'NO_PASS_CERTIFIED' if row.search_complete else 'UNKNOWN'):
            raise ValueError('Joint construction-domain feasibility mismatch')
        if checked:
            pool=both or checked
            best=min(pool,key=lambda c:candidate_key(c,row.construction_path,bool(both)))
            if best!=candidate:raise ValueError('Chosen candidate does not follow exact ranking among evaluated facts')
        if row.search_complete:
            if row.execution!='FINISHED' or row.enumerated_vectors!=size:
                raise ValueError('Certification/execution mismatch')
            enumerated={e.counts for e in row.journal if e.stage=='EXACT_ENUMERATION'}
            if enumerated!=set(vectors(bounds)):raise ValueError('Incomplete finite proof traversal')
        elif row.enumerated_vectors!=len({e.counts for e in row.journal if e.stage=='EXACT_ENUMERATION'}):
            raise ValueError('Partial enumeration count mismatch')
    statuses={r.execution for r in result.strategies}
    expected=next((s for s in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED','INCOMPLETE') if s in statuses),'FINISHED')
    if result.execution!=expected:raise ValueError('Aggregate execution mismatch')
    observed={e.counts for row in result.strategies for e in row.journal}
    if result.unique_exact_evaluations!=len(observed):raise ValueError('Exact cache evidence mismatch')
    if not math.isfinite(result.elapsed_seconds) or result.elapsed_seconds<0 or result.deadline_overrun_seconds<0:
        raise ValueError('Invalid timing evidence')
    if result.deadline_overrun_seconds!=max(0,result.elapsed_seconds-float(request.policy.computation_seconds)):
        raise ValueError('Deadline overrun evidence mismatch')
