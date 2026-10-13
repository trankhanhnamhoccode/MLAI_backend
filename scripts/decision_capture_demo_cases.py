"""Deterministic synthetic repository-port facts, never operational DB data."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.contracts.decision_capture import OperationalDecisionInput, OperationalFacts
from app.application.contracts.forecast_execution import PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared
from scripts.procurement_demo_cases import simple, D, STORE, RUN


def synthetic_case():
    data = simple(demand=2, stock='1', budget='5', certification='DISABLED')
    p = data['prepared']
    retained = PreparedForecastInput(request=dict(store_id=STORE, product_ids=p['request']['product_ids'],
        cutoff_date=D, history_start_date=D), timezone='UTC', products=tuple(
        dict(product_id=r['product_id'], selling_unit=r['selling_unit']) for r in p['products']),
        observations=(), forecast_dates=tuple(D + timedelta(days=n) for n in range(1,8)))
    digest = serialize_prepared(retained).digest
    request = OperationalDecisionInput(store_id=STORE, forecast_run_id=RUN,
        product_ids=p['request']['product_ids'], cutoff_date=D,
        day_start_provenance='SYNTHETIC day-start observation, no intraday trades',
        no_additional_orders_provenance='SYNTHETIC one-order scenario',
        committed_inbound_state='CONFIRMED_NONE', committed_inbound_provenance='SYNTHETIC explicit absence',
        inventory_scope=tuple(dict(ingredient_id=i['ingredient_id'], state='COMPLETE_CURRENT_LOTS',
            provenance='SYNTHETIC complete lot scope') for i in p['ingredients']), snapshot_policy=p['policy'],
        procurement=dict(policy=data['policy'], offers=data['offers'], budget=data['budget'],
            supplier_fees=data['supplier_fees'], capacities=data['capacities'], supplier_limits=data['supplier_limits'],
            capacity_state='EXPLICIT_NOT_CONFIGURED', supplier_limit_state='EXPLICIT_NOT_CONFIGURED',
            provenance='SYNTHETIC explicit caller configuration, not DB facts'))
    facts = OperationalFacts(captured_at=p['inventory_as_of'], store=dict(id=STORE, timezone='UTC', currency='VND'),
        forecast=dict(id=RUN, store_id=STORE, status='COMPLETED', training_start_date=D, training_end_date=D,
            forecast_start_date=D+timedelta(days=1), forecast_end_date=D+timedelta(days=7),
            completed_at=datetime(2026,10,7,23,tzinfo=timezone.utc), input_fingerprint=digest,
            model_type='historical_quantile_baseline', model_version='1', artifact_key=None,
            predictions=tuple(dict(id=UUID(int=5000+n), store_id=STORE, forecast_run_id=RUN,
                **{k:v for k,v in r.items() if k!='unit'}) for n,r in enumerate(p['forecast']['predictions'])),
            retained=retained, retained_digest=digest, execution=None), products=p['products'], ingredients=p['ingredients'],
        recipes=p['recipes'], lots=p['lots'], supplier_terms=p['supplier_terms'], constraints=p['constraints'],
        source_times=(dict(entity='inventory_lot', entity_id=p['lots'][0]['id'], kind='ROW_UPDATED_AT',
                           at=datetime(2026,10,7,23,tzinfo=timezone.utc)),))
    return request, facts


class SyntheticSnapshotSource:
    """Fake repository adapter: detached read values; no PostgreSQL isolation claim."""
    def __init__(self, facts):
        self.facts = facts
        self.reads = 0

    def read(self, request, clock):
        self.reads += 1
        return self.facts.model_copy(update={'captured_at': clock()})
