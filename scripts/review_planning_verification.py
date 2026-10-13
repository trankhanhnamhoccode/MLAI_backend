"""Recompute independent small-domain acceptance and optionally audit supplied benchmarks."""
from datetime import timedelta
from fractions import Fraction as F
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.planning_verification_cases import run_case, independent_oracle
from app.application.contracts.procurement_v2 import ProcurementInputV2
from app.application.use_cases.procurement_v2 import evaluate_basket_v2


def exact(quantity):
    return F(int(quantity.numerator),int(quantity.denominator))


def temporal_upper_bound(request):
    """Independent conservative bound for the exact SYNTHETIC benchmark topology.

    All purchase lots of Ingredient203 expire before late start D+4; only captured
    nonexpired stock can serve P100 afterwards. Ignore ALL competing Products,
    budgets/capacity/FEFO consumption before then, giving an upper bound, not demand.
    Dates expire AFTER service on expiry date, matching the accepted date policy.
    No production serving/BOM/search/ranking call derives this arithmetic.
    """
    from uuid import UUID
    p=request.prepared;product,ingredient=UUID(int=100),UUID(int=203)
    first_late=p.request.cutoff_date+timedelta(days=4)
    points=[x for x in p.forecast.predictions if x.product_id==product]
    assert len(points)==7 and not request.arrivals
    terms={t.id:t for t in p.supplier_terms}
    expiry=[]
    for offer in request.offers:
        t=terms[offer.term_id]
        if t.ingredient_id!=ingredient:continue
        arrival=p.request.cutoff_date+timedelta(days=1+t.lead_time_days)
        assert t.shelf_life_days is not None
        end=arrival+timedelta(days=t.shelf_life_days)
        assert end<first_late
        expiry.append(dict(term_id=str(t.id),arrival=arrival.isoformat(),expiry=end.isoformat()))
    assert len(expiry)==2
    stock=sum((F(l.on_hand_quantity) for l in p.lots if l.ingredient_id==ingredient
               and (l.expiry_date is None or l.expiry_date>=first_late)),F(0))
    intensities=[]
    for point in points:
        if point.forecast_date<first_late:continue
        recipes=[r for r in p.recipes if r.product_id==product and r.effective_from<=point.forecast_date
                 and (r.effective_to is None or r.effective_to>=point.forecast_date)]
        assert len(recipes)==1
        recipe=recipes[0];lines=[x for x in recipe.lines if x.ingredient_id==ingredient]
        assert len(lines)==1
        intensities.append(F(lines[0].quantity)/(F(recipe.yield_quantity)*(1-F(recipe.process_loss_rate))))
    minimum=min(intensities);assert minimum>0
    early=sum((F(x.p50) for x in points if x.forecast_date<first_late),F(0))
    total=sum((F(x.p50) for x in points),F(0))
    upper=min(total,early+stock/minimum)
    required=total*F(19,20)
    assert upper<required
    return dict(status='VERIFIED_NECESSARY_BOUND_NO_CUSTOMER_PASS',
        scope='ONLY_UNCHANGED_CAPTURED_BENCHMARK_TOPOLOGY',product_id=str(product),ingredient_id=str(ingredient),
        first_late=first_late.isoformat(),purchase_expiry=expiry,late_stock=str(stock),
        minimum_late_intensity=str(minimum),early_requested=str(early),total_requested=str(total),
        fulfilled_upper_bound=str(upper),BASE95_required=str(required),service_upper_bound=str(upper/total),
        limitations='Separate reviewer arithmetic, not engine finite-enumeration proof. No artifact/proof/status rewritten.')


