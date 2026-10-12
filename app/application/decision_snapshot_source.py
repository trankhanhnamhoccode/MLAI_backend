"""Small synchronous port. Store scoping is not actor authorization."""
from datetime import datetime
from typing import Callable, Protocol

from app.application.contracts.decision_capture import OperationalDecisionInput, OperationalFacts, CaptureProblem


class OperationalDataError(Exception):
    """Known malformed source data; transport/programming errors are not this type."""
    def __init__(self, problems: tuple[CaptureProblem, ...], captured_at: datetime):
        self.problems, self.captured_at = problems, captured_at
        super().__init__('Operational data cannot be captured: ' + ', '.join(p.code for p in problems))


class DecisionSnapshotSource(Protocol):
    def read(self, request: OperationalDecisionInput, clock: Callable[[], datetime]) -> OperationalFacts:
        """One consistent snapshot; return by value after closing owned resources.

        Never accept/change caller transactions. clock marks the observed snapshot,
        not a historical inventory availability query.
        """
        ...
