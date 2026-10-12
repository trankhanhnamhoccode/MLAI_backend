"""Small synthetic captured inputs for internal demo/tests, never operational data."""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
D=date(2026,10,7)
STORE,RUN=UUID(int=1),UUID(int=2)
def pid(i):return UUID(int=100+i)
def iid(i):return UUID(int=200+i)

def snapshot(demands,recipes,stock=(),units=None):
    n=max(i for recipe in recipes for i in recipe)+1
    units=units or ['g']*n
    return dict(request=dict(store_id=STORE,forecast_run_id=RUN,product_ids=[pid(p) for p in range(len(demands))],
        cutoff_date=D,order_at=datetime(2026,10,8,tzinfo=timezone.utc)),
        inventory_as_of=datetime(2026,10,8,tzinfo=timezone.utc),timezone='UTC',currency='VND',
        products=[dict(store_id=STORE,product_id=pid(p),sku=f'P{p}',selling_unit='cup') for p in range(len(demands))],
        ingredients=[dict(store_id=STORE,ingredient_id=iid(i),unit=units[i],expiry_tracking=False) for i in range(n)],
        recipes=[dict(id=UUID(int=300+p),store_id=STORE,product_id=pid(p),version=1,effective_from=D,yield_quantity='1',
            process_loss_rate='0',lines=[dict(ingredient_id=iid(i),quantity=str(v),unit=units[i]) for i,v in recipe.items()])
            for p,recipe in enumerate(recipes)],
        forecast=dict(store_id=STORE,run_id=RUN,cutoff_date=D,input_fingerprint='SYNTHETIC-S344',
            model_type='historical_quantile_baseline',model_version='1',artifact_identity=None,
            predictions=[dict(product_id=pid(p),forecast_date=D+timedelta(days=t+1),unit='cup',p25=str(v),p50=str(v),p75=str(v))
                         for p,values in enumerate(demands) for t,v in enumerate(values)]),
        lots=[dict(id=UUID(int=400+j),store_id=STORE,ingredient_id=iid(i),supplier_id=None,lot_code=None,unit=units[i],
            on_hand_quantity=str(v),received_date=D-timedelta(days=2),expiry_date=expiry,unit_cost='1')
              for j,(i,v,expiry) in enumerate(stock)],
        supplier_terms=[],constraints=[],policy={},issues=[],
        assumptions=['DAY_START_CAPTURE','COMPLETE_INVENTORY_SCOPE','NO_ADDITIONAL_ORDERS'],
        source_references=[dict(entity='forecast_run',entity_id=RUN,origin='SOURCE_EXPLICIT')])


def policy(target='1', seconds='30', certification='EXACT_ENUMERATION', limit=256):
    """Explicit SYNTHETIC configuration, not accepted business defaults."""
    return dict(policy_id='procurement',version=1,configuration_id='SYNTHETIC-S344',configuration_version=1,
        provenance='SYNTHETIC demo choices',rules=[dict(strategy=s,path=p,target=target,floors=[])
            for s,p in zip(('LEAN','BALANCED','PROTECTED'),('LOW','BASE','HIGH'))],
        service_units='COMMON_SELLING_UNIT_HORIZON_AGGREGATE',primary='MIN_OUTLAY_SUBJECT_TO_REQUIREMENTS',
        fallback='MAX_CONSTRUCTION_SERVICE_THEN_MIN_OUTLAY',tie_rule='SORTED_OFFER_UUID_PACK_VECTOR_LEXICOGRAPHIC',
        supplier_splitting=True,order_count=1,fee_mode='NONE',computation_seconds=seconds,validation_reserve_seconds='.001',
        max_solves_per_strategy=8,certification=certification,certification_vector_limit=limit if certification!='DISABLED' else 0,
        numeric=dict(integer_tolerance='.0000001',coefficient_min='.0000000001',coefficient_max='10000000000',
            scale_min='1e-100',scale_max='1e100',integer_max=2**53-1))


