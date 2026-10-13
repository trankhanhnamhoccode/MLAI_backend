"""PLAN15.3/16 retained inspection; result nullability decision S410."""
from datetime import date
from typing import Generic,TypeVar,Literal
from uuid import UUID
from pydantic import AwareDatetime,model_serializer
from app.application.contracts.auth import DTO,Pagination
from app.application.contracts.planning_setup import Version,MoneyText
from app.application.contracts.planning_public import (
    OptionId,ExactQuantity,IngredientBalance,PlanningNotification,Purchase,Path,Strategy,StrategyResult,
)

Selection=Literal['winner','explicit','not_selected']


class InspectionMeta(DTO):
    request_id: str
    run_id: UUID
    result_digest: Version | None
    response_version: Version
    pagination: Pagination | None=None

    @model_serializer(mode='wrap')
    def present(self,handler):
        result=handler(self)
        if self.pagination is None:result.pop('pagination',None)
        return result


T=TypeVar('T')
class InspectionEnvelope(DTO,Generic[T]):
    data: T
    meta: InspectionMeta
    error: None


class IngredientResultRow(DTO):
    ingredient_id: UUID
    unit: str
    display_name: str | None
    name_availability: Literal['captured','not_captured']
    purchase_quantity: ExactQuantity | None
    purchase_line_count: int | None
    path_balances: tuple[IngredientBalance,...] | None
    issues: tuple[PlanningNotification,...]
    detail_available: bool


class IngredientNavigator(DTO):
    run_id: UUID
    result_digest: Version | None
    selected_option_id: OptionId | None
    selection_status: Selection
    items: tuple[IngredientResultRow,...]


class CapturedLot(DTO):
    lot_id: UUID
    quantity: ExactQuantity
    unit: str
    received_date: date | None
    expiry_date: date | None
    supplier_id: UUID | None
    unit_cost: MoneyText | None
    cost_availability: Literal['known','unknown']


class CapturedStock(DTO):
    captured_at: AwareDatetime
    lots: tuple[CapturedLot,...]
    scope_declaration: Literal['COMPLETE_CURRENT_LOTS','CONFIRMED_EMPTY','UNKNOWN']
    provenance: str | None


class IngredientDay(DTO):
    path: Path
    day: date
    unit: str
    requested: ExactQuantity
    available: ExactQuantity
    shortage: ExactQuantity
    consumed: ExactQuantity
    expired: ExactQuantity
    other_waste: ExactQuantity
    ending: ExactQuantity
    incoming_quantity: ExactQuantity


class FulfilledContribution(DTO):
    path: Path
    day: date
    quantity: ExactQuantity


class ProductDependency(DTO):
    product_id: UUID
    selling_unit: str
    ingredient_unit: str
    recipe_ids: tuple[UUID,...]
    affected_dates: tuple[date,...]
    fulfilled_contributions: tuple[FulfilledContribution,...] | None


class IngredientDetail(DTO):
    run_id: UUID
    result_digest: Version | None
    ingredient_id: UUID
    unit: str
    selected_option_id: OptionId | None
    selection_status: Selection
    display_name: str | None
    name_availability: Literal['captured','not_captured']
    captured_stock: CapturedStock
    purchases: tuple[Purchase,...] | None
    daily_balances: tuple[IngredientDay,...] | None
    related_products: tuple[ProductDependency,...]
    issues: tuple[PlanningNotification,...]
    evidence_availability: Literal['known','partial','not_evaluated']


class ExplanationWinner(DTO):
    option_id: OptionId | None
    reason_code: str


class ExcludedProduct(DTO):
    product_id: UUID
    reason_codes: tuple[str,...]
    affected_dates: tuple[date,...]


class OptionReason(DTO):
    option_id: OptionId
    eligible: bool
    rejection_reasons: tuple[str,...]
    not_selected_reason: str | None
    source_strategies: tuple[Strategy,...]
    evidence: tuple[StrategyResult,...]


class Explanation(DTO):
    run_id: UUID
    result_schema_version: str | None
    result_digest: Version | None
    availability: Literal['available','partial','unavailable']
    outcome: str | None
    winner: ExplanationWinner
    exclusions: tuple[ExcludedProduct,...]
    blockers: tuple[PlanningNotification,...]
    warnings: tuple[PlanningNotification,...]
    options: tuple[OptionReason,...]
    evidence_availability: Literal['known','unknown','not_evaluated']


class ExplanationMeta(DTO):
    request_id: str


class ExplanationEnvelope(DTO):
    data: Explanation
    meta: ExplanationMeta
    error: None
