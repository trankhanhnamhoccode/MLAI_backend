"""comparison/2 and selector/1. No persisted API resource or purchase mutation."""
from typing import Literal
from pydantic import model_validator, ValidationInfo
from app.application.contracts.common import Contract, Strategy, Nonblank
from app.application.contracts.procurement_v2 import ProcurementResultV2
from app.application.contracts.procurement_comparison import ComparisonOption, OptionDelta, ComparisonDiagnostic, Token


class StrategyBinding(Contract):
    strategy: Strategy
    option_token: Token | None


class ComparisonV2(Contract):
    semantics_version: Literal['procurement_comparison/2']
    source: ProcurementResultV2
    options: tuple[ComparisonOption, ...]
    bindings: tuple[StrategyBinding, ...]
    deltas: tuple[OptionDelta, ...]
    diagnostics: tuple[ComparisonDiagnostic, ...]

    @model_validator(mode='after')
    def reconcile(self):
        from app.application.use_cases.procurement_selection import validate_comparison
        validate_comparison(self)
        return self


class CandidateRejection(Contract):
    option_token: Token
    reasons: tuple[Nonblank, ...]


class WinnerSelection(Contract):
    semantics_version: Literal['procurement_selector/1']
    comparison: ComparisonV2
    winner_token: Token | None
    eligible_tokens: tuple[Token, ...]
    rejected: tuple[CandidateRejection, ...]
    proof: Literal['BEST_EVALUATED_CANDIDATES_ONLY']
    reason: Literal['WINNER_FOUND', 'NO_ELIGIBLE_CANDIDATE']

    @model_validator(mode='after')
    def reconcile(self, info: ValidationInfo):
        if info.context and info.context.get('retained_consistency'):
            from app.application.retained_decision_validation import validate_selection
            validate_selection(self)
            return self
        from app.application.use_cases.procurement_selection import selection_facts
        expected=selection_facts(self.comparison)
        if (self.winner_token,self.eligible_tokens,self.rejected,self.reason)!=expected:
            raise ValueError('Winner does not match exact eligibility/ranking')
        return self
