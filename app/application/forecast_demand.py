"""Project captured observations to versioned consumer inputs, without changing sales."""
from app.domain.forecasting.stockout import Observation, reconstruct


def demand_estimates(prepared):
    return {pid: reconstruct(tuple(Observation(r.sales_date, r.quantity, r.is_stockout)
        for r in prepared.observations if r.product_id == pid), prepared.request.cutoff_date)
        for pid in prepared.request.product_ids}


def usable_histories(prepared):
    if prepared.demand_policy == 'observed_sales_v1':
        return {pid: tuple((r.sales_date, r.quantity) for r in prepared.observations if r.product_id == pid)
                for pid in prepared.request.product_ids}
    return {pid: tuple((r.day, r.demand_quantity) for r in rows if r.usable)
            for pid, rows in demand_estimates(prepared).items()}


def demand_warnings(prepared):
    from app.application.contracts.forecast_execution import ForecastWarning
    if prepared.demand_policy == 'observed_sales_v1':
        return ()
    codes = {'UNKNOWN_OBSERVED_COMPATIBILITY': ('STOCKOUT_UNKNOWN', 'Observed quantity used; censorship unknown'),
             'CENSORED_UNSUPPORTED': ('CENSORED_HISTORY_EXCLUDED', 'Censored days lack prior uncensored support and are excluded'),
             'PAST_MEDIAN': ('DEMAND_RECONSTRUCTED', 'Demand is a causal estimate, not observed lost demand')}
    warnings = tuple(ForecastWarning(code=code, severity='WARNING', field='is_stockout', entity='product',
        product_id=pid, impact=impact) for pid, rows in demand_estimates(prepared).items()
        for method, (code, impact) in codes.items() if any(r.method == method for r in rows))
    return tuple(sorted(warnings, key=lambda w: (w.code, w.severity, w.field, w.entity, w.impact, str(w.product_id))))
