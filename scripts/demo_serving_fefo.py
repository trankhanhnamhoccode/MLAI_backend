"""Small deterministic in-memory milk example. No DB or provider calls."""
import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from app.application.contracts.serving import ServingSimulationInput
from app.application.use_cases.serving import simulate_serving


def milk_input() -> ServingSimulationInput:
    store, run, a, b, ingredient, lot = (UUID(int=i) for i in range(1, 7))
    cutoff = date(2026, 10, 7)
    instant = datetime(2026, 10, 8, tzinfo=timezone.utc)
    prepared = dict(
        request=dict(store_id=store, forecast_run_id=run, product_ids=[a,b], cutoff_date=cutoff, order_at=instant),
        timezone='UTC', currency='VND', inventory_as_of=instant,
        forecast=dict(store_id=store, run_id=run, cutoff_date=cutoff, input_fingerprint='SYNTHETIC-MILK',
            model_type='historical_quantile_baseline', model_version='1', artifact_identity=None,
            predictions=[dict(product_id=p, forecast_date=cutoff+timedelta(days=i),unit='cup',p25=q,p50=q,p75=q)
                         for i in range(1,8) for p,q in ((a,'20'),(b,'10'))]),
        products=[dict(store_id=store,product_id=p,selling_unit='cup',sku=label) for p,label in ((a,'A'),(b,'B'))],
        ingredients=[dict(store_id=store,ingredient_id=ingredient,unit='L',expiry_tracking=False)],
        recipes=[dict(id=UUID(int=10+i),store_id=store,product_id=p,version=1,effective_from=cutoff,
            yield_quantity='1',process_loss_rate='0',lines=[dict(ingredient_id=ingredient,quantity=q,unit='L')])
                 for i,(p,q) in enumerate(((a,'.2'),(b,'.4')))],
        lots=[dict(id=lot,store_id=store,ingredient_id=ingredient,supplier_id=None,lot_code=None,
            received_date=cutoff,expiry_date=None,on_hand_quantity='6',unit='L',unit_cost='1')],
        supplier_terms=[],constraints=[],policy={},issues=[],
        assumptions=['DAY_START_CAPTURE','COMPLETE_INVENTORY_SCOPE','NO_ADDITIONAL_ORDERS'],
        source_references=[dict(entity='forecast_run',entity_id=run,origin='SOURCE_EXPLICIT')])
    return ServingSimulationInput(prepared=prepared)


def main() -> None:
    result=simulate_serving(milk_input())
    print(json.dumps(dict(synthetic=True,status=result.status,decision_readiness=result.decision_readiness,
        semantics_version=result.semantics_version,
        base_day1=[r.model_dump(mode='json') for r in result.products if r.path_id=='BASE' and r.day==date(2026,10,8)]),indent=2))


if __name__=='__main__':
    main()
