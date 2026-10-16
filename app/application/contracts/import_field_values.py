"""Explicit scalar declarations and reviewed source rules, not row defaults."""

from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from app.application.contracts.import_scalars import ImportDTO, Text
from app.application.contracts.import_domains import SOURCE_MODELS

BOTH = {
    "calendar_events": (),
    "promotion_observations": (),
    "usage_history": ("unit",),
    "purchase_history": ("unit", "currency", "price_basis", "price_unit"),
    "sales": ("unit",),
    "inventory_count": ("unit",),
    "opening_stock": ("unit", "currency"),
    "inventory_receipts": ("unit", "currency"),
    "recipes": ("unit", "yield_unit", "yield_quantity", "process_loss_rate", "quantity_basis"),
    "products": ("selling_unit", "active"),
    "ingredients": ("base_unit", "active", "expiry_tracking"),
    "suppliers": ("active",),
    "supplier_terms": ("unit", "currency", "active", "price_basis", "price_quantity",
        "price_unit", "moq_basis", "moq_unit", "pack_label"),
    "payable_fees": ("scope", "mode", "coverage", "currency"),
    "scope_declarations": (),
}
IMPORT_ONLY = {
    "calendar_events": ("effective_from", "effective_to", "declared_at", "is_closed", "is_holiday", "evidence_reference"),
    "promotion_observations": ("sales_date", "promotion_name", "promotion_applied", "evidence_reference"),
    "usage_history": ("usage_date", "observed_at", "evidence_reference"),
    "purchase_history": ("order_date", "received_date", "report_date", "price", "price_quantity", "supplier_id", "evidence_reference"),
    "sales": ("business_report_key", "is_stockout"),
    "inventory_count": ("observed_at", "reason"),
    "opening_stock": ("observed_at", "reason", "received_date", "expiry_date", "supplier_id", "unit_cost"),
    "inventory_receipts": ("observed_at", "reason", "received_date", "expiry_date", "supplier_id", "unit_cost"),
    "recipes": ("version", "effective_from", "effective_to"),
    "products": ("sku",),
    "ingredients": (),
    "suppliers": (),
    "supplier_terms": (
        "effective_from",
        "effective_to",
        "pack_size_base_quantity",
        "pack_cost",
        "minimum_order_quantity",
        "lead_time_days",
        "shelf_life_days",
        "maximum_order_base_quantity",
    ),
    "payable_fees": (
        "effective_from",
        "effective_to",
        "source_fee_key",
        "evidence_reference",
        "reason",
    ),
    "scope_declarations": ("source_declaration_key",),
}
Scalar = (
    Annotated[StrictStr, Field(max_length=1000)]
    | StrictBool
    | Annotated[StrictInt, Field(ge=-2147483648, le=2147483647)]
    | None
)
Target = Annotated[StrictStr, Field(min_length=1, max_length=128)]


def allowed_scopes(target):
    schema, _, field = target.partition(".")
    if field in BOTH.get(schema, ()):
        return ("PROFILE_CONSTANT", "IMPORT_VALUE")
    if field in IMPORT_ONLY.get(schema, ()):
        return ("IMPORT_VALUE",)
    return ()


def validate_scalar(target, scope, value):
    if scope not in allowed_scopes(target):
        raise ValueError("SHARED_FIELD_NOT_ALLOWED")
    if isinstance(value, str) and not value.strip():
        raise ValueError("EXPLICIT_NULL_OR_NONBLANK_REQUIRED")
    if target == "products.sku" and value is not None:
        raise ValueError("EXPLICIT_UNKNOWN_SKU_REQUIRED")
    schema, field = target.split(".")
    p = SOURCE_MODELS[schema].model_json_schema()["properties"][field]
    types = {x.get("type") for x in p.get("anyOf", (p,))}
    actual = (
        "null"
        if value is None
        else (
            "boolean"
            if type(value) is bool
            else (
                "integer"
                if type(value) is int
                else "string" if type(value) is str else "unsupported"
            )
        )
    )
    if actual not in types:
        raise ValueError("INVALID_SHARED_VALUE_TYPE")
    # Lexical date/decimal normalization and cross-field validation remain downstream.


