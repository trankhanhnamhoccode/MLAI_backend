"""Explicit scalar declarations and reviewed source rules, not row defaults."""

from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from app.application.contracts.import_scalars import ImportDTO, Text
from app.application.contracts.import_domains import SOURCE_MODELS

BOTH = {
    "sales": ("unit",),
    "inventory_count": ("unit",),
    "recipes": ("unit", "yield_unit", "yield_quantity", "process_loss_rate"),
    "products": ("selling_unit", "active"),
    "ingredients": ("base_unit", "active", "expiry_tracking"),
    "suppliers": ("active",),
    "supplier_terms": ("unit", "currency", "active"),
    "payable_fees": ("scope", "mode", "coverage", "currency"),
    "scope_declarations": (),
}
IMPORT_ONLY = {
    "sales": ("business_report_key",),
    "inventory_count": ("observed_at", "reason"),
    "recipes": ("version", "effective_from", "effective_to"),
    "products": (),
    "ingredients": (),
    "suppliers": (),
    "supplier_terms": (
        "effective_from",
        "effective_to",
        "pack_size_base_quantity",
        "pack_cost",
        "minimum_order_packs",
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
    version: Literal["field_value/1"] = "field_value/1"
    scope: Literal["IMPORT_VALUE"] = "IMPORT_VALUE"
    target_field: Target

    @model_validator(mode="after")
    def valid(self):
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
