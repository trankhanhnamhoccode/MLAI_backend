"""E4 frozen synthetic facts: only scope/origin enter, never forecast/actual quantities."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from uuid import UUID

from app.application.contracts.planning_impact import ImpactSnapshot
from app.application.forecast_benchmark_admission import next_run
from scripts.procurement_demo_cases import snapshot, envelope, D, pid, iid, STORE
from scripts.procurement_v2_demo_cases import upgrade, path

FIXTURES = ('stock_only', 'shared_purchase', 'dated_expiry_arrivals', 'bounded_unproven')


def operational_snapshot(origin, products, timezone, fixture):
    if fixture not in FIXTURES or len(products) != 2:
        raise ValueError('Frozen E4 synthetic scope requires two Products')
    stock = [(0, '1000', D+timedelta(days=10)), (1, '1000', D+timedelta(days=10))]
    specs = []
    if fixture != 'stock_only':
        stock = [(0, '20', D+timedelta(days=10)), (1, '1000', D+timedelta(days=10))]
        specs = [dict(ingredient=0, pack='60', cost='2', upper=5, shelf=10)]
    if fixture == 'dated_expiry_arrivals':
        stock = [(0, '120', D+timedelta(days=2)), (1, '400', D+timedelta(days=7))]
        specs[0].update(lead=2, shelf=4)
    if fixture == 'bounded_unproven':
        stock = [(0, '20', D+timedelta(days=7)), (1, '40', D+timedelta(days=7))]
        specs = [dict(ingredient=i, pack='60', cost=str(i+2), upper=5,
                      minimum=2 if i == 0 else 1, shelf=6, supplier=i) for i in range(2)]
    data = upgrade(envelope(snapshot([[0]*7, [0]*7], [{0:1, 1:1}, {0:2}], stock, ['g','ml']),
        specs, budget='14' if fixture == 'bounded_unproven' else '25', seconds='2',
        certification='DISABLED' if fixture == 'bounded_unproven' else 'EXACT_ENUMERATION', limit=16),
        [path('BASE', '.95')])
    data['policy'].update(max_solves_per_strategy=4, fee_mode='PER_SUPPLIER_ORDER',
                          configuration_id='SYNTHETIC-E4-frozen/1')
    data['supplier_fees'] = [dict(supplier_id=UUID(int=2000+i), amount=str(i+1),
        provenance='SYNTHETIC declared generic payable fee') for i in range(2 if fixture == 'bounded_unproven' else bool(specs))]
    p = data['prepared']
    if fixture == 'dated_expiry_arrivals':
        first = p['recipes'][0]
        first.update(effective_to=D+timedelta(days=3), process_loss_rate='.2')
        second = deepcopy(first)
        second.update(id=UUID(int=900), version=2, effective_from=D+timedelta(days=4),
                      effective_to=None, yield_quantity='2', process_loss_rate='0')
        p['recipes'].append(second)
    for ingredient in p['ingredients']:
        ingredient['expiry_tracking'] = True
    for i in range(2):
        data['capacities'].append(dict(store_id=STORE, ingredient_id=iid(i), unit=('g','ml')[i],
            maximum_quantity='1500', checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',
            provenance='SYNTHETIC fixed gross capacity'))
    for j, spec in enumerate(specs):
        data['supplier_limits'].append(dict(store_id=STORE, supplier_id=UUID(int=2000+spec.get('supplier',0)),
            ingredient_id=iid(spec['ingredient']), unit=('g','ml')[spec['ingredient']], maximum_quantity='300',
            scope='ONE_ORDER_SUPPLIER_INGREDIENT', provenance='SYNTHETIC fixed supplier limit'))
    replacements = {pid(i):p.product_id for i,p in enumerate(products)}
    delta = origin-D
    def convert(value):
        if isinstance(value, dict): return {k:convert(v) for k,v in value.items()}
        if isinstance(value, (list,tuple)): return [convert(v) for v in value]
        if isinstance(value, (date,datetime)): return value+delta
        if isinstance(value, UUID): return replacements.get(value,value)
        return value
    data = convert(data)
    p = data['prepared']
    p.update(timezone=timezone, inventory_as_of=next_run(origin,timezone))
    p['request']['order_at'] = next_run(origin,timezone)
    p['forecast'].update(model_type='counterfactual_placeholder', model_version='1', input_fingerprint='SYNTHETIC-E4-template/1')
    for row, product in zip(p['products'],products,strict=True): row['selling_unit']=product.selling_unit
    units = {p.product_id:p.selling_unit for p in products}
    for row in p['forecast']['predictions']: row['unit']=units[row['product_id']]
    return ImpactSnapshot(fixture_id=fixture, origin=origin, facts_known_at=next_run(origin,timezone), template=data)
