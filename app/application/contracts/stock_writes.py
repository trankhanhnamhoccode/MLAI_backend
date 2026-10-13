"""Accepted N6/N8 boundaries; canonical stock quantities remain decimal text."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, field_validator
from app.application.contracts.auth import DTO
from app.application.contracts.public_reads import Quantity, Money, LotRead, MovementRead, Notification

Text = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
Reason = Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]
StockQuantity = Annotated[Quantity, Field(max_length=200)]

class ReceiptIdentity(DTO):
    source_system_key: Text
    source_record_id: Text

class StockReceiptRequest(DTO):
    origin: Literal["OPENING_STOCK", "ACTUAL_RECEIPT"]
    receipt_identity: ReceiptIdentity
    ingredient_id: UUID
    supplier_id: UUID | None
    lot_code: Text | None
    quantity: StockQuantity
    unit: Text
    received_date: date | None
    expiry_date: date | None
    unit_cost: Money | None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    observed_at: AwareDatetime
    reason: Reason
    expected_inventory_version: Text

    @field_validator("quantity")
    @classmethod
    def positive(cls, value):
        from decimal import Decimal
        if Decimal(value) <= 0:
            raise ValueError("Positive stock quantity required")
        return value

class StockReceiptResult(DTO):
    receipt_id: UUID
    origin: Literal["OPENING_STOCK", "ACTUAL_RECEIPT"]
    lot: LotRead
    movement: MovementRead
    inventory_version: str
    audit_reference: UUID
    warnings: tuple[Notification, ...] = ()

class ThresholdRequest(DTO):
    minimum_usable_quantity: StockQuantity | None
    unit: Text
    reason: Reason

class ThresholdResult(DTO):
    ingredient_id: UUID
    minimum_usable_quantity: Quantity | None
    unit: str
    version: str
    updated_at: datetime
    updated_by: UUID
