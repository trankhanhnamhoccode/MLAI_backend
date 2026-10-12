"""Offline SYNTHETIC fixed-basket fixture generation; no solver/search or DB.

The comparison/demo read this artifact; they never rerun this generator implicitly.
"""
from pathlib import Path
import sys
import time
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.application.contracts.procurement import ProcurementInput, ProcurementResult, StrategyProcurementResult, CandidateClassification
from app.application.use_cases.procurement import evaluate_procurement_basket, gaps, passing
from scripts.procurement_demo_cases import envelope, snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--equal-cost',action='store_true')
    args=parser.parse_args()
    specs=([dict(ingredient=0,pack='1',cost='2',upper=1),dict(ingredient=0,pack='1',cost='2',upper=1)]
           if args.equal_cost else [dict(ingredient=0,pack='1',cost='2',upper=4)])
    data=envelope(snapshot([[20,0,0,0,0,0,0],[10,0,0,0,0,0,0]],[{0:'.2'},{0:'.4'}],[(0,'6',None)],['L']),
        specs,budget='9',target='.9',certification='DISABLED')
    points=data['prepared']['forecast']['predictions']
    for p in points:
        if p['p50']=='20':p.update(p25='10',p75='30')
        if p['p50']=='10':p.update(p25='5',p75='20')
    data['policy'].update(fee_mode='PER_SUPPLIER_ORDER',configuration_id='SYNTHETIC-S351-MANUAL-SUBSET',
        provenance='Offline canonical fixed-basket evaluations only; no procurement search was run')
    from uuid import UUID
    data['supplier_fees']=[dict(supplier_id=UUID(int=2000),amount='1',provenance='SYNTHETIC unclassified payable supplier fee')]
    request=ProcurementInput.model_validate(data);rows=[];started=time.perf_counter()
    vectors=((1,0),(0,1),(1,0)) if args.equal_cost else ((0,),(2,),(4,))
    for rule,vector in zip(request.policy.rules,vectors):
        candidate=evaluate_procurement_basket(request,vector)
        met=passing(candidate,rule)
        rows.append(StrategyProcurementResult(rule=rule,execution='INCOMPLETE',
            termination='SYNTHETIC_MANUAL_ONE_VECTOR_SUBSET_NOT_OPTIMIZATION',target_met=met,
            target_feasibility='PASS_EXISTS' if met else 'UNKNOWN',
            best_target_met=candidate if met else None,best_available=None if met else candidate,
            requirement_gaps=gaps(candidate,rule),proof='UNPROVEN',proof_scope='CAPTURED_FINITE_DOMAIN_ONLY',
            search_complete=False,domain_size=4 if args.equal_cost else 5,enumerated_vectors=1,solver=(),
            journal=(CandidateClassification(counts=vector,stage='ENUMERATION',
                classification='TARGET_MET' if met else 'HARD_VALID_TARGET_MISS',reasons=()),),excluded=(),diagnostic=None))
    from app.application.use_cases.procurement import constraint_coverage
    result=ProcurementResult(semantics_version='procurement/1',input=request,execution='INCOMPLETE',
        readiness='READY_FOR_INTERNAL_PROCUREMENT',coverage=constraint_coverage(request),strategies=tuple(rows),
        elapsed_seconds=time.perf_counter()-started,deadline_overrun_seconds=0,unique_exact_evaluations=len(set(vectors)),decision_readiness='NOT_ASSESSED')
    name='procurement_comparison_equal_cost_synthetic.json' if args.equal_cost else 'procurement_comparison_synthetic.json'
    destination=Path(__file__).resolve().parents[1]/'tests/fixtures'/name
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(result.model_dump_json(indent=2),encoding='utf-8')
    print('SYNTHETIC fixed-basket artifact written:',destination.name)


if __name__=='__main__':main()
