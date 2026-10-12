from typing import Annotated
from pydantic import Field, StrictStr, StrictBool, field_validator, AfterValidator, WrapValidator, TypeAdapter, ValidationError, WithJsonSchema
from app.application.contracts.auth import DTO as AuthDTO
from datetime import date, datetime
import re


def meaningful(value):
    if not value.strip():
        raise ValueError("NONBLANK_REQUIRED")
    return value


class ImportDTO(AuthDTO):
    @field_validator(
        "name",
        "unit",
        "base_unit",
        "selling_unit",
        "yield_unit",
        "sku",
        "reason",
        "evidence_reference",
        "data_date",
        "sales_date",
        "effective_from",
        "effective_to",
        "from_date",
        "to_date",
        "observed_at",
        "created_at",
        "imported_at",
        "approved_at",
        "decided_at",
        "started_at",
        "completed_at",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def dates_and_content(cls, value, info):
        if isinstance(value, str) and info.field_name in {
            "name",
            "unit",
            "base_unit",
            "selling_unit",
            "yield_unit",
            "sku",
            "reason",
            "evidence_reference",
        }:
            meaningful(value)
        if value is not None and info.field_name in {
            "data_date",
            "sales_date",
            "effective_from",
            "effective_to",
            "from_date",
            "to_date",
        }:
            if type(value) is date:
                return value
            if not isinstance(value, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
            ):
                raise ValueError("CANONICAL_DATE_REQUIRED")
        if value is not None and info.field_name in {
            "observed_at",
            "created_at",
            "imported_at",
            "approved_at",
            "decided_at",
            "started_at",
            "completed_at",
        }:
            if isinstance(value, str):
                if not re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})",
                    value,
                ):
                    raise ValueError("TIMESTAMP_REQUIRED")
                value = datetime.fromisoformat(value)
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError("TIMEZONE_REQUIRED")
        return value


DTO = ImportDTO

Quantity = Annotated[
    StrictStr, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=200)
]
Text = Annotated[
    StrictStr, Field(min_length=1, max_length=1000), AfterValidator(meaningful)
]


def retained_money(value, handler, info):
    try:
        return handler(value)
    except ValidationError:
        if (info.context or {}).get("retained_evidence"):
            return TypeAdapter(Quantity).validate_python(value)
        raise


Money = Annotated[StrictStr, Field(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$"), WrapValidator(retained_money),
    WithJsonSchema({"type":"string","pattern":r"^(0|[1-9][0-9]*)(\.[0-9]+)?$","maxLength":200,
        "description":"New money obeys 18 integer/18 fractional digits; retained pre-alignment import evidence may preserve wider exact decimal text. Never an input bypass."},mode="serialization")]


class ProductMetadata(DTO):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    selling_unit: Annotated[StrictStr, Field(min_length=1, max_length=32)]
    sku: Annotated[StrictStr, Field(min_length=1, max_length=64)] | None
    price: Money | None
    active: StrictBool


class IngredientMetadata(DTO):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    base_unit: Annotated[StrictStr, Field(min_length=1, max_length=32)]
    sku: Annotated[StrictStr, Field(min_length=1, max_length=64)] | None
    expiry_tracking: StrictBool
    active: StrictBool


class SupplierMetadata(DTO):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    active: StrictBool
