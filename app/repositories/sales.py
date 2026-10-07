"""Canonical daily sales access; no additive reimport, upsert or correction."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SalesDaily
from app.repositories._guards import require_new, require_store


class SalesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_sales_record(self, store_id: UUID, daily: SalesDaily) -> None:
        require_store(store_id, daily.store_id)
        require_new(daily)
        self._session.add(daily)

    def get_daily_by_id(self, store_id: UUID, daily_id: UUID) -> SalesDaily | None:
        return self._session.scalar(select(SalesDaily).where(SalesDaily.store_id == store_id, SalesDaily.id == daily_id))

    def get_daily_sale(self, store_id: UUID, product_id: UUID, day: date) -> SalesDaily | None:
        return self._session.scalar(select(SalesDaily).where(SalesDaily.store_id == store_id, SalesDaily.product_id == product_id, SalesDaily.sales_date == day))

    def get_sales_history(self, store_id: UUID, product_id: UUID, start_date: date, end_date: date) -> list[SalesDaily]:
        if end_date < start_date:
            raise ValueError("Sales date range must be ordered")
        return list(self._session.scalars(select(SalesDaily).where(
            SalesDaily.store_id == store_id, SalesDaily.product_id == product_id,
            SalesDaily.sales_date >= start_date, SalesDaily.sales_date <= end_date,
        ).order_by(SalesDaily.sales_date, SalesDaily.id)))

    def list_store_sales(self, store_id: UUID, start_date: date, end_date: date) -> list[SalesDaily]:
        if end_date < start_date:
            raise ValueError("Sales date range must be ordered")
        return list(self._session.scalars(select(SalesDaily).where(
            SalesDaily.store_id == store_id, SalesDaily.sales_date >= start_date,
            SalesDaily.sales_date <= end_date,
        ).order_by(SalesDaily.sales_date, SalesDaily.product_id, SalesDaily.id)))
