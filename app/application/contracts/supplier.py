from datetime import date
from typing import Annotated
from uuid import UUID
from pydantic import Field, model_validator
from app.application.contracts.common import Contract, NonnegativeDecimal, PositiveDecimal, Unit


class CreateSupplierTermInput(Contract):
    store_id: UUID
    supplier_id: UUID
    ingredient_id: UUID
    unit: Unit
    version: Annotated[int, Field(gt=0, strict=True)]
    effective_from: date
    effective_to: date | None = None
    pack_size_base_quantity: PositiveDecimal
    minimum_order_packs: Annotated[int, Field(ge=1, strict=True)]
    pack_cost: NonnegativeDecimal
    lead_time_days: Annotated[int, Field(ge=0, strict=True)]
    shelf_life_days: Annotated[int, Field(ge=0, strict=True)] | None = None
    active: bool = True

    @model_validator(mode='after')
    def ordered_period(self) -> 'CreateSupplierTermInput':
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError('Effective period must be ordered')
        return self


class GetSupplierTermInput(Contract):
    store_id: UUID
    supplier_term_id: UUID


class SupplierTermResult(CreateSupplierTermInput):
    id: UUID
