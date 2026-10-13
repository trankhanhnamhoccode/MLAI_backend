"""P01/P02/V01--V04 canonical projections, separate from internal writer DTOs."""

from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from pydantic import Field, model_serializer
from app.application.contracts.auth import DTO, Pagination, ErrorInfo

Quantity = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")]
SignedQuantity = Annotated[str, Field(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")]
Money = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$")]


class IssueDetails(DTO):
    entity: Literal["product", "ingredient", "inventory_lot"]
    entity_id: UUID
    field: str
    severity: Literal["WARNING", "DATA_ERROR"] = "WARNING"
    impact: str


class Notification(DTO):
    code: str
    message: str
    details: IssueDetails


class CatalogMeta(DTO):
    request_id: str
    observed_at: datetime
    as_of_date: date
    timezone: str
    updated_at: datetime | None
    data_version: str
    pagination: Pagination | None = None

    @model_serializer(mode="wrap")
    def serialize_meta(self, handler):
        result = handler(self)
        if self.pagination is None:
            result.pop("pagination", None)
        return result

    warnings: tuple[Notification, ...] = ()


class InventoryMeta(DTO):
    request_id: str
    as_of_date: date
    updated_at: datetime | None
    snapshot_id: str
    data_version: str
    pagination: Pagination | None = None

    @model_serializer(mode="wrap")
    def serialize_meta(self, handler):
        result = handler(self)
        if self.pagination is None:
            result.pop("pagination", None)
        return result


T = TypeVar("T")


class CatalogEnvelope(DTO, Generic[T]):
    data: T
    meta: CatalogMeta
    error: None


class InventoryEnvelope(DTO, Generic[T]):
    data: T
    meta: InventoryMeta
    error: None


class EmptyMeta(DTO):
    pass


class ReadErrorEnvelope(DTO):
    data: None
    meta: EmptyMeta
    error: ErrorInfo


class ProductFields(DTO):
    product_id: UUID
    sku: str | None
    name: str
    selling_unit: str
    selling_price: Money | None
    currency: str
    status: Literal["active", "paused"]


class ProductRow(ProductFields):
    ingredient_count: int | None
    ingredient_count_availability: Literal["available", "missing_recipe", "forbidden"]


class MenuSummary(DTO):
    product_count: int
    active_count: int
    paused_count: int


class Menu(DTO):
    summary: MenuSummary
    items: tuple[ProductRow, ...]


class RecipeIngredient(DTO):
    recipe_line_id: UUID
    ingredient_id: UUID
    ingredient_name: str
    ingredient_sku: str | None
    ingredient_active: bool
    expiry_tracking: bool
    base_unit: str
    quantity: Quantity
    unit: str


class RecipeRead(DTO):
    recipe_id: UUID
    version: int
    effective_from: date
    effective_to: date | None
    yield_quantity: Quantity
    yield_unit: str
    process_loss_rate: Quantity
    ingredients: tuple[RecipeIngredient, ...]


class ProductDetail(ProductFields):
    recipe: RecipeRead | None


class LowStock(DTO):
    status: Literal["low", "ok", "unknown"]
    threshold: Quantity | None
    version: str | None


StockStatus = Literal["expired", "empty", "low_stock", "near_expiry", "watch", "stable"]


class IngredientStock(DTO):
    ingredient_id: UUID
    name: str
    sku: str | None
    ingredient_active: bool
    unit: str
    on_hand_quantity: Quantity
    usable_quantity: Quantity | None
    usable_known_quantity: Quantity
    usable_availability: Literal["known", "unknown"]
    expired_quantity: Quantity
    stock_completeness: Literal["CONFIRMED", "UNKNOWN"]
    lot_count: int
    positive_lot_count: int
    nearest_expiry: date | None
    status: StockStatus
    status_reasons: tuple[Notification, ...]
    low_stock_assessment: LowStock
    near_expiry_lot_count: int


class InventorySummary(DTO):
    ingredient_count: int
    positive_lot_count: int
    near_expiry_lot_count: int
    near_expiry_ingredient_count: int
    expired_lot_count: int
    low_stock_ingredient_count: int | None
    unknown_assessment_ingredient_count: int


class InventoryList(DTO):
    summary: InventorySummary
    items: tuple[IngredientStock, ...]
    missing_ingredient_ids: tuple[UUID, ...]


class LotCost(DTO):
    availability: Literal["known", "unknown", "forbidden"]
    unit_cost: Money | None
    currency: str


class LotRead(DTO):
    lot_id: UUID
    batch_code: str | None
    quantity: Quantity
    unit: str
    supplier_id: UUID | None
    received_date: date | None
    expiry_date: date | None
    status: Literal["empty", "expired", "near_expiry", "watch", "stable"]
    use_first: bool
    location: None
    location_availability: Literal["unsupported"]
    updated_at: datetime
    version: str
    origin: Literal["OPENING_STOCK", "ACTUAL_RECEIPT", "UNKNOWN"]
    cost: LotCost


class LotsPage(DTO):
    next_cursor: str | None
    total_count: int


class InventoryDetail(IngredientStock):
    lots: tuple[LotRead, ...]
    lots_page: LotsPage
    threshold_version: str


class Lots(DTO):
    ingredient_id: UUID
    items: tuple[LotRead, ...]


class MovementReference(DTO):
    type: str
    id: str


class MovementRead(DTO):
    movement_id: UUID
    lot_id: UUID
    batch_code: str | None
    kind: Literal[
        "receipt", "usage", "waste", "expired", "count_correction", "manual_adjustment"
    ]
    quantity_delta: SignedQuantity
    unit: str
    occurred_at: datetime
    recorded_at: datetime
    actor_user_id: UUID | None
    reason: str | None
    reference: MovementReference | None
    origin: Literal["OPENING_STOCK", "ACTUAL_RECEIPT", "IMPORT_COUNT", "UNKNOWN"]


class Movements(DTO):
    ingredient_id: UUID
    items: tuple[MovementRead, ...]
