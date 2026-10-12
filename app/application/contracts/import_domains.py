"""Discriminated source/preview schemas; missing facts never default to zero."""

from datetime import date, datetime
from typing import Literal, Annotated
from uuid import UUID
from decimal import Decimal
from pydantic import Field, StrictBool, StrictInt, model_validator
from app.application.contracts.import_scalars import ImportDTO as DTO
from app.application.contracts.import_scalars import (
    Quantity,
    Money,
    Text,
    ProductMetadata,
    IngredientMetadata,
    SupplierMetadata,
)


class SalesSource(DTO):
    domain: Literal["sales"] = "sales"
    product_id: UUID
    sales_date: date
    quantity: Quantity
    unit: str
    business_report_key: Text


class CountSource(DTO):
    domain: Literal["inventory_count"] = "inventory_count"
    ingredient_id: UUID
    lot_id: UUID
    on_hand: Quantity
    unit: str
    observed_at: datetime
    reason: Text

    @model_validator(mode="after")
    def aware(self):
        if self.observed_at.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        return self


class RecipeSource(DTO):
    domain: Literal["recipes"] = "recipes"
    product_id: UUID
    version: StrictInt = Field(ge=1, le=2147483647)
    effective_from: date
    effective_to: date | None
    yield_quantity: Quantity
    yield_unit: str
    process_loss_rate: Quantity
    ingredient_id: UUID
    quantity: Quantity
    unit: str

    @model_validator(mode="after")
    def values(self):
        if (
            Decimal(self.yield_quantity) <= 0
            or Decimal(self.quantity) <= 0
            or Decimal(self.process_loss_rate) >= 1
        ):
            raise ValueError("INVALID_RECIPE_QUANTITY")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("INVALID_PERIOD")
        return self


class RecipeLineValue(DTO):
    ingredient_id: UUID
    quantity: Quantity
    unit: str


class RecipeValue(DTO):
    domain: Literal["recipes"] = "recipes"
    product_id: UUID
    version: int
    effective_from: date
    effective_to: date | None
    yield_quantity: Quantity
    yield_unit: str
    process_loss_rate: Quantity
    lines: tuple[RecipeLineValue, ...]


class ProductSource(ProductMetadata):
    domain: Literal["products"] = "products"
    source_business_key: Text


class IngredientSource(IngredientMetadata):
    domain: Literal["ingredients"] = "ingredients"
    source_business_key: Text


class SupplierSource(SupplierMetadata):
    domain: Literal["suppliers"] = "suppliers"
    source_supplier_key: Text


class TermSource(DTO):
    domain: Literal["supplier_terms"] = "supplier_terms"
    source_term_key: Text
    supplier_id: UUID
    ingredient_id: UUID
    effective_from: date
    effective_to: date | None
    unit: str
    pack_size_base_quantity: Quantity
    pack_cost: Money
    currency: str
    minimum_order_packs: StrictInt = Field(ge=1, le=2147483647)
    lead_time_days: StrictInt = Field(ge=0, le=2147483647)
    shelf_life_days: StrictInt | None = Field(ge=0, le=2147483647)
    active: StrictBool
    maximum_order_base_quantity: Quantity | None

    @model_validator(mode="after")
    def period(self):
        if Decimal(self.pack_size_base_quantity) <= 0:
            raise ValueError("INVALID_PACK_SIZE")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("INVALID_PERIOD")
        return self


class FeeComponent(DTO):
    component_key: Text
    label: Text
    basis: Literal["PER_OFFER", "PER_SUPPLIER_ORDER"]
    source_term_key: Text | None
    source_supplier_key: Text | None
    amount: Money
    condition: Literal["WHEN_ORDERED"]

    @model_validator(mode="after")
    def ref(self):
        if self.basis == "PER_OFFER" and (
            not self.source_term_key or self.source_supplier_key is not None
        ):
            raise ValueError("INVALID_FEE_REFERENCE")
        if self.basis == "PER_SUPPLIER_ORDER" and (
            not self.source_supplier_key or self.source_term_key is not None
        ):
            raise ValueError("INVALID_FEE_REFERENCE")
        return self