def envelope(data, offer_specs, budget='100', target='1', seconds='30', certification='EXACT_ENUMERATION',limit=256):
    """Specs explicitly describe synthetic term facts and finite technical bounds."""
    from copy import deepcopy
    data=deepcopy(data);offers=[]
    for j,spec in enumerate(offer_specs):
        i=spec['ingredient'];term=UUID(int=1000+j)
        data['supplier_terms'].append(dict(id=term,store_id=STORE,supplier_id=UUID(int=2000+spec.get('supplier',0)),
            ingredient_id=iid(i),unit=data['ingredients'][i]['unit'],version=1,effective_from=D,
            pack_size_base_quantity=spec['pack'],pack_cost=spec['cost'],minimum_order_packs=spec.get('minimum',1),
            lead_time_days=spec.get('lead',0),shelf_life_days=spec.get('shelf')))
        offers.append(dict(term_id=term,arrival_lot_id=UUID(int=3000+j),
            bound=dict(maximum_packs=spec['upper'],source='TECHNICAL_SEARCH_LIMIT',
                derivation='Explicit SYNTHETIC finite test/demo domain; no supplier-limit claim',proof_scope='CAPTURED_FINITE_DOMAIN_ONLY'),
            payable_fee=spec.get('fee'),provenance='SYNTHETIC captured term/fee/bound'))
    return dict(prepared=data,policy=policy(target,seconds,certification,limit),offers=offers,
        budget=dict(state='KNOWN' if budget is not None else 'EXPLICIT_UNCONSTRAINED',amount=budget,currency='VND',provenance='SYNTHETIC explicit budget'),
        supplier_fees=[],capacities=[],supplier_limits=[],arrivals=[],unsupported_configured_constraints=[],
        source_references=data['source_references']+[dict(entity='supplier_term',entity_id=o['term_id'],origin='SOURCE_EXPLICIT') for o in offers])


def simple(demand=10, stock='0', **kwargs):
    return envelope(snapshot([[demand,0,0,0,0,0,0]],[{0:1}],[(0,stock,None)]),
        [dict(ingredient=0,pack='1',cost='.1',upper=10)],**kwargs)


def representative(n, seconds='15'):
    """5/10 Products, 4 Ingredients, 8 offers, 8 lots; no exact oracle."""
    from decimal import Decimal
    recipes=[{i:str(1+(p+i)%2) for i in range(4) if (p+i)%3!=1} for p in range(n)]
    recipes[0][3]='1'
    data=snapshot([[1+(p*3+t)%4 for t in range(7)] for p in range(n)],recipes,
        [(i,str(1+i),D+timedelta(days=2)) for i in range(4)]+[(i,'2',None) for i in range(4)],['g','ml','g','ml'])
    for point in data['forecast']['predictions']:
        v=Decimal(point['p50']);point.update(p25=str(v/2),p75=str(v*Decimal('1.5')))
    from copy import deepcopy
    for p,r in enumerate(data['recipes'][:]):
        r.update(yield_quantity='3',process_loss_rate='.2',effective_to=D+timedelta(days=3))
        later=deepcopy(r);later.update(id=UUID(int=500+p),version=2,effective_from=D+timedelta(days=4),
            effective_to=None,yield_quantity='2',process_loss_rate='.1')
        data['recipes'].append(later)
    specs=[dict(ingredient=i,pack='8' if s==0 else '6',cost='2' if s==0 else '3',upper=3,
        minimum=2 if s==0 else 1,lead=0 if s==0 else 2,shelf=2 if s==0 else 0,supplier=s)
        for i in range(4) for s in (0,1)]
    result=envelope(data,specs,budget='14',target='.8',seconds=seconds,certification='DISABLED')
    result['policy']['validation_reserve_seconds']='.5'
    result['policy']['fee_mode']='PER_SUPPLIER_ORDER'
    result['supplier_fees']=[dict(supplier_id=UUID(int=2000+s),amount=str(1+s/2),provenance='SYNTHETIC explicit fee') for s in (0,1)]
    result['capacities']=[dict(store_id=STORE,ingredient_id=iid(i),unit=data['ingredients'][i]['unit'],maximum_quantity='22',
        checkpoint='POST_RECEIPT_PRE_EXPIRY_PRE_CONSUMPTION',provenance='SYNTHETIC capacity') for i in range(4)]
    return result
