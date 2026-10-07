from datetime import date
from uuid import UUID
from pydantic import model_validator
from app.application.contracts.common import Contract, NonnegativeDecimal


class RecordDailySalesInput(Contract):
    store_id: UUID
    product_id: UUID
    sales_date: date
    quantity: NonnegativeDecimal


class SalesResult(RecordDailySalesInput):
    id: UUID


class GetSalesHistoryInput(Contract):
    store_id: UUID
    product_id: UUID
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def ordered_window(self) -> 'GetSalesHistoryInput':
        if self.start_date > self.end_date:
            raise ValueError('Sales date range must be ordered')
        return self
