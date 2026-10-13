"""A2 recorded evidence: never inventory transactions or forecast features."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
import re

from pydantic import AwareDatetime, Field, StrictBool, model_validator, field_validator
from app.application.contracts.import_scalars import ImportDTO, Quantity, Money, Text


class HistoryIdentity(ImportDTO):
    source_record_key: Text
    evidence_reference: Text

    @field_validator('effective_from', 'effective_to', 'sales_date', 'usage_date',
                     'order_date', 'received_date', 'report_date', mode='before', check_fields=False)
    @classmethod
    def exact_date(cls, value):
        if value is not None and not isinstance(value, date) and (
            not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)):
            raise ValueError('DECLARED_DATE_FORMAT_REQUIRED')
        return value


class CalendarEventSource(HistoryIdentity):
    domain: Literal['calendar_events'] = 'calendar_events'
    event_name: Text
    effective_from: date
    effective_to: date
    declared_at: AwareDatetime
    is_closed: StrictBool | None
    is_holiday: StrictBool | None

    @model_validator(mode='after')
    def period(self):
        if self.effective_to < self.effective_from:
            raise ValueError('INVALID_PERIOD')
        return self


class PromotionObservationSource(HistoryIdentity):
    domain: Literal['promotion_observations'] = 'promotion_observations'
    product_id: UUID
    sales_date: date
    promotion_name: Text | None
    promotion_applied: StrictBool | None


class UsageHistorySource(HistoryIdentity):
    domain: Literal['usage_history'] = 'usage_history'
    ingredient_id: UUID
    usage_date: date
    observed_at: AwareDatetime | None
    quantity: Quantity
    unit: Annotated[str, Field(min_length=1, max_length=32, pattern=r'\S')]


class PurchaseHistorySource(HistoryIdentity):
    domain: Literal['purchase_history'] = 'purchase_history'
    ingredient_id: UUID
    supplier_id: UUID | None
    quantity: Quantity
    unit: Annotated[str, Field(min_length=1, max_length=32, pattern=r'\S')]
    order_date: date | None
    received_date: date | None
    report_date: date
    price: Money | None
    price_basis: Literal['PER_QUANTITY', 'LINE_TOTAL', 'UNKNOWN']
    price_quantity: Quantity | None
    price_unit: str | None
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]

    @model_validator(mode='after')
    def basis(self):
        if self.price_basis == 'UNKNOWN':
            if any(v is not None for v in (self.price, self.price_quantity, self.price_unit)):
                raise ValueError('UNKNOWN_PRICE_HAS_VALUES')
        elif self.price is None:
            raise ValueError('PRICE_REQUIRED')
        elif self.price_basis == 'PER_QUANTITY':
            if self.price_quantity is None or Decimal(self.price_quantity) <= 0 or not self.price_unit:
                raise ValueError('PRICE_DENOMINATOR_REQUIRED')
        elif self.price_quantity is not None or self.price_unit is not None:
            raise ValueError('UNEXPECTED_PRICE_DENOMINATOR')
        if self.received_date and self.order_date and self.received_date < self.order_date:
            raise ValueError('RECEIPT_BEFORE_ORDER')
        return self


HISTORY_MODELS = {
    'calendar_events': CalendarEventSource,
    'promotion_observations': PromotionObservationSource,
    'usage_history': UsageHistorySource,
    'purchase_history': PurchaseHistorySource,
}
HistoryValue = Annotated[
    CalendarEventSource | PromotionObservationSource | UsageHistorySource | PurchaseHistorySource,
    Field(discriminator='domain'),
]
