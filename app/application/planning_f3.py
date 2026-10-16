"""F3 metrics/replay over existing E4 and exact host serving; no second engine."""
from collections import defaultdict
from fractions import Fraction as F
from app.application.planning_impact import realized_metrics,fraction,exact_json
from app.application.use_cases.procurement_v2 import evaluate_basket_v2
from app.application.use_cases.procurement_selection import compare_procurement_v2,select_winner


def mass_balance(simulation):
    groups=defaultdict(list)
    for r in simulation.lots:groups[r.path_id,r.lot_id,r.ingredient_id,r.unit].append(r)
    receipts=[]
    for (path,lot,ingredient,unit),rows in sorted(groups.items()):
        rows.sort(key=lambda r:r.day)
        incoming=fraction(rows[0].opening)+sum((fraction(r.arrivals) for r in rows),F(0))
        consumed=sum((fraction(r.consumed) for r in rows),F(0))
        expired=sum((fraction(r.pre_service_expired)+fraction(r.close_expired) for r in rows),F(0))
        waste=sum((fraction(r.other_waste) for r in rows),F(0));ending=fraction(rows[-1].ending)
        if incoming!=consumed+expired+waste+ending:raise ValueError('F3_MASS_BALANCE')
        receipts.append(dict(path=path,lot_id=lot,ingredient_id=ingredient,unit=unit,incoming=exact_json(incoming),
            consumed=exact_json(consumed),expired=exact_json(expired),other_waste=exact_json(waste),ending=exact_json(ending)))
    return receipts


def cost_balance(request,candidate):
    terms={t.id:t for t in request.prepared.supplier_terms}
    purchase=sum((F(terms[b.term_id].pack_cost)*b.packs for b in candidate.basket),F(0))
    suppliers={terms[b.term_id].supplier_id for b in candidate.basket}
    fees=sum((F(f.amount) for f in request.supplier_fees if f.supplier_id in suppliers),F(0))
    if request.policy.fee_mode!='PER_SUPPLIER_ORDER':raise ValueError('F3_FROZEN_FEE_MODE')
    if fraction(candidate.outlay)!=purchase+fees:raise ValueError('F3_COST_BALANCE')
    return dict(purchase=exact_json(purchase),payable_fees=exact_json(fees),total=exact_json(purchase+fees),currency=request.prepared.currency)


def validate_fixed(selection,request):
    if selection.comparison.source.input!=request:raise ValueError('F3_PLANNING_INPUT_CHANGED')
    for strategy in selection.comparison.source.strategies:
        c=strategy.candidate
        if c is not None:
            if evaluate_basket_v2(request,c.counts)!=c:raise ValueError('F3_FIXED_BASKET_CHANGED')
            cost_balance(request,c);mass_balance(c.evaluation)
    if select_winner(compare_procurement_v2(selection.comparison.source))!=selection:
        raise ValueError('F3_SELECTION_CHANGED')


def summarize(runs,plan):
    results=[]
    for run in runs:
        s=run.selection;winner=None if s is None else next((o for o in s.comparison.options if o.token==s.winner_token),None)
        options=[]
        if s is not None:
            for o in s.comparison.options:
                options.append(dict(token=o.token,eligible=o.token in s.eligible_tokens,source_strategies=o.source_strategies,
                    basket=o.basket,arrivals=o.arrivals,outlay=o.outlay,products=o.products,ingredients=o.ingredients))
        results.append(dict(identity=run.identity,origin=run.snapshot.origin,fixture=run.snapshot.fixture_id,variant=run.variant,
            status=run.status,reason=run.reason,winner=None if winner is None else winner.token,
            winner_outlay=None if winner is None else winner.outlay,winner_basket=None if winner is None else winner.basket,
            winner_products=None if winner is None else winner.products,winner_ingredients=None if winner is None else winner.ingredients,
            options=options,realized_status='NOT_EVALUATED' if run.realized is None else run.realized.status,
            realized=realized_metrics(run.realized),elapsed_seconds=run.elapsed_seconds,
            coverage=[] if s is None else s.comparison.source.coverage,
            host_execution=None if s is None else s.comparison.source.execution,
            host_elapsed_seconds=None if s is None else s.comparison.source.elapsed_seconds,
            host_deadline_overrun_seconds=None if s is None else s.comparison.source.deadline_overrun_seconds,
            strategies=[] if s is None else [dict(strategy=r.strategy,execution=r.execution,termination=r.termination,
                selection_kind=r.selection_kind,proof=r.proof,proof_scope=r.proof_scope,domain_size=r.domain_size,
                search_complete=r.search_complete,enumerated_vectors=r.enumerated_vectors,solves=len(r.solver),
                customer_pass=r.customer_pass,construction_pass=r.construction_pass,
                customer_feasibility=r.customer_feasibility,construction_feasibility=r.construction_feasibility,
                customer_gaps=r.customer_gaps,construction_gaps=r.construction_gaps) for r in s.comparison.source.strategies]))
    pairs=[]
    for snap in plan.snapshots:
        group=[r for r in results if (r['origin'],r['fixture'])==(snap.origin,snap.fixture_id)]
        by={r['variant']:r for r in group};b=by.get('B_COMMON');c=by.get('C0_COMMON')
        pairs.append(dict(origin=snap.origin,fixture=snap.fixture_id,completed=len(group)==3 and all(r['status']=='COMPLETED' for r in group),
            primary_paired_winners=b is not None and c is not None and b['winner'] is not None and c['winner'] is not None,
            primary_paired_realized=b is not None and c is not None and b['realized_status']==c['realized_status']=='COMPLETE_PRIMARY_OBSERVED',
            no_winner=[r['variant'] for r in group if r['winner'] is None]))
    return dict(status='F3_COUNTERFACTUAL_SYNTHETIC_COMPLETE' if len(runs)==24 and all(r.status=='COMPLETED' for r in runs) else 'PARTIAL',
        classification='F3_SYNTHETIC',expected_runs=24,retained_runs=len(runs),results=results,paired_cases=pairs,
        run_order=plan.run_order,primary_comparison='B_COMMON_vs_C0_COMMON',C1='EXPLORATORY_NOT_SELECTED',
        production='LOCKED',real_impact='NOT_ESTABLISHED',
        interpretation='Per-Product/path/unit service; per-Ingredient/unit waste. Counterfactual outlay is not realized savings; no forecast selection by impact.')