class FeeSource(DTO):
    domain: Literal["payable_fees"] = "payable_fees"
    source_fee_key: Text
    scope: Literal["STORE_PROCUREMENT"]
    effective_from: date
    effective_to: date | None
    mode: Literal["NONE", "PER_OFFER", "PER_SUPPLIER_ORDER"]
    coverage: Literal["COMPLETE", "UNKNOWN"]
    currency: str
    components: tuple[FeeComponent, ...]
    covered_source_term_keys: tuple[Text, ...]
    covered_source_supplier_keys: tuple[Text, ...]
    evidence_reference: Text
    reason: Text

    @model_validator(mode="after")
    def values(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("INVALID_PERIOD")
        if self.mode == "NONE" and (self.components or self.coverage != "COMPLETE"):
            raise ValueError("INVALID_NONE_FEE")
        if any(c.basis != self.mode for c in self.components):
            raise ValueError("UNSUPPORTED_FEE_RULE")
        if len({c.component_key for c in self.components}) != len(self.components):
            raise ValueError("DUPLICATE_FEE_COMPONENT")
        return self


class InventoryDeclaration(DTO):
    kind: Literal["INVENTORY"]
    ingredient_id: UUID
    state: Literal["COMPLETE_CURRENT_LOTS", "CONFIRMED_EMPTY", "UNKNOWN"]
    observed_at: datetime
    covered_lot_ids: tuple[UUID, ...]
    evidence_reference: Text

    @model_validator(mode="after")
    def aware(self):
        if self.observed_at.utcoffset() is None:
            raise ValueError("TIMEZONE_REQUIRED")
        if len(set(self.covered_lot_ids)) != len(self.covered_lot_ids):
            raise ValueError("DUPLICATE_LOT_ID")
        return self


class SalesDeclaration(DTO):
    kind: Literal["SALES_COVERAGE"]
    product_ids: tuple[UUID, ...]
    from_date: date
    to_date: date
    state: Literal["COMPLETE", "PARTIAL", "UNKNOWN"]
    evidence_reference: Text

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("DUPLICATE_PRODUCT_SCOPE")
        return self


class Capacity(DTO):
    ingredient_id: UUID
    unit: str
    maximum_quantity: Quantity
    checkpoint: Literal["POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION"]


class SupplierLimit(DTO):
    supplier_id: UUID
    ingredient_id: UUID
    unit: str
    maximum_quantity: Quantity
    scope: Literal["ONE_ORDER_SUPPLIER_INGREDIENT"]


class ProcurementDeclaration(DTO):
    kind: Literal["PROCUREMENT_CONTEXT"]
    effective_from: date
    effective_to: date | None
    committed_inbound_state: Literal["CONFIRMED_NONE", "PRESENT_UNSUPPORTED", "UNKNOWN"]
    no_additional_orders_state: Literal["CONFIRMED_NONE", "UNKNOWN"]
    capacity_state: Literal["DECLARED", "EXPLICIT_NOT_CONFIGURED", "UNKNOWN"]
    capacities: tuple[Capacity, ...]
    supplier_limit_state: Literal["DECLARED", "EXPLICIT_NOT_CONFIGURED", "UNKNOWN"]
    supplier_limits: tuple[SupplierLimit, ...]
    evidence_reference: Text

    @model_validator(mode="after")
    def declared(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("INVALID_PERIOD")
        if len({c.ingredient_id for c in self.capacities}) != len(self.capacities):
            raise ValueError("DUPLICATE_CAPACITY")
        if len({(c.supplier_id, c.ingredient_id) for c in self.supplier_limits}) != len(
            self.supplier_limits
        ):
            raise ValueError("DUPLICATE_SUPPLIER_LIMIT")
        for state, values in (
            (self.capacity_state, self.capacities),
            (self.supplier_limit_state, self.supplier_limits),
        ):
            if (state == "DECLARED") != bool(values):
                raise ValueError("INVALID_DECLARATION_SCOPE")
        return self


class DeclarationSource(DTO):
    domain: Literal["scope_declarations"] = "scope_declarations"
    source_declaration_key: Text
    declaration: Annotated[
        InventoryDeclaration | SalesDeclaration | ProcurementDeclaration,
        Field(discriminator="kind"),
    ]


SourceValue = Annotated[
    SalesSource
    | CountSource
    | RecipeSource
    | ProductSource
    | IngredientSource
    | SupplierSource
    | TermSource
    | FeeSource
    | DeclarationSource,
    Field(discriminator="domain"),
]


class TermValue(TermSource):
    # Existing canonical rows do not have an import source identity; retain null.
    source_term_key: Text | None


CanonicalValue = Annotated[
    SalesSource
    | CountSource
    | RecipeValue
    | ProductSource
    | IngredientSource
    | SupplierSource
    | TermValue
    | FeeSource
    | DeclarationSource,
    Field(discriminator="domain"),
]
SOURCE_MODELS = {
    "sales": SalesSource,
    "inventory_count": CountSource,
    "recipes": RecipeSource,
    "products": ProductSource,
    "ingredients": IngredientSource,
    "suppliers": SupplierSource,
    "supplier_terms": TermSource,
    "payable_fees": FeeSource,
    "scope_declarations": DeclarationSource,
}