def audit_benchmark(raw):
    request=ProcurementInputV2.model_validate(raw['procurement']['input'])
    terms={t.id:t for t in request.prepared.supplier_terms}
    offers=[]
    for o in request.offers:
        t=terms[o.term_id];arrival=request.prepared.request.cutoff_date+timedelta(days=1+t.lead_time_days)
        offers.append(dict(term_id=str(t.id),ingredient_id=str(t.ingredient_id),unit=t.unit,
            pack_size=str(t.pack_size_base_quantity),pack_cost=str(t.pack_cost),MOQ=t.minimum_order_packs,
            maximum_packs=o.bound.maximum_packs,bound_source=o.bound.source,arrival=arrival.isoformat(),
            expiry=None if t.shelf_life_days is None else (arrival+timedelta(days=t.shelf_life_days)).isoformat()))
    # Five predeclared probes, not enumeration of the 65,536-vector domain.
    probes=[tuple(0 for _ in offers)]
    for skip in range(4):probes.append(tuple(2 if i%2==0 and i//2!=skip else 0 for i in range(8)))
    checked=[]
    for counts in probes:
        c=evaluate_basket_v2(request,counts)
        passing=c is not None and all(exact(m.served)>=F(19,20)*exact(m.requested)
            for m in c.services if m.path=='BASE')
        checked.append(dict(counts=counts,hard_valid=c is not None,customer_pass=passing,
            outlay=str(exact(c.outlay)) if c else None,
            BASE_service=[dict(product_id=str(m.product_id),requested=str(exact(m.requested)),
                served=str(exact(m.served)),ratio=None if exact(m.requested)==0 else str(exact(m.served)/exact(m.requested)))
                for m in c.services if m.path=='BASE'] if c else []))
    return dict(budget=request.budget.model_dump(mode='json'),fee_mode=request.policy.fee_mode,
        supplier_fees=[f.model_dump(mode='json') for f in request.supplier_fees],offers=offers,
        stock=[l.model_dump(mode='json') for l in request.prepared.lots],
        capacities=[c.model_dump(mode='json') for c in request.capacities],
        strategies=[{k:s[k] for k in ('strategy','termination','execution','customer_feasibility','proof','proof_scope','domain_size')}
                    for s in raw['procurement']['strategies']],exact_probes=checked,
        probe_conclusion='No witness in five probes; this absence alone is not infeasibility proof.',
        separate_temporal_bound=temporal_upper_bound(request))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark-directory',type=Path,help='Optional generated pipeline_5p/10p inputs, never required historical evidence')
    args=parser.parse_args()
    folder=ROOT/'runtime/verification/planning/results';index=1
    while folder.exists():index+=1;folder=ROOT/f'runtime/verification/planning/results_{index}'
    folder.mkdir(parents=True,exist_ok=False)
    rows=[]
    for kind in ('stock','purchase','infeasible'):
        resolved,result,calls=run_case(kind);oracle=independent_oracle(kind)
        (folder/f'{kind}_resolution.json').write_text(resolved.model_dump_json(indent=2),encoding='utf-8')
        (folder/f'{kind}_pipeline.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
        customer=[s for s in result.procurement.strategies if s.customer_pass]
        verified=(result.selection.winner_token is not None and customer and
                  all(exact(s.candidate.outlay)==oracle['minimum_outlay'] for s in customer)) if oracle['passing'] else (
                  result.selection.winner_token is None and all(s.customer_feasibility=='NO_PASS_CERTIFIED' for s in result.procurement.strategies))
        rows.append(dict(case=kind,status='VERIFIED' if verified else 'UNKNOWN_NATIVE_DISCREPANCY',
            oracle=oracle,native_factory_calls=calls,winner_token=result.selection.winner_token,
            strategy_evidence=[dict(strategy=s.strategy,counts=s.candidate.counts if s.candidate else None,
                outlay=str(exact(s.candidate.outlay)) if s.candidate else None,customer_pass=s.customer_pass,
                construction_pass=s.construction_pass,proof=s.proof,proof_scope=s.proof_scope,
                feasibility=s.customer_feasibility,termination=s.termination,enumerated_vectors=s.enumerated_vectors)
                for s in result.procurement.strategies]))
    audits={} if args.benchmark_directory is None else {str(n):audit_benchmark(json.loads((args.benchmark_directory/f'pipeline_{n}p.json').read_text())) for n in (5,10)}
    summary=dict(cases=rows,benchmark_audit=audits,limits='Synthetic only; optional supplied benchmark probes, no DB/HTTP/accuracy/SLA.')
    (folder/'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(dict(results=str(folder),cases=[dict(case=r['case'],status=r['status']) for r in rows],
        benchmark_engine_feasibility='UNKNOWN',benchmark_audited=bool(audits))),flush=True)


if __name__=='__main__':main()
