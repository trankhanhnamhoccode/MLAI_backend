"""Whole resolver/pipeline native witnesses and independent tiny-domain proof."""
from fractions import Fraction

from scripts.planning_verification_cases import independent_oracle, run_case


def exact(q):
    return Fraction(int(q.numerator), int(q.denominator))


def winner(result):
    token=result.selection.winner_token
    assert token is not None and token in result.selection.eligible_tokens
    return next(o for o in result.comparison.options if o.token==token)


def test_BASE95_stock_zero_purchase_winner_whole_pipeline():
    resolved,result,calls=run_case('stock')
    assert resolved.resolution.requirements.paths[0].minimum.as_integer_ratio()==(19,20)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert exact(winner(result).outlay.total)==0
    assert calls==0  # Exact zero baseline shortcut, not a fabricated selector input.
    for s in result.procurement.strategies:
        assert s.customer_pass and s.construction_pass
        assert s.candidate.counts==(0,0) and exact(s.candidate.outlay)==0
        for metric in s.candidate.services:
            assert exact(metric.served)==exact(metric.requested)
    assert independent_oracle('stock')['minimum_outlay']==0


def test_BASE95_purchase_native_matches_independent_exhaustive_oracle():
    oracle=independent_oracle('purchase')
    assert oracle['passing']==[dict(counts=(2,2),outlay=10,hard_valid=True,customer_pass=True,served=('10','20'))]
    resolved,result,calls=run_case('purchase')
    assert result.procurement.input.policy.certification=='DISABLED'
    assert calls==3 and all(s.solver for s in result.procurement.strategies)
    assert result.outcome=='RECOMMENDATION_AVAILABLE'
    assert exact(winner(result).outlay.total)==oracle['minimum_outlay']
    for s in result.procurement.strategies:
        # Keep these expected values unchanged if native has a discrepancy.
        assert s.customer_pass and s.construction_pass
        assert s.candidate.counts==(2,2) and exact(s.candidate.outlay)==oracle['minimum_outlay']
        for metric in s.candidate.services:
            assert exact(metric.served)>=Fraction(19,20)*exact(metric.requested)
        assert s.customer_feasibility=='PASS_EXISTS' and s.proof=='UNPROVEN'


def test_BASE95_insufficient_budget_complete_finite_no_pass_certificate():
    oracle=independent_oracle('infeasible')
    assert oracle['evaluated']==9 and oracle['passing']==[]
    _,result,calls=run_case('infeasible')
    assert calls==3 and result.outcome=='NO_ELIGIBLE_CANDIDATE'
    assert result.selection.winner_token is None and result.selection.eligible_tokens==()
    for s in result.procurement.strategies:
        assert s.customer_feasibility=='NO_PASS_CERTIFIED'
        assert s.construction_feasibility=='NO_PASS_CERTIFIED'
        assert s.execution=='FINISHED' and s.search_complete and s.enumerated_vectors==9
        assert s.proof=='COMPLETE_EXACT_ENUMERATION' and s.proof_scope==oracle['scope']
        assert s.domain_size==9 and not s.customer_pass