class ProfileConstant(ImportDTO):
    version: Literal["field_value/1"] = "field_value/1"
    scope: Literal["PROFILE_CONSTANT"] = "PROFILE_CONSTANT"
    target_field: Target
    declaration_id: UUID
    value: Scalar
    evidence_reference: Text

    @model_validator(mode="after")
    def valid(self):
        validate_scalar(self.target_field, self.scope, self.value)
        return self


class ImportValueRequirement(ImportDTO):
    version: Literal["field_value/1", "product_field_value/1"] = "field_value/1"
    scope: Literal["IMPORT_VALUE"] = "IMPORT_VALUE"
    target_field: Target

    @model_validator(mode="after")
    def valid(self):
        if self.version == "product_field_value/1":
            if self.target_field not in ("products.sku", "products.active"):
                raise ValueError("PRODUCT_VALUE_TARGET_NOT_ALLOWED")
            return self
        if self.scope not in allowed_scopes(self.target_field):
            raise ValueError("SHARED_FIELD_NOT_ALLOWED")
        return self


class ImportValue(ImportDTO):
    version: Literal["field_value/1"] = "field_value/1"
    scope: Literal["IMPORT_VALUE"] = "IMPORT_VALUE"
    target_field: Target
    declaration_id: UUID
    value: Scalar
    evidence_reference: Text

    @model_validator(mode="after")
    def valid(self):
        validate_scalar(self.target_field, self.scope, self.value)
        return self


SharedRule = Annotated[
    ProfileConstant | ImportValueRequirement, Field(discriminator="scope")
]


class SharedValueResolution(ImportDTO):
    kind: Literal["shared_value"] = "shared_value"
    target_field: Target
    scope: Literal["PROFILE_CONSTANT", "IMPORT_VALUE"]
    value: Scalar
    evidence_reference: Text
    replace_source_column_index: Annotated[StrictInt, Field(ge=0, le=255)] | None = None
    acknowledgment: StrictBool = False

    @model_validator(mode="after")
    def valid(self):
        validate_scalar(self.target_field, self.scope, self.value)
        if self.replace_source_column_index is not None and not self.acknowledgment:
            raise ValueError("SOURCE_SWITCH_ACKNOWLEDGMENT_REQUIRED")
        return self


class ProductFieldValue(ImportDTO):
    product_id: UUID
    value: Annotated[StrictStr, Field(min_length=1, max_length=64)] | StrictBool | None


class ProductImportValue(ImportDTO):
    version: Literal["product_field_value/1"] = "product_field_value/1"
    scope: Literal["IMPORT_VALUE"] = "IMPORT_VALUE"
    target_field: Literal["products.sku", "products.active"]
    declaration_id: UUID
    values: tuple[ProductFieldValue, ...] = Field(min_length=1, max_length=1000)
    evidence_reference: Text

    @model_validator(mode="after")
    def valid(self):
        for item in self.values:
            if self.target_field == "products.active":
                if type(item.value) is not bool:
                    raise ValueError("PRODUCT_ACTIVE_BOOLEAN_REQUIRED")
            elif item.value is not None and (type(item.value) is not str or not item.value.strip()):
                raise ValueError("PRODUCT_SKU_STRING_OR_EXPLICIT_NULL_REQUIRED")
        return self


class ProductValuesResolution(ImportDTO):
    kind: Literal["product_values"] = "product_values"
    scope: Literal["IMPORT_VALUE"] = "IMPORT_VALUE"
    target_field: Literal["products.sku", "products.active"]
    values: tuple[ProductFieldValue, ...] = Field(min_length=1, max_length=1000)
    evidence_reference: Text
    replace_source_column_index: Annotated[StrictInt, Field(ge=0, le=255)] | None = None
    acknowledgment: StrictBool = False

    @model_validator(mode="after")
    def valid(self):
        ProductImportValue(target_field=self.target_field, declaration_id=UUID(int=0),
            values=self.values, evidence_reference=self.evidence_reference)
        if self.replace_source_column_index is not None and not self.acknowledgment:
            raise ValueError("SOURCE_SWITCH_ACKNOWLEDGMENT_REQUIRED")
        return self


BatchFieldValue = Annotated[ImportValue | ProductImportValue, Field(discriminator="version")]


def parse_import_value(value):
    data = value.model_dump() if isinstance(value, (ImportValue, ProductImportValue)) else value
    model = ProductImportValue if data.get("version") == "product_field_value/1" else ImportValue
    return model.model_validate(data)
