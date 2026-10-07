from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.application._validation import require_idle_session, require_product
from app.application.contracts.sales import GetSalesHistoryInput, RecordDailySalesInput, SalesResult
from app.application.errors import known_conflict
from app.models import SalesDaily
from app.repositories.sales import SalesRepository


class SalesUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sales = SalesRepository(session)

    def record(self, data: RecordDailySalesInput) -> SalesResult:
        data = RecordDailySalesInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            require_product(self.session, data.store_id, data.product_id)
            row = SalesDaily(**data.model_dump())
            self.sales.add_sales_record(data.store_id, row)
            self.session.flush()
            result = SalesResult.model_validate(row)
            self.session.commit()
            return result
        except IntegrityError as error:
            self.session.rollback()
            mapped = known_conflict(error, 'uq_sales_daily_store_product_date')
            if mapped is not None:
                raise mapped from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def history(self, data: GetSalesHistoryInput) -> tuple[SalesResult, ...]:
        data = GetSalesHistoryInput.model_validate(data)
        with self.session.no_autoflush:
            require_product(self.session, data.store_id, data.product_id)
            return tuple(SalesResult.model_validate(row) for row in self.sales.get_sales_history(
                data.store_id, data.product_id, data.start_date, data.end_date))
