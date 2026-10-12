"""Independent exact expectations for actual progressive serving and FEFO."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, localcontext, Inexact
from fractions import Fraction
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.serving import ServingSimulationInput, HypotheticalArrival, Quantity
from app.application.use_cases.serving import simulate_serving
from tests.unit.test_decision_execution import snapshot_data, issue, D, PRODUCT, INGREDIENT, RECIPE, LOT, STORE
from tests.unit.test_bom import add_product

SECOND_INGREDIENT = UUID(int=301)
SECOND_LOT = UUID(int=302)


def rational(value):
    return Fraction(int(value.numerator), int(value.denominator))


def run(data, arrivals=()):
    return simulate_serving(ServingSimulationInput(prepared=data, arrivals=arrivals))


def rows(result, day=1, path='BASE'):
    return [r for r in result.products if r.path_id==path and r.day==D+timedelta(days=day)]


def complement(stock_s,stock_e):
    data=snapshot_data()
    second=add_product(data,quantity='10',line_quantity='1')
    for p in data['forecast']['predictions']:
        p.update(p25='10',p50='10',p75='10')
    data['ingredients'].append(data['ingredients'][0] | dict(ingredient_id=SECOND_INGREDIENT))
    data['recipes'][0]['lines'].append(dict(ingredient_id=SECOND_INGREDIENT,quantity='1',unit='g'))
    data['lots'][0]['on_hand_quantity']=str(stock_s)
    data['lots'].append(data['lots'][0] | dict(id=SECOND_LOT,ingredient_id=SECOND_INGREDIENT,on_hand_quantity=str(stock_e)))
    return data,second


def test_milk_progressive_equal_fractions_15_and_7_point_5():
    data=snapshot_data()
    second=add_product(data,quantity='10',line_quantity='.4')
    for p in data['forecast']['predictions']:
        if p['product_id']==PRODUCT:p.update(p25='20',p50='20',p75='20')
    data['ingredients'][0]['unit']='L'
    for r in data['recipes']:
        for line in r['lines']:line['unit']='L'
    data['recipes'][0]['lines'][0]['quantity']='.2'
    data['lots'][0].update(unit='L',on_hand_quantity='6')
    data['supplier_terms']=[]
    result=run(data)
    assert result.status=='COMPLETE' and result.decision_readiness=='NOT_ASSESSED'
    assert {r.product_id:rational(r.fulfilled) for r in rows(result)}=={PRODUCT:Fraction(15),second:Fraction(15,2)}
    assert [rational(r.fulfilled) for r in rows(result,day=2)]==[0,0]
    assert rational(result.lots[0].consumed)==6


@pytest.mark.parametrize('s,e,expected',[(20,0,(0,10)),(15,5,(5,10)),(10,5,(5,5))])
def test_g07_complementary_shortage_and_simultaneous_saturation(s,e,expected):
    data,second=complement(s,e)
    result=run(data)
    assert [rational(r.fulfilled) for r in rows(result)]==list(expected)
    if e==0:
        assert rational(next(r for r in result.lots if r.path_id=='BASE' and r.day==D+timedelta(days=1) and r.lot_id==LOT).ending)==10
        diagnostic={r.ingredient_id:rational(r.shortage) for r in result.ingredients if r.path_id=='BASE' and r.day==D+timedelta(days=1)}
        assert diagnostic=={INGREDIENT:0,SECOND_INGREDIENT:10}
        assert sum(rational(r.lost) for r in rows(result))==10


def test_permutations_snapshot_immutability_and_ambient_context():
    data,second=complement(15,5)
    original=deepcopy(data)
    request=ServingSimulationInput(prepared=data)
    expected=simulate_serving(request)
    data['lots'][0]['on_hand_quantity']='999'
    data['recipes'][0]['lines'][0]['quantity']='999'
    assert simulate_serving(request)==expected
    assert request.prepared.lots[0].on_hand_quantity==15
    other=deepcopy(original)
    for name in ('lots','recipes','products','ingredients','supplier_terms'):other[name].reverse()
    other['request']['product_ids'].reverse()
    other['forecast']['predictions'].reverse()
    for recipe in other['recipes']:recipe['lines'].reverse()
    with localcontext() as c:
        c.prec=2;c.Emax=2;c.Emin=-2;c.traps[Inexact]=True
        assert run(other)==expected
    with pytest.raises(ValidationError):expected.products[0].fulfilled.numerator='999'


def test_g04_expiry_day_usable_close_disposal_once_not_ending_waste():
    data=snapshot_data()
    for p in data['forecast']['predictions']:
        q='3' if p['forecast_date']<=D+timedelta(days=2) else '0'
        p.update(p25=q,p50=q,p75=q)
    data['ingredients'][0]['expiry_tracking']=True
    data['lots'][0].update(on_hand_quantity='4',expiry_date=D+timedelta(days=1))
    data['lots'].append(data['lots'][0] | dict(id=SECOND_LOT,on_hand_quantity='6',expiry_date=D+timedelta(days=3)))
    result=run(data)
    daily=[r for r in result.ingredients if r.path_id=='BASE']
    assert [rational(r.consumed) for r in daily]==[3,3,0,0,0,0,0]
    assert [rational(r.expired) for r in daily]==[1,0,3,0,0,0,0]
    assert sum(rational(r.other_waste) for r in daily)==0
    assert sum(rational(r.consumed)+rational(r.expired) for r in daily)==10


def test_fefo_expiry_receipt_uuid_unknown_last_and_already_expired():
    data=snapshot_data()
    for p in data['forecast']['predictions']:p.update(p25='3',p50='3',p75='3')
    base=data['lots'][0]
    data['lots']=[base | dict(id=UUID(int=400+i),on_hand_quantity='1',received_date=received,expiry_date=expiry)
        for i,(received,expiry) in enumerate([(D,D+timedelta(days=2)),(D-timedelta(days=1),D+timedelta(days=2)),
            (D-timedelta(days=1),D+timedelta(days=2)),(None,D+timedelta(days=2)),(D,None),(D-timedelta(days=3),D)])]
    data['issues']=[issue('MISSING_RECEIVED_DATE','WARNING','inventory_lot',UUID(int=403))]
    result=run(data)
    lots={r.lot_id:r for r in result.lots if r.path_id=='BASE' and r.day==D+timedelta(days=1)}
    assert [rational(lots[UUID(int=i)].consumed) for i in range(400,406)]==[1,1,1,0,0,0]
    assert rational(lots[UUID(int=405)].pre_service_expired)==1
    assert all(rational(r.pre_service_expired)==0 for r in result.lots if r.lot_id==UUID(int=405) and r.day>D+timedelta(days=1))
    assert result.issues[0].code=='MISSING_RECEIVED_DATE'


def test_future_operational_lot_never_becomes_inbound_explicit_arrival_does():
    data=snapshot_data()
    data['lots'][0].update(received_date=D+timedelta(days=2),on_hand_quantity='999')
    arrival=HypotheticalArrival(lot_id=SECOND_LOT,store_id=STORE,ingredient_id=INGREDIENT,
        unit='g',arrival_day=D+timedelta(days=2),quantity='6')
    result=run(data,[arrival])
    assert [rational(rows(result,day=day)[0].fulfilled) for day in range(1,8)]==[0,3,3,0,0,0,0]
    assert {r.lot_id for r in result.lots}=={SECOND_LOT}
    assert any(i.code=='FUTURE_RECEIPT_NOT_INBOUND' for i in result.issues)
    assert rational(next(r for r in result.lots if r.path_id=='BASE' and r.day==D+timedelta(days=2)).arrivals)==6


def test_arrival_today_then_expiry_close_today_is_usable():
    data=snapshot_data();data['lots']=[]
    arrival=dict(lot_id=SECOND_LOT,store_id=STORE,ingredient_id=INGREDIENT,unit='g',
        arrival_day=D+timedelta(days=1),expiry_date=D+timedelta(days=1),quantity='5')
    result=run(data,[arrival])
    assert rational(rows(result)[0].fulfilled)==3
    lot=next(r for r in result.lots if r.path_id=='BASE')
    assert rational(lot.close_expired)==2 and rational(lot.ending)==0


def test_dated_recipe_yield_loss_changes_daily_consumption():
    data=snapshot_data();data['lots'][0]['on_hand_quantity']='100000'
    first=data['recipes'][0]
    first.update(yield_quantity='10',process_loss_rate='.2',effective_to=D+timedelta(days=3))
    first['lines'][0]['quantity']='100'
    data['recipes'].append(first | dict(id=UUID(int=350),version=2,effective_from=D+timedelta(days=4),effective_to=None,
        lines=[dict(ingredient_id=INGREDIENT,quantity='200',unit='g')]))
    result=run(data)
    assert [rational(r.quantity) for r in result.contributions if r.path_id=='BASE']==[Fraction('37.5')]*3+[75]*4
    assert [r.recipe_id for r in rows(result,day=4)]==[UUID(int=350)]


def test_exact_repeating_fulfillment_and_lot_remainders_are_not_decimal_clipped():
    data,second=complement(1,0)
    # A blocked by E. B uses 3g/serving => serves exactly 1/3.
    data['recipes'][1]['lines'][0]['quantity']='3'
    result=run(data)
    b=next(r for r in rows(result) if r.product_id==second)
    assert rational(b.fulfilled)==Fraction(1,3)
    assert b.fulfilled.decimal_view==Decimal('0.'+'3'*50)
    assert rational(b.lost)==Fraction(29,3)
    assert rational(next(r for r in result.contributions if r.path_id=='BASE' and r.product_id==second).quantity)==1
    assert rational(next(r for r in result.lots if r.path_id=='BASE' and r.lot_id==LOT).ending)==0
    assert rational(b.fulfilled)-Fraction(b.fulfilled.decimal_view)==Fraction(1,3*10**50)


def test_zero_demand_keeps_ending_inventory_and_paths_are_isolated():
    data=snapshot_data()
    for p in data['forecast']['predictions']:p.update(p25='0',p50='2',p75='4')
    data['lots'][0]['on_hand_quantity']='10'
    result=run(data)
    assert sum(rational(r.fulfilled) for r in result.products if r.path_id=='BASE')==10
    assert sum(rational(r.fulfilled) for r in result.products if r.path_id=='HIGH')==10
    low=[r for r in result.lots if r.path_id=='LOW']
    assert all(rational(r.ending)==10 and rational(r.consumed)==rational(r.close_expired)==0 for r in low)
    assert all(rational(r.fulfilled)==rational(r.lost)==0 for r in result.products if r.path_id=='LOW')


def test_exact_conservation_product_ingredient_lot_day_path():
    data,second=complement('17.2','3.1')
    result=run(data)
    for row in result.products:assert rational(row.requested)==rational(row.fulfilled)+rational(row.lost)
    for row in result.lots:
        assert rational(row.opening)+rational(row.arrivals)==sum(rational(getattr(row,n)) for n in ('pre_service_expired','consumed','close_expired','other_waste','ending'))
        assert all(rational(getattr(row,n))>=0 for n in ('opening','consumed','ending'))
    for row in result.ingredients:
        contributions=[r for r in result.contributions if (r.path_id,r.day,r.ingredient_id)==(row.path_id,row.day,row.ingredient_id)]
        lots=[r for r in result.lots if (r.path_id,r.day,r.ingredient_id)==(row.path_id,row.day,row.ingredient_id)]
        assert rational(row.consumed)==sum(rational(r.quantity) for r in contributions)==sum(rational(r.consumed) for r in lots)
        assert rational(row.ending)==sum(rational(r.ending) for r in lots)
        assert rational(row.shortage)==max(rational(row.requested)-rational(row.available),0)


def test_known_blockers_stop_output_even_when_bom_complete_and_warnings_survive():
    data=snapshot_data();data['ingredients'][0]['expiry_tracking']=True
    data['issues']=[issue('MISSING_EXPIRY','DATA_BLOCKER','inventory_lot',LOT)]
    result=run(data)
    assert result.status=='DATA_BLOCKED' and result.bom.status=='COMPLETE'
    assert not result.products and not result.lots
    assert result.input.prepared.source_references==result.bom.prepared.source_references
    assert result.decision_readiness=='DATA_BLOCKED'
    data['lots']=[];data['issues']=[]
    result=run(data,[dict(lot_id=SECOND_LOT,store_id=STORE,ingredient_id=INGREDIENT,unit='g',
        arrival_day=D+timedelta(days=1),quantity='1')])
    assert result.status=='DATA_BLOCKED' and any(i.code=='MISSING_ARRIVAL_EXPIRY' for i in result.issues)


def test_missing_recipe_zero_demand_does_not_bypass_blocker():
    data=snapshot_data();data['recipes']=[]
    for p in data['forecast']['predictions']:p.update(p25='0',p50='0',p75='0')
    data['issues']=[issue('MISSING_RECIPE','DATA_BLOCKER','product',PRODUCT)]
    result=run(data)
    assert result.status=='DATA_BLOCKED' and not result.products
    assert len([i for i in result.issues if i.day])==7


@pytest.mark.parametrize('defect',['float','bool','nan','unit','store','outside_window','duplicate','expiry','forged'])
def test_input_arrival_revalidation_rejects_invalid_and_forged(defect):
    data=snapshot_data()
    a=dict(lot_id=SECOND_LOT,store_id=STORE,ingredient_id=INGREDIENT,unit='g',
        arrival_day=D+timedelta(days=1),quantity='1')
    if defect in ('float','bool','nan'):a['quantity']={'float':1.0,'bool':True,'nan':Decimal('NaN')}[defect]
    elif defect=='unit':a['unit']='kg'
    elif defect=='store':a['store_id']=UUID(int=999)
    elif defect=='outside_window':a['arrival_day']=D
    elif defect=='expiry':a['expiry_date']=D
    arrivals=[a,a] if defect=='duplicate' else [a]
    with pytest.raises(ValidationError):
        if defect=='forged':
            good=ServingSimulationInput(prepared=data)
            bad=good.prepared.recipes[0].model_copy(update={'yield_quantity':Decimal(0)})
            simulate_serving(good.model_copy(update={'prepared':good.prepared.model_copy(update={'recipes':(bad,)})}))
        else:run(data,arrivals)


def test_numeric_capacity_and_output_boundary_return_no_partial_success():
    data=snapshot_data()
    data['lots'][0]['on_hand_quantity']='1e-2000'
    result=run(data)
    assert result.status=='ARITHMETIC_BLOCKED' and not result.products and not result.lots
    assert result.issues[-1].code=='SERVING_NUMERIC_BOUNDARY'
    # Each source/BOM is within existing boundary; aggregate available is not.
    data['lots'][0]['on_hand_quantity']='1e308'
    data['lots'].append(data['lots'][0] | dict(id=SECOND_LOT))
    result=run(data)
    assert result.status=='ARITHMETIC_BLOCKED' and not result.ingredients


def test_exact_quantity_canonical_shape_and_display_cannot_be_forged():
    with pytest.raises(ValidationError):Quantity(numerator='2',denominator='6',decimal_view='.333')
    with pytest.raises(ValidationError):Quantity(numerator='1',denominator='3',decimal_view='.333')
    with pytest.raises(ValidationError):Quantity(numerator=True,denominator='1',decimal_view='1')


def test_exact_repeating_lot_balance_is_carried_between_days():
    data=snapshot_data()
    for p in data['forecast']['predictions']:p.update(p25='1',p50='1',p75='1')
    data['recipes'][0]['yield_quantity']='3'
    data['lots'][0]['on_hand_quantity']='1'
    result=run(data)
    lots=[r for r in result.lots if r.path_id=='BASE']
    assert [rational(r.ending) for r in lots]==[Fraction(2,3),Fraction(1,3),0,0,0,0,0]
    assert [rational(r.opening) for r in lots]==[1,Fraction(2,3),Fraction(1,3),0,0,0,0]
    assert [rational(rows(result,day=d)[0].fulfilled) for d in range(1,8)]==[1,1,1,0,0,0,0]
    assert sum(rational(r.consumed) for r in lots)==1


def test_arrival_order_invariance_and_unknown_cost_warning_provenance_retained():
    data=snapshot_data()
    data['lots'][0].update(received_date=None,unit_cost=None,on_hand_quantity='2')
    data['issues']=[issue('MISSING_COST','WARNING','inventory_lot',LOT),
                    issue('MISSING_RECEIVED_DATE','WARNING','inventory_lot',LOT)]
    arrivals=[dict(lot_id=UUID(int=500+i),store_id=STORE,ingredient_id=INGREDIENT,unit='g',
        arrival_day=D+timedelta(days=1),quantity='1',expiry_date=D+timedelta(days=i+1)) for i in range(2)]
    result=run(data,arrivals)
    assert run(data,list(reversed(arrivals)))==result
    assert {i.code for i in result.issues}=={'MISSING_COST','MISSING_RECEIVED_DATE'}
    assert result.input.prepared.lots[0].received_date is None and result.input.prepared.lots[0].unit_cost is None
    assert result.input.prepared.forecast.input_fingerprint=='forecast-fixture'
    assert result.input.prepared.source_references
    assert {r.lot_id:rational(r.consumed) for r in result.lots if r.path_id=='BASE' and r.day==D+timedelta(days=1)}=={
        LOT:1,UUID(int=500):1,UUID(int=501):1}


def test_programming_error_is_not_converted_to_numeric_or_success(monkeypatch):
    import app.application.use_cases.serving as boundary
    def broken(*args,**kwargs):raise RuntimeError('programming bug')
    monkeypatch.setattr(boundary,'simulate',broken)
    with pytest.raises(RuntimeError,match='programming bug'):run(snapshot_data())


def test_domain_framework_provider_io_import_guard(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    script='''
import sys
class Guard:
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {'pydantic','sqlalchemy','psycopg','fastapi','httpx','numpy','lightgbm'} or name.startswith(('app.application','app.api','app.models','app.infrastructure')):
            raise AssertionError(name)
sys.meta_path.insert(0,Guard())
from app.domain.decision.serving import allocate
from fractions import Fraction as F
from uuid import UUID
a,b,s,e=(UUID(int=i) for i in range(1,5))
assert allocate({a:F(10),b:F(10)},{a:{s:F(1),e:F(1)},b:{s:F(1)}},{s:F(15),e:F(5)})=={a:F(5),b:F(10)}
'''
    result=subprocess.run([sys.executable,'-c',script],cwd=tmp_path,capture_output=True,text=True,
        env=os.environ | {'PYTHONPATH':str(Path(__file__).resolve().parents[2]),'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0,result.stderr
    assert list(tmp_path.iterdir())==[]
