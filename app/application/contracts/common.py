"""Shared boundary types; validation only, no business computation."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue, RootModel, StringConstraints, model_validator
from decimal import Decimal


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, from_attributes=True,
                              revalidate_instances='always', allow_inf_nan=False)


def exact_decimal(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError('Supply Decimal, decimal string or integer, never binary float/bool')
    return value


NonnegativeDecimal = Annotated[Decimal, BeforeValidator(exact_decimal), Field(ge=0, allow_inf_nan=False)]
PositiveDecimal = Annotated[Decimal, BeforeValidator(exact_decimal), Field(gt=0, allow_inf_nan=False)]
FiniteDecimal = Annotated[Decimal, BeforeValidator(exact_decimal), Field(allow_inf_nan=False)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r'\S')]
Unit = Annotated[str, StringConstraints(min_length=1, max_length=32, pattern=r'\S')]
Sku = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'\S')]
Metadata = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r'\S')]
Nonblank = Annotated[str, StringConstraints(min_length=1, pattern=r'\S')]
RunStatus = Literal['RUNNING', 'COMPLETED', 'FAILED']
Strategy = Literal['LEAN', 'BALANCED', 'PROTECTED']


class JsonObject(RootModel[dict[str, JsonValue]]):
    """Opaque finite JSON object; full business package schema remains future."""
    model_config = ConfigDict(frozen=True, allow_inf_nan=False, revalidate_instances='always')

    @model_validator(mode='after')
    def finite_json(self) -> 'JsonObject':
        # JSON serializers otherwise permit NaN/Infinity unsupported by JSONB.
        import json
        json.dumps(self.root, allow_nan=False)
        return self


class RunReferenceInput(Contract):
    store_id: UUID
    run_id: UUID
