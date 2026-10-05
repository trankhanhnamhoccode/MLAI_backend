from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Annotated
from pydantic import Field, model_validator
from app.application.contracts.common import Contract, NonnegativeDecimal, PositiveDecimal, Unit


class RecipeLineInput(Contract):
    ingredient_id: UUID
    quantity: PositiveDecimal
    unit: Unit


class CreateRecipeVersionInput(Contract):
    store_id: UUID
    product_id: UUID
    version: Annotated[int, Field(gt=0, strict=True)]
    effective_from: date
    effective_to: date | None = None
    yield_quantity: PositiveDecimal
    process_loss_rate: Annotated[NonnegativeDecimal, Field(lt=1)]
    lines: tuple[RecipeLineInput, ...]

    @model_validator(mode='after')
    def valid_period_and_unique_lines(self) -> 'CreateRecipeVersionInput':
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError('Effective period must be ordered')
        if len({line.ingredient_id for line in self.lines}) != len(self.lines):
            raise ValueError('Ingredient may appear only once per Recipe')
        return self


class GetActiveRecipeInput(Contract):
    store_id: UUID
    product_id: UUID
    effective_date: date


class RecipeLineResult(Contract):
    id: UUID
    ingredient_id: UUID
    quantity: Decimal
    unit: Unit


class RecipeResult(Contract):
    id: UUID
    store_id: UUID
    product_id: UUID
    version: int
    effective_from: date
    effective_to: date | None
    yield_quantity: Decimal
    process_loss_rate: Decimal
    lines: tuple[RecipeLineResult, ...]
