from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, StringConstraints, field_validator, model_validator
from app.application.contracts.common import Contract, FiniteDecimal, Metadata, Nonblank, NonnegativeDecimal, PositiveDecimal, Unit

MovementType = Literal['RECEIPT', 'USAGE', 'WASTE', 'EXPIRED', 'COUNT_CORRECTION', 'MANUAL_ADJUSTMENT']


class MovementMetadata(Contract):
    occurred_at: AwareDatetime
    reference_type: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'\S')] | None = None
    reference_id: Nonblank | None = None
    note: str | None = None

    @field_validator('occurred_at')
    @classmethod
    def utc_instant(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def paired_reference(self) -> 'MovementMetadata':
        if (self.reference_type is None) != (self.reference_id is None):
            raise ValueError('Reference type/id must both be present or absent')
        return self


class ReceiveInventoryInput(MovementMetadata):
    store_id: UUID
    ingredient_id: UUID
    supplier_id: UUID | None = None
    lot_code: Metadata | None = None
    received_date: date | None = None
    expiry_date: date | None = None
    quantity: PositiveDecimal
    unit: Unit
    unit_cost: NonnegativeDecimal | None = None

    @model_validator(mode='after')
    def expiry_order(self) -> 'ReceiveInventoryInput':
        if self.received_date is not None and self.expiry_date is not None and self.expiry_date < self.received_date:
            raise ValueError('Expiry cannot precede known receipt date')
        return self


class AdjustInventoryInput(MovementMetadata):
    store_id: UUID
    lot_id: UUID
    quantity_delta: FiniteDecimal
    unit: Unit
    movement_type: Literal['COUNT_CORRECTION', 'MANUAL_ADJUSTMENT']
    note: Nonblank

    @model_validator(mode='after')
    def nonzero_delta(self) -> 'AdjustInventoryInput':
        if self.quantity_delta == 0:
            raise ValueError('Adjustment delta must be nonzero')
        return self


class GetInventoryLotInput(Contract):
    store_id: UUID
    lot_id: UUID


class InventoryLotResult(Contract):
    id: UUID
    store_id: UUID
    ingredient_id: UUID
    supplier_id: UUID | None
    lot_code: str | None
    received_date: date | None
    expiry_date: date | None
    on_hand_quantity: NonnegativeDecimal
    unit: Unit
    unit_cost: NonnegativeDecimal | None


class InventoryMovementResult(MovementMetadata):
    id: UUID
    store_id: UUID
    lot_id: UUID
    ingredient_id: UUID
    movement_type: MovementType
    quantity_delta: FiniteDecimal


class InventoryMutationResult(Contract):
    lot: InventoryLotResult
    movement: InventoryMovementResult
