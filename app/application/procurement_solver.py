"""Small synchronous candidate-search port for the concrete internal use case."""
from dataclasses import dataclass
from typing import Protocol, Literal
from app.application.contracts.procurement import ConstructionRule, SolverEvidence


class NumericUnsupported(ValueError):
    """Exact input cannot be safely admitted by the configured float projection."""


@dataclass(frozen=True)
class SolverProposal:
    evidence: SolverEvidence
    counts: tuple[int, ...] | None


class CandidateSearch(Protocol):
    def solve(self, rule: ConstructionRule, phase: Literal['TARGET', 'FALLBACK_SERVICE', 'FALLBACK_COST'],
              deadline: float) -> SolverProposal: ...
    def exclude(self, counts: tuple[int, ...], *, phase: str, hard_invalid: bool) -> None: ...
