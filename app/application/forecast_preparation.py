"""Typed scope/observations prepared from one detached canonical snapshot."""
from datetime import timedelta,date
from decimal import Decimal
from uuid import UUID
from app.application.contracts.forecast_execution import PreparedForecastInput,ForecastExecutionInput
from app.application.contracts.auth import AuthError
from app.repositories.readiness import ReadinessFacts


def prepare_observations(facts: ReadinessFacts,store: UUID,start: date,
                         product_ids: tuple[UUID,...] | None=None, *, native_challenger=False) -> PreparedForecastInput:
    cutoff=start-timedelta(days=1)
    active={r['id']:r for r in facts.snapshot['products'] if r['active']}
    history=[r for r in facts.snapshot['sales_daily'] if r['product_id'] in active and r['sales_date']<=str(cutoff)]
    ids=set(map(str,product_ids)) if product_ids is not None else {r['product_id'] for r in history}
    if not ids or not ids<=set(active):
        raise AuthError('NO_COMPUTABLE_PRODUCTS',409)
    rows=[r for r in history if r['product_id'] in ids]
    if {r['product_id'] for r in rows}!=ids:
        raise AuthError('PRODUCT_HISTORY_MISSING',409)
    return PreparedForecastInput(schema_version=3 if native_challenger else 2,
        demand_policy='engine_native_reconstruction_v1' if native_challenger else 'causal_stockout_v1',
        request=ForecastExecutionInput(store_id=store,product_ids=tuple(UUID(i) for i in sorted(ids)),
        history_start_date=min(date.fromisoformat(r['sales_date']) for r in rows),cutoff_date=cutoff),
        timezone=facts.snapshot['stores'][0]['timezone'],products=tuple(dict(product_id=i,selling_unit=active[i]['selling_unit']) for i in sorted(ids)),
        observations=tuple(dict(store_id=store,product_id=r['product_id'],sales_date=r['sales_date'],
            quantity=Decimal(r['quantity']),is_stockout=r.get('is_stockout'),selling_unit=active[r['product_id']]['selling_unit']) for r in rows),
        forecast_dates=tuple(start+timedelta(days=i) for i in range(7)))
