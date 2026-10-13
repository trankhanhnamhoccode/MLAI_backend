"""Owned detached /2 port. Store scoping is not actor authorization."""
from datetime import datetime
from typing import Callable, Protocol
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2


class DecisionSnapshotSourceV2(Protocol):
    def read(self, request: OperationalDecisionInputV2, clock: Callable[[], datetime]) -> OperationalFactsV2:
        """Capture all active menu and operational facts in one snapshot; close before return."""
        ...
