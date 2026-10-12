"""Reconcile comparison projections with both ends and retained source evidence."""
from datetime import timedelta
from fractions import Fraction as F
from itertools import combinations
from app.application.procurement_comparison_facts import (
    q, option_token, plan_identity, evaluation_identity, outlay_breakdown, daily_products, daily_ingredients, issues,
)
from app.domain.decision.quantities import checked


def _sum(values):
    return checked(sum(values,F(0)))


def validate_comparison(result):
    source=result.input.procurement;request=source.input
    tokens=[o.token for o in result.options]
    if tokens!=sorted(set(tokens)):raise ValueError('Comparison option tokens must be unique/canonical')
    outcomes={r.rule.strategy:r for r in result.outcomes}
    if len(outcomes)!=3 or tuple(r.rule.strategy for r in result.outcomes)!=tuple(r.rule.strategy for r in source.strategies):
        raise ValueError('Every source strategy requires separate canonical outcome')
    candidates={};members={};plans={};token_keys={}
    for row in source.strategies:
        candidate=row.best_target_met or row.best_available
        token=None if candidate is None else option_token(request,candidate)
        outcome=outcomes[row.rule.strategy]
        if outcome.option_token!=token or outcome.model_dump(exclude={'option_token'})!=row.model_dump(exclude={'best_target_met','best_available'}):
            raise ValueError('Comparison must preserve every strategy target/proof/diagnostic and evidence')
        if candidate:
            key=plan_identity(request,candidate),evaluation_identity(candidate)
            if token in token_keys and token_keys[token]!=key:raise ValueError('Internal comparison token collision')
            token_keys[token]=key
            candidates[token]=candidate;members.setdefault(token,[]).append(row.rule.strategy)
            plans.setdefault(plan_identity(request,candidate),{}).setdefault(evaluation_identity(candidate),[]).append((row.rule.strategy,token))
    if set(tokens)!=set(candidates):raise ValueError('No invented, missing or dropped candidate options')
    for option in result.options:
        candidate=candidates[option.token];e=candidate.evaluation
        if option.source_strategies!=tuple(members[option.token]):raise ValueError('Grouped strategies/provenance mismatch')
        if option.basket!=candidate.basket or option.arrivals!=candidate.arrivals or option.outlay!=outlay_breakdown(request,candidate):
            raise ValueError('Option plan/captured outlay/fees mismatch')
        if option.daily_products!=daily_products(e) or option.daily_ingredients!=daily_ingredients(e) or option.issues!=issues(e):
            raise ValueError('Option must preserve exact evaluated rows and issues')
        if option.provenance!=request.prepared.source_references+request.source_references:
            raise ValueError('Option provenance lost or altered')
        expected_products=[]
        for path in sorted(('LOW','BASE','HIGH')):
            for product in request.prepared.products:
                rows=[r for r in e.products if r.path_id==path and r.product_id==product.product_id]
                requested=_sum(q(r.requested) for r in rows);served=_sum(q(r.fulfilled) for r in rows);lost=_sum(q(r.lost) for r in rows)
                expected_products.append((path,product.product_id,product.selling_unit,requested,served,lost,None if not requested else checked(served/requested)))
        actual=[(r.path,r.product_id,r.unit,q(r.requested),q(r.fulfilled),q(r.lost),None if r.service is None else q(r.service)) for r in option.products]
        if actual!=expected_products:raise ValueError('Product metrics/coverage/unit mismatch')
        expected_ingredients=[]
        end_day=request.prepared.request.cutoff_date+timedelta(days=7)
        for path in sorted(('LOW','BASE','HIGH')):
            for ingredient in request.prepared.ingredients:
                rows=[r for r in e.ingredients if r.path_id==path and r.ingredient_id==ingredient.ingredient_id]
                end=next(r for r in rows if r.day==end_day)
                expected_ingredients.append((path,ingredient.ingredient_id,ingredient.unit,_sum(q(r.shortage) for r in rows),q(end.ending),
                    _sum(q(r.expired) for r in rows),_sum(q(r.other_waste) for r in rows)))
        actual=[(r.path,r.ingredient_id,r.unit,q(r.daily_shortage_sum),q(r.horizon_ending),q(r.expired),q(r.other_waste)) for r in option.ingredients]
        if actual!=expected_ingredients:raise ValueError('Ingredient metrics/coverage/unit mismatch')
    expected_pairs=[(a.token,b.token) for a,b in combinations(result.options,2)]
    if [(d.from_token,d.to_token) for d in result.deltas]!=expected_pairs:
        raise ValueError('Delta requires every canonical unordered pair exactly once')
    options={o.token:o for o in result.options}
    for d in result.deltas:
        before=options[d.from_token];after=options[d.to_token]
        if d.currency!=before.outlay.currency or d.currency!=after.outlay.currency or q(d.total_outlay)!=checked(q(after.outlay.total)-q(before.outlay.total)):
            raise ValueError('Delta currency/total must reconcile B minus A')
        expected=[(a.path,a.product_id,a.unit,checked(q(b.fulfilled)-q(a.fulfilled)),checked(q(b.lost)-q(a.lost))) for a,b in zip(before.products,after.products)]
        actual=[(r.path,r.product_id,r.unit,q(r.fulfilled),q(r.lost)) for r in d.products]
        if actual!=expected:raise ValueError('Product delta coverage/value mismatch')
        fields=('daily_shortage_sum','horizon_ending','expired','other_waste')
        expected=[(a.path,a.ingredient_id,a.unit,*(checked(q(getattr(b,f))-q(getattr(a,f))) for f in fields)) for a,b in zip(before.ingredients,after.ingredients)]
        actual=[(r.path,r.ingredient_id,r.unit,*(q(getattr(r,f)) for f in fields)) for r in d.ingredients]
        if actual!=expected:raise ValueError('Ingredient delta coverage/value mismatch')
    expected=[]
    for plan,variants in sorted(plans.items()):
        if len(variants)>1:
            entries=[entry for values in variants.values() for entry in values]
            expected.append((tuple(sorted({s for s,t in entries})),tuple(sorted({t for s,t in entries}))))
    if [(d.strategies,d.option_tokens) for d in result.diagnostics]!=expected:
        raise ValueError('Incompatible evaluations require separate options and diagnostic')
    if result.status!=('COMPLETE_WITH_DIAGNOSTICS' if expected else 'COMPLETE'):
        raise ValueError('Comparison status must reflect grouping diagnostics')
