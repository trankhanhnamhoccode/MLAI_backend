"""Concrete v2 search port; no infrastructure imports."""
from dataclasses import dataclass
from typing import Protocol
from app.application.contracts.procurement_v2 import SolverEvidenceV2
from app.application.contracts.procurement import ProcurementCandidate


@dataclass(frozen=True)
class ProposalV2:
    evidence: SolverEvidenceV2
    counts: tuple[int, ...] | None


class ProductCandidateSearch(Protocol):
    def solve(self, strategy: str, phase: str, deadline: float) -> ProposalV2: ...
    def accept(self, strategy: str, phase: str, candidate: ProcurementCandidate) -> None: ...
    def exclude(self, counts: tuple[int, ...], *, phase: str, hard_invalid: bool,
                customer_invalid: bool) -> None: ...
