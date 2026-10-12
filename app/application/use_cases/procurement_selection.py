"""Group exact procurement/2 facts then select; no solver/DB/provider call."""
from itertools import combinations
from fractions import Fraction as F
from app.application.contracts.procurement_v2 import ProcurementResultV2
from app.application.contracts.procurement_selection import ComparisonV2, StrategyBinding, WinnerSelection, CandidateRejection
from app.application.contracts.procurement_comparison import ComparisonDiagnostic
from app.application.procurement_comparison_facts import plan_identity, evaluation_identity, option_token, q
from app.application.use_cases.procurement_comparison import _option, _delta
from app.application.use_cases.procurement_v2 import candidate_gaps, passed, stable_basket
from app.domain.decision.procurement_policy import service_summary, winner_key


def projected(source):
    grouped={};plans={};bindings=[]
    for row in source.strategies:
        c=row.candidate;token=None
        if c is not None:
            token=option_token(source.input,c)
            plan=plan_identity(source.input,c);evaluation=evaluation_identity(c)
            key=plan,evaluation
            grouped.setdefault(key,(token,c,[]))[2].append(row.strategy)
            plans.setdefault(plan,{}).setdefault(evaluation,[]).append((row.strategy,token))
        bindings.append(StrategyBinding(strategy=row.strategy,option_token=token))
    options=tuple(_option(source.input,c,tuple(strategies)) for token,c,strategies in
                  sorted(grouped.values(),key=lambda v:v[0]))
    if len({o.token for o in options})!=len(options):raise ValueError('Option identity collision')
    diagnostics=[]
    for plan,variants in plans.items():
        if len(variants)>1:
            sources=[x for rows in variants.values() for x in rows]
            diagnostics.append(ComparisonDiagnostic(code='SAME_PLAN_DIFFERENT_EVALUATION',
                strategies=tuple(sorted({s for s,t in sources})),option_tokens=tuple(sorted({t for s,t in sources})),
                detail='Same plan with distinct exact evaluation; separate options, evidence not promoted'))
    return options,tuple(bindings),tuple(_delta(a,b) for a,b in combinations(options,2)),tuple(diagnostics)


def validate_comparison(result):
    if (result.options,result.bindings,result.deltas,result.diagnostics)!=projected(result.source):
        raise ValueError('Comparison does not preserve captured grouping/facts/evidence')


def compare_procurement_v2(source: ProcurementResultV2) -> ComparisonV2:
    source=ProcurementResultV2.model_validate(source)
    options,bindings,deltas,diagnostics=projected(source)
    return ComparisonV2(semantics_version='procurement_comparison/2',source=source,
                        options=options,bindings=bindings,deltas=deltas,diagnostics=diagnostics)


def selection_facts(comparison):
    source=comparison.source
    by_token={option_token(source.input,r.candidate):r.candidate for r in source.strategies if r.candidate}
    eligible=[];rejected=[]
    for option in comparison.options:
        candidate=by_token[option.token];reasons=[]
        if any(i.kind in ('DATA_BLOCKER','HARD_VIOLATION') for i in option.issues):reasons.append('RELATED_BLOCKER')
        if not passed(candidate_gaps(source.input,candidate)):reasons.append('CUSTOMER_REQUIREMENTS_NOT_MET')
        if reasons:rejected.append(CandidateRejection(option_token=option.token,reasons=tuple(reasons)))
        else:eligible.append(option)
    def key(option):
        minima=tuple(service_summary((q(p.requested),q(p.fulfilled)) for p in option.products if p.path==path)[0]
                     for path in ('HIGH','BASE','LOW'))
        return winner_key(minima,q(option.outlay.total),stable_basket(by_token[option.token]))
    ordered=sorted(eligible,key=key)
    return (ordered[0].token if ordered else None,tuple(o.token for o in ordered),tuple(rejected),
            'WINNER_FOUND' if ordered else 'NO_ELIGIBLE_CANDIDATE')


def select_winner(comparison: ComparisonV2) -> WinnerSelection:
    comparison=ComparisonV2.model_validate(comparison)
    winner,tokens,rejected,reason=selection_facts(comparison)
    return WinnerSelection(semantics_version='procurement_selector/1',comparison=comparison,
        winner_token=winner,eligible_tokens=tokens,rejected=rejected,
        proof='BEST_EVALUATED_CANDIDATES_ONLY',reason=reason)
