"""BOM-only output; computation success does not assert whole-Decision readiness."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import model_validator
from app.application.contracts.common import Contract, NonnegativeDecimal, Unit
from app.application.contracts.decision_execution import DecisionIssue, PreparedDecisionInput, VersionOne
from app.application.contracts.decision_package import BOMContribution, PathId, ProductDemandPath


class IngredientDemandTotal(Contract):
    path_id: PathId
    day: date
    ingredient_id: UUID
    unit: Unit
    quantity: NonnegativeDecimal


class BOMIssue(DecisionIssue):
    day: date | None = None
    path_id: PathId | None = None


class BOMExpansionResult(Contract):
    schema_version: VersionOne = 1
    bom_version: Literal['dated_bom/1'] = 'dated_bom/1'
    status: Literal['COMPLETE', 'DATA_BLOCKED', 'ARITHMETIC_BLOCKED']
    decision_readiness: Literal['DATA_BLOCKED', 'NOT_ASSESSED']
    prepared: PreparedDecisionInput
    paths: tuple[ProductDemandPath, ...]
    contributions: tuple[BOMContribution, ...]
    totals: tuple[IngredientDemandTotal, ...]
    issues: tuple[BOMIssue, ...]

    @model_validator(mode='after')
    def honest_status(self):
        blocked = any(i.kind == 'DATA_BLOCKER' for i in self.issues)
        if blocked != (self.decision_readiness == 'DATA_BLOCKED'):
            raise ValueError('Known blockers must remain visible in Decision readiness')
        if self.status != 'COMPLETE':
            if not blocked or self.paths or self.contributions or self.totals:
                raise ValueError('Blocked BOM must not return partial successful quantities')
        elif tuple(p.path_id for p in self.paths) != ('LOW', 'BASE', 'HIGH'):
            raise ValueError('Complete BOM requires all three Product paths')
        return self
