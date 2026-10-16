"""Forecast-only host composition and fixed-basket, complete-primary post evaluation."""
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid5, NAMESPACE_URL

from app.application.contracts.planning_impact import ImpactBinding, ImpactSnapshot, RealizedImpact
from app.application.contracts.procurement_v2 import ProcurementInputV2
from app.application.contracts.serving import ServingSimulationInput
from app.application.forecast_benchmark_reporting import attach_targets
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.use_cases.bom import expand_bom
from app.application.use_cases.procurement_v2 import execute_procurement_v2
from app.application.use_cases.procurement_selection import compare_procurement_v2, select_winner
from app.application.use_cases.serving import simulate_serving


def planning_request(snapshot: ImpactSnapshot, binding: ImpactBinding) -> ProcurementInputV2:
    checkpoint = binding.checkpoint
    rows = checkpoint.predictions
    if checkpoint.status != 'COMPLETED' or checkpoint.origin != snapshot.origin:
        raise ValueError('E3_COMPLETED_ORIGIN_REQUIRED')
    if binding.output_digest != challenger_digest('e3-output', rows):
        raise ValueError('E3_OUTPUT_DIGEST_MISMATCH')
    if any(p.actual is not None or p.mask != 'missing' for p in rows):
        raise ValueError('SCORED_TARGETS_CANNOT_ENTER_PLANNING')
    raw = snapshot.template.model_dump(mode='python')
    p = raw['prepared']
    run_id = uuid5(NAMESPACE_URL, 'e4-forecast/'+binding.output_digest)
    p['request']['forecast_run_id'] = run_id
    p['forecast'].update(run_id=run_id, model_type=checkpoint.arm,
        model_version='E3/'+checkpoint.identity, artifact_identity=checkpoint.artifact_identity,
        input_fingerprint=checkpoint.input_digest,
        predictions=tuple(dict(product_id=r.product_id, forecast_date=r.target_date, unit=r.selling_unit,
                               p25=r.p25,p50=r.p50,p75=r.p75) for r in rows))
    if any(r.store_id != p['request']['store_id'] or r.arm != checkpoint.arm or r.origin != checkpoint.origin for r in rows):
        raise ValueError('E3_OUTPUT_SCOPE_MISMATCH')
    for refs in (raw['source_references'], p['source_references']):
        for ref in refs:
            if ref['entity'] == 'forecast_run': ref['entity_id'] = run_id
    return ProcurementInputV2.model_validate(raw)


def plan_forecast(request, search_factory):
    bom = expand_bom(request.prepared)
    if bom.status != 'COMPLETE' or bom.decision_readiness == 'DATA_BLOCKED':
        raise ValueError('HOST_BOM_BLOCKED')
    result = execute_procurement_v2(request, search_factory)
    return select_winner(compare_procurement_v2(result))


def realized_evaluation(data, checkpoint, selection):
    rows = attach_targets(data, checkpoint)
    digest = challenger_digest('realized-targets', tuple((r.product_id,r.target_date,r.actual,r.mask) for r in rows))
    primary = sum(r.mask == 'primary_known_false' for r in rows)
    body = dict(target_digest=digest,primary_tasks=primary,total_tasks=len(rows),simulation=None)
    if selection.winner_token is None:
        return RealizedImpact(status='UNAVAILABLE_NO_WINNER',**body)
    if primary != len(rows):
        return RealizedImpact(status='UNAVAILABLE_INCOMPLETE_PRIMARY',**body)
    winner = next(o for o in selection.comparison.options if o.token == selection.winner_token)
    prepared = selection.comparison.source.input.prepared.model_dump(mode='python')
    run_id = uuid5(NAMESPACE_URL, 'e4-realized/'+digest)
    prepared['request']['forecast_run_id'] = run_id
    prepared['forecast'].update(run_id=run_id,model_type='complete_observed_target_evaluation',model_version='1',
        artifact_identity=None,input_fingerprint=digest,
        predictions=tuple(dict(product_id=r.product_id,forecast_date=r.target_date,unit=r.selling_unit,
                               p25=r.actual,p50=r.actual,p75=r.actual) for r in rows))
    for ref in prepared['source_references']:
        if ref['entity'] == 'forecast_run': ref['entity_id'] = run_id
    # No procurement/generator here: basket, captured facts and arrivals stay fixed.
    simulation = simulate_serving(ServingSimulationInput(prepared=prepared,arrivals=winner.arrivals))
    if simulation.status != 'COMPLETE':
        raise ValueError('REALIZED_EXACT_SERVING_BLOCKED')
    return RealizedImpact(status='COMPLETE_PRIMARY_OBSERVED',**(body|{'simulation':simulation}))


