"""F3_SYNTHETIC facts from scope/origin only; never forecast or actual quantities."""
from copy import deepcopy
from datetime import date,datetime,timedelta
from uuid import UUID,uuid5,NAMESPACE_URL
from app.application.contracts.planning_impact import ImpactSnapshot
from app.application.forecast_benchmark_admission import next_run
from scripts.procurement_demo_cases import snapshot,envelope,D,STORE,pid,iid
from scripts.procurement_v2_demo_cases import upgrade,path

FIXTURES=('stock_only','scarce_purchase','dated_shared','tight_budget')


def operational_snapshot(origin,products,timezone,store_id,fixture):
    if fixture not in FIXTURES or len(products)!=5:raise ValueError('F3_FROZEN_SCOPE')
    specs=[];stock=[(0,'100000',D+timedelta(days=10)),(1,'100000',D+timedelta(days=10))]
    if fixture in ('scarce_purchase','tight_budget'):
        stock[0]=(0,'0',D+timedelta(days=10))
        specs=[dict(ingredient=0,pack='400',cost='20',upper=4,shelf=10)]
    if fixture=='dated_shared':
        stock=[(0,'500',D+timedelta(days=2)),(1,'500',D+timedelta(days=3))]
        specs=[dict(ingredient=0,pack='800',cost='40',upper=2,lead=2,shelf=4,supplier=0),
               dict(ingredient=1,pack='800',cost='25',upper=2,lead=0,shelf=7,supplier=1)]
    data=upgrade(envelope(snapshot([[0]*7 for _ in products],[{0:1,1:1} for _ in products],stock,['g','ml']),
        specs,budget='23' if fixture=='tight_budget' else '500',seconds='4',
        certification='DISABLED' if fixture=='tight_budget' else 'EXACT_ENUMERATION',limit=9),[path('BASE','.95')])
    data['policy'].update(configuration_id='F3_SYNTHETIC/1',provenance='F3_SYNTHETIC delegated counterfactual policy, not Store facts',
        max_solves_per_strategy=2,fee_mode='PER_SUPPLIER_ORDER')
    suppliers=sorted({s.get('supplier',0) for s in specs})
    data['supplier_fees']=[dict(supplier_id=UUID(int=2000+i),amount=str(3 if i==0 else 2),
        provenance='F3_SYNTHETIC generic payable order fee; no delivery-fee type inference') for i in suppliers]
    p=data['prepared']
    if fixture=='dated_shared':
        for i,recipe in enumerate(p['recipes'][:]):
            recipe.update(effective_to=D+timedelta(days=3),process_loss_rate='.1')
            later=deepcopy(recipe)
            later.update(id=UUID(int=900+i),version=2,effective_from=D+timedelta(days=4),effective_to=None,
                yield_quantity='2',process_loss_rate='0')
            for line in later['lines']:line['quantity']='2'
            p['recipes'].append(later)
    for ingredient in p['ingredients']:ingredient['expiry_tracking']=True
    for i,unit in enumerate(('g','ml')):
        data['capacities'].append(dict(store_id=STORE,ingredient_id=iid(i),unit=unit,maximum_quantity='200000',
            checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',provenance='F3_SYNTHETIC explicit gross capacity'))
    for spec in specs:
        data['supplier_limits'].append(dict(store_id=STORE,supplier_id=UUID(int=2000+spec.get('supplier',0)),
            ingredient_id=iid(spec['ingredient']),unit=('g','ml')[spec['ingredient']],maximum_quantity='2000',
            scope='ONE_ORDER_SUPPLIER_INGREDIENT',provenance='F3_SYNTHETIC explicit physical order limit'))
    replacements={STORE:store_id,**{pid(i):v.product_id for i,v in enumerate(products)},
        **{iid(i):uuid5(NAMESPACE_URL,'shelfcash/F3_SYNTHETIC/ingredient/'+unit) for i,unit in enumerate(('g','ml'))}}
    delta=origin-D
    def convert(value):
        if isinstance(value,dict):return {k:convert(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [convert(v) for v in value]
        if isinstance(value,(date,datetime)):return value+delta
        if isinstance(value,UUID):return replacements.get(value,value)
        return value
    data=convert(data);p=data['prepared']
    p.update(timezone=timezone,inventory_as_of=next_run(origin,timezone))
    p['request']['order_at']=next_run(origin,timezone)
    p['assumptions'].append('F3_SYNTHETIC: complete fictional stock/recipes/offers/fees/constraints; no workbook operational facts substituted')
    p['forecast'].update(model_type='counterfactual_placeholder',model_version='F3/1',input_fingerprint='F3_SYNTHETIC-placeholder/1')
    units={v.product_id:v.selling_unit for v in products}
    for row in p['products']:row['selling_unit']=units[row['product_id']]
    for row in p['forecast']['predictions']:row['unit']=units[row['product_id']]
    for refs in (p['source_references'],data['source_references']):
        for r in refs:r['origin']='SYSTEM_ASSIGNED'
    return ImpactSnapshot(fixture_id=fixture,origin=origin,facts_known_at=next_run(origin,timezone),template=data)
