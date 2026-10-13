"""Project already evaluated procurement candidates. No solving/simulating or winner."""
from dataclasses import asdict
from datetime import timedelta
from itertools import combinations
from app.application.contracts.procurement_comparison import (
    ProcurementComparisonInput, ProcurementComparisonResult, ComparisonOption, StrategyComparisonOutcome,
    ComparedProduct, ComparedIngredient, OptionDelta, ProductDelta, IngredientDelta, ComparisonDiagnostic,
)
from app.application.procurement_comparison_facts import (
    q, quantity, signed, plan_identity, evaluation_identity, option_token, outlay_breakdown,
    daily_products, daily_ingredients, issues,
)
from app.domain.decision.comparison import (
    ProductObservation, IngredientObservation, product_totals, ingredient_totals, delta, ComparisonNumericError,
)
from app.domain.decision.quantities import ServingNumericError


def _option(request,candidate,strategies):
    evaluation=candidate.evaluation
    products=product_totals(tuple(ProductObservation(r.path_id,r.product_id,r.unit,q(r.requested),q(r.fulfilled),q(r.lost))
                                  for r in evaluation.products))
    ingredients=ingredient_totals(tuple(IngredientObservation(r.path_id,r.day,r.ingredient_id,r.unit,
        q(r.shortage),q(r.ending),q(r.expired),q(r.other_waste)) for r in evaluation.ingredients),
        request.prepared.request.cutoff_date+timedelta(days=7))
    def values(row):
        return {k:(quantity(v) if k not in ('path','product_id','ingredient_id','unit') and v is not None else v)
                for k,v in asdict(row).items()}
    return ComparisonOption(token=option_token(request,candidate),identity_kind='INTERNAL_COMPARISON_TOKEN_NOT_PERSISTED',
        source_strategies=strategies,basket=candidate.basket,arrivals=candidate.arrivals,
        outlay=outlay_breakdown(request,candidate),products=tuple(ComparedProduct(**values(r)) for r in products),
        ingredients=tuple(ComparedIngredient(**values(r)) for r in ingredients),daily_products=daily_products(evaluation),
        daily_ingredients=daily_ingredients(evaluation),issues=issues(evaluation),
        provenance=request.prepared.source_references+request.source_references,hard_validity=candidate.hard_validity)


def _delta(before,after):
    # Same revalidated captured context guarantees these exact scope/unit keys agree.
    product_rows=[];ingredient_rows=[]
    for a,b in zip(before.products,after.products):
        if (a.path,a.product_id,a.unit)!=(b.path,b.product_id,b.unit):raise ValueError('Product delta scope/unit mismatch')
        product_rows.append(ProductDelta(path=a.path,product_id=a.product_id,unit=a.unit,
            fulfilled=signed(delta(q(a.fulfilled),q(b.fulfilled))),lost=signed(delta(q(a.lost),q(b.lost)))))
    for a,b in zip(before.ingredients,after.ingredients):
        if (a.path,a.ingredient_id,a.unit)!=(b.path,b.ingredient_id,b.unit):raise ValueError('Ingredient delta scope/unit mismatch')
        ingredient_rows.append(IngredientDelta(path=a.path,ingredient_id=a.ingredient_id,unit=a.unit,
            **{field:signed(delta(q(getattr(a,field)),q(getattr(b,field))))
               for field in ('daily_shortage_sum','horizon_ending','expired','other_waste')}))
    if before.outlay.currency!=after.outlay.currency:raise ValueError('Currency delta mismatch')
    return OptionDelta(from_token=before.token,to_token=after.token,currency=before.outlay.currency,
        total_outlay=signed(delta(q(before.outlay.total),q(after.outlay.total))),
        products=tuple(product_rows),ingredients=tuple(ingredient_rows))


def compare_procurement(request: ProcurementComparisonInput) -> ProcurementComparisonResult:
    request=ProcurementComparisonInput.model_validate(request)
    source=request.procurement;captured=source.input
    grouped={};plans={};outcomes=[];token_keys={}
    try:
        for row in source.strategies:
            candidate=row.best_target_met or row.best_available
            token=None
            if candidate is not None:
                token=option_token(captured,candidate)
                plan=plan_identity(captured,candidate)
                evaluation=evaluation_identity(candidate)
                key=plan,evaluation
                if token in token_keys and token_keys[token]!=key:
                    raise ValueError('Internal option token collision; comparison aborted without grouping distinct facts')
                token_keys[token]=key
                grouped.setdefault(key,(token,candidate,[]))[2].append(row.rule.strategy)
                plans.setdefault(plan,{}).setdefault(evaluation,[]).append((row.rule.strategy,token))
            fields=row.model_dump(exclude={'best_target_met','best_available'})
            outcomes.append(StrategyComparisonOutcome(option_token=token,**fields))
        options=tuple(_option(captured,candidate,tuple(strategies)) for token,candidate,strategies
                      in sorted(grouped.values(),key=lambda item:item[0]))
        diagnostics=[]
        for plan,variants in sorted(plans.items()):
            if len(variants)>1:
                sources=[entry for values in variants.values() for entry in values]
                diagnostics.append(ComparisonDiagnostic(code='SAME_PLAN_DIFFERENT_EVALUATION',
                    strategies=tuple(sorted({s for s,t in sources})),option_tokens=tuple(sorted({t for s,t in sources})),
                    detail='Same exact captured purchase/arrival plan has incompatible evaluated facts; kept separate without choosing which is authoritative'))
        deltas=tuple(_delta(a,b) for a,b in combinations(options,2))
        return ProcurementComparisonResult(semantics_version='procurement_comparison/1',input=request,
            status='COMPLETE_WITH_DIAGNOSTICS' if diagnostics else 'COMPLETE',options=options,outcomes=tuple(outcomes),
            deltas=deltas,diagnostics=tuple(diagnostics),delta_convention='TO_MINUS_FROM',decision_readiness='NOT_ASSESSED')
    except ServingNumericError as error:
        raise ComparisonNumericError('Comparison cannot represent exact aggregate/delta: '+str(error)) from error
