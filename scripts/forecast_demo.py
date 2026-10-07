"""Small deterministic SYNTHETIC capture; no import of customer/operational data."""
from datetime import date, timedelta
from uuid import UUID

from app.application.contracts.forecast_execution import ForecastExecutionInput, PreparedForecastInput
from app.domain.forecasting.validation import forecast_dates


def synthetic_input(days: int = 120, products: int = 2) -> PreparedForecastInput:
    start = date(2026, 1, 1)
    cutoff = start + timedelta(days=days - 1)
    store, ids = UUID(int=1000), tuple(UUID(int=1001+i) for i in range(products))
    return PreparedForecastInput(request=ForecastExecutionInput(store_id=store, product_ids=ids,
        history_start_date=start, cutoff_date=cutoff), timezone='Asia/Ho_Chi_Minh',
        products=[dict(product_id=p, selling_unit='cup') for p in ids],
        observations=[dict(store_id=store, product_id=p, selling_unit='cup',
            sales_date=start+timedelta(days=d), quantity=str(10 + (d % 7)*5 + d//14 + code*10))
            for code,p in enumerate(ids) for d in range(days)], forecast_dates=forecast_dates(cutoff))