def fraction(value):
    return Fraction(int(value.numerator),int(value.denominator))


def exact_json(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def realized_metrics(realized):
    if realized is None or realized.simulation is None:
        return None
    simulation = realized.simulation
    products=[];ingredients=[]
    for product in simulation.input.prepared.products:
        rows=[r for r in simulation.products if r.path_id=='BASE' and r.product_id==product.product_id]
        requested=sum((fraction(r.requested) for r in rows),Fraction(0))
        served=sum((fraction(r.fulfilled) for r in rows),Fraction(0))
        products.append(dict(product_id=product.product_id,unit=product.selling_unit,
            requested=exact_json(requested),served=exact_json(served),lost=exact_json(requested-served),
            service=None if not requested else exact_json(served/requested)))
    for ingredient in simulation.input.prepared.ingredients:
        rows=sorted((r for r in simulation.ingredients if r.path_id=='BASE' and r.ingredient_id==ingredient.ingredient_id),key=lambda r:r.day)
        ingredients.append(dict(ingredient_id=ingredient.ingredient_id,unit=ingredient.unit,
            consumed=exact_json(sum((fraction(r.consumed) for r in rows),Fraction(0))),
            expired=exact_json(sum((fraction(r.expired) for r in rows),Fraction(0))),
            ending=exact_json(fraction(rows[-1].ending))))
    return dict(products=products,ingredients=ingredients)


def report_runs(runs, *, expected):
    rows=[]
    for run in runs:
        selection=run.selection
        winner=None if selection is None else next((o for o in selection.comparison.options if o.token==selection.winner_token),None)
        rows.append(dict(fixture=run.snapshot.fixture_id,origin=run.snapshot.origin,arm=run.binding.checkpoint.arm,
            status=run.status,reason=run.reason,winner_available=winner is not None and run.status=='COMPLETED',
            outlay=None if winner is None else winner.outlay,
            budget=run.snapshot.template.budget,
            realized_status='NOT_EVALUATED' if run.realized is None else run.realized.status,
            realized=realized_metrics(run.realized),
            strategies=() if selection is None else tuple(dict(strategy=s.strategy,execution=s.execution,
                termination=s.termination,proof=s.proof,scope=s.proof_scope,domain_size=s.domain_size,
                customer_pass=s.customer_pass,construction_pass=s.construction_pass,selection_kind=s.selection_kind,
                solves=len(s.solver)) for s in selection.comparison.source.strategies),elapsed_seconds=run.elapsed_seconds))
    groups={}
    for row in rows: groups.setdefault((row['fixture'],row['origin']),[]).append(row)
    paired_winner=[v for v in groups.values() if len(v)==3 and all(r['winner_available'] for r in v)]
    paired_realized=[v for v in paired_winner if all(r['realized_status']=='COMPLETE_PRIMARY_OBSERVED' for r in v)]
    return dict(status='COUNTERFACTUAL_SYNTHETIC_VERIFIED' if len(runs)==expected and all(r.status=='COMPLETED' for r in runs) else 'INCOMPLETE',
        real_impact='REAL_IMPACT_BLOCKED',production='LOCKED',e3_accuracy='REAL_BENCHMARK_BLOCKED',
        runs=len(runs),expected_runs=expected,paired_groups=len(groups),paired_winner_groups=len(paired_winner),
        paired_realized_groups=len(paired_realized),
        paired_completed_groups=sum(len(v)==3 and all(r['status']=='COMPLETED' for r in v) for v in groups.values()),
        exclusions=tuple(dict(fixture=r['fixture'],origin=r['origin'],arm=r['arm'],reason=r['reason']) for r in rows if r['status']!='COMPLETED'),
        availability=dict(Counter(r['realized_status'] for r in rows)),
        native_solves=sum(s['solves'] for r in rows for s in r['strategies']),
        elapsed_seconds=sum(r.elapsed_seconds for r in runs),results=rows,
        interpretation='Per-Product/unit service and per-Ingredient/unit waste only; outlay is not profit or real savings.')
