"""Typed retained report input; no live business lookups or arbitrary HTML."""
from app.application.contracts.auth import DTO
from app.application.contracts.planning_public import RunView,Option
from app.application.contracts.planning_inspection import IngredientDetail,Explanation
from app.application.contracts.planning_source_evidence import PlanningSourceEvidence


class PlanningPDFDocument(DTO):
    view: RunView
    option: Option
    ingredients: tuple[IngredientDetail,...]
    explanation: Explanation
    source_evidence: PlanningSourceEvidence | None
