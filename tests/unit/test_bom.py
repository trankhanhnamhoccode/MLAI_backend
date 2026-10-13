"""Hand-derived expectations for actual pure BOM, not simulation fixtures."""
from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.decision_execution import PreparedDecisionInput
from app.application.use_cases.bom import expand_bom
from tests.unit.test_decision_execution import D, PRODUCT, INGREDIENT, RECIPE, snapshot_data, issue


def capture(**changes):
    return PreparedDecisionInput.model_validate(snapshot_data() | changes)


def test_yield_loss_whole_recipe_40_cups_is_5000_ml():
    data = snapshot_data()
    data['ingredients'][0]['unit'] = 'ml'
    data['lots'] = []
    data['supplier_terms'] = []
    data['recipes'][0].update(yield_quantity='10', process_loss_rate='.2')
    data['recipes'][0]['lines'][0].update(quantity='1000', unit='ml')
    for point in data['forecast']['predictions']:
        point.update(p25='40', p50='40', p75='40')
    result = expand_bom(PreparedDecisionInput.model_validate(data))
    assert result.status == 'COMPLETE'
    assert len(result.contributions) == len(result.totals) == 21
    assert {row.quantity for row in result.contributions} == {Decimal('5000')}
    assert {row.quantity for row in result.totals} == {Decimal('5000')}
    assert {row.unit for row in result.totals} == {'ml'}


def test_dated_recipe_switch_inclusive_no_boundary_overlap():
    data = snapshot_data()
    first = data['recipes'][0]
    first['effective_to'] = D+timedelta(days=3)
    second = first | dict(id=UUID(int=100), version=2, effective_from=D+timedelta(days=4), effective_to=None,
                         lines=[dict(ingredient_id=INGREDIENT, quantity='2', unit='g')])
    data['recipes'].append(second)
    result = expand_bom(PreparedDecisionInput.model_validate(data))
    base = [r for r in result.contributions if r.path_id == 'BASE']
    assert [r.recipe_id for r in base] == [RECIPE]*3+[second['id']]*4
    assert [r.quantity for r in base] == [Decimal(3)]*3+[Decimal(6)]*4


def test_missing_recipe_returns_dated_blockers_without_partial_success():
    data = snapshot_data()
    data['recipes'][0]['effective_to'] = D+timedelta(days=3)
    data['issues'] = [issue('MISSING_RECIPE', 'DATA_BLOCKER', 'product', PRODUCT)]
    result = expand_bom(PreparedDecisionInput.model_validate(data))
    assert result.status == 'DATA_BLOCKED'
    assert not result.paths and not result.contributions and not result.totals
    gaps = [i for i in result.issues if i.day is not None]
    assert [i.day for i in gaps] == [D+timedelta(days=i) for i in range(4,8)]
    assert all(i.affected[0].entity_id == PRODUCT for i in gaps)


def test_other_blocker_allows_bom_math_but_not_decision_readiness():
    data = snapshot_data()
    data['ingredients'][0]['expiry_tracking'] = True
    from tests.unit.test_decision_execution import LOT
    data['issues'] = [issue('MISSING_EXPIRY', 'DATA_BLOCKER', 'inventory_lot', LOT)]
    result = expand_bom(PreparedDecisionInput.model_validate(data))
    assert result.status == 'COMPLETE'
    assert result.decision_readiness == 'DATA_BLOCKED'
    assert result.contributions
    assert result.issues[0].code == 'MISSING_EXPIRY'


def test_hostile_ambient_context_does_not_change_whole_yield_math():
    prepared = capture()
    normal = expand_bom(prepared)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        assert expand_bom(prepared) == normal


def test_invalid_copy_rejected_before_any_output():
    prepared = capture()
    forged = prepared.model_copy(update={'recipes':(prepared.recipes[0].model_copy(update={'yield_quantity': Decimal(0)}),)})
    with pytest.raises(ValidationError):
        expand_bom(forged)


def add_product(data, *, quantity='8', line_quantity='2'):
    """Captured fixture values only; no expected-output computation."""
    product, recipe = UUID(int=101), UUID(int=102)
    data['request']['product_ids'].append(product)
    data['products'].append(data['products'][0] | dict(product_id=product, sku='SECOND'))
    data['forecast']['predictions'].extend(p | dict(product_id=product, p25=quantity, p50=quantity, p75=quantity)
                                         for p in list(data['forecast']['predictions']))
    data['recipes'].append(data['recipes'][0] | dict(id=recipe, product_id=product,
        lines=[dict(ingredient_id=INGREDIENT, quantity=line_quantity, unit='g')]))
    return product


def test_shared_ingredient_keeps_product_contributions_and_exact_daily_totals():
    data = snapshot_data()
    second = add_product(data)
    result = expand_bom(PreparedDecisionInput.model_validate(data))
    rows = [c for c in result.contributions if c.path_id=='BASE' and c.day==D+timedelta(days=1)]
    assert {(c.product_id,c.quantity) for c in rows} == {(PRODUCT,Decimal(3)), (second,Decimal(16))}
    assert [t.quantity for t in result.totals if t.path_id=='BASE'] == [Decimal(19)]*7
    assert len(result.contributions)==42 and len(result.totals)==21


def test_multiple_exact_units_unused_ingredients_and_no_inventory_safety_pack_netting():
    data = snapshot_data()
    second, unused = UUID(int=105), UUID(int=106)
    data['ingredients'].extend([data['ingredients'][0] | dict(ingredient_id=second,unit='ml'),
                               data['ingredients'][0] | dict(ingredient_id=unused,unit='kg')])
    data['recipes'][0]['lines'].append(dict(ingredient_id=second,quantity='2',unit='ml'))
    data['constraints']=[dict(id=UUID(int=109),store_id=data['request']['store_id'],version=1,
        kind='MIN_SAFETY_STOCK',ingredient_id=INGREDIENT,value='999',unit='g',effective_from=D)]
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    totals=[t for t in result.totals if t.path_id=='BASE' and t.day==D+timedelta(days=1)]
    assert {(t.ingredient_id,t.unit,t.quantity) for t in totals} == {
        (INGREDIENT,'g',Decimal(3)),(second,'ml',Decimal(6))}
    assert unused not in {t.ingredient_id for t in result.totals}
    assert len(result.totals)==42


def test_zero_demand_ordered_paths_full_scope_and_positive_recipe_lines():
    data=snapshot_data()
    for p in data['forecast']['predictions']:
        p.update(p25='0',p50='0',p75='0')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    assert tuple(p.path_id for p in result.paths)==('LOW','BASE','HIGH')
    assert all(len(p.demands)==7 for p in result.paths)
    assert len(result.contributions)==21 and len(result.totals)==21
    assert {c.quantity for c in result.contributions}=={Decimal(0)}
    assert result.decision_readiness=='NOT_ASSESSED'


def test_low_base_high_monotonic_and_design_labels_only():
    result=expand_bom(capture())
    for day in (D+timedelta(days=i) for i in range(1,8)):
        assert [t.quantity for t in result.totals if t.day==day]==[Decimal(2),Decimal(3),Decimal(4)]
    assert set(result.model_dump()) == {'schema_version','bom_version','status','decision_readiness',
        'prepared','paths','contributions','totals','issues'}
    assert all('probability' not in t.model_dump() for t in result.totals)


def test_empty_recipe_blocks_even_zero_demand():
    data=snapshot_data()
    data['recipes'][0]['lines']=[]
    data['issues']=[issue('MISSING_RECIPE','DATA_BLOCKER','product',PRODUCT)]
    for p in data['forecast']['predictions']:
        p.update(p25='0',p50='0',p75='0')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    assert result.status=='DATA_BLOCKED'
    assert len([i for i in result.issues if i.code=='EMPTY_RECIPE'])==7
    assert not result.paths and not result.contributions and not result.totals


@pytest.mark.parametrize('defect',['overlap','wrong_unit','duplicate_line','missing_without_issue'])
def test_malformed_recipe_snapshot_rejected_without_fallback(defect):
    prepared=capture()
    if defect=='overlap':
        bad=prepared.model_copy(update={'recipes':prepared.recipes+(prepared.recipes[0].model_copy(update={'id':UUID(int=999)}),)})
    elif defect=='missing_without_issue':
        bad=prepared.model_copy(update={'recipes':()})
    else:
        recipe=prepared.recipes[0]
        lines=recipe.lines*2 if defect=='duplicate_line' else (recipe.lines[0].model_copy(update={'unit':'kg'}),)
        bad=prepared.model_copy(update={'recipes':(recipe.model_copy(update={'lines':lines}),)})
    with pytest.raises(ValidationError):
        expand_bom(bad)


def test_repeating_division_single_boundary_and_exact_sum_exceeds_50_digits():
    data=snapshot_data()
    data['recipes'][0]['yield_quantity']='3'
    for p in data['forecast']['predictions']:
        p.update(p25='3',p50='3',p75='3')
    second=add_product(data,quantity='1',line_quantity='1')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    one_third=Decimal('0.'+'3'*50)
    total=Decimal('1.'+'3'*50)
    assert {c.quantity for c in result.contributions if c.product_id==second}=={one_third}
    assert {c.quantity for c in result.contributions if c.product_id==PRODUCT}=={Decimal(1)}
    assert {t.quantity for t in result.totals}=={total}
    assert len(total.as_tuple().digits)==51
    from fractions import Fraction
    assert Fraction(total)==Fraction(1)+Fraction(one_third)
    with localcontext() as ctx:
        ctx.prec=3
        ctx.Emin=-2
        ctx.Emax=2
        ctx.traps[__import__('decimal').Inexact]=True
        assert expand_bom(PreparedDecisionInput.model_validate(data))==result


def test_rational_loss_avoids_intermediate_division_rounding():
    data=snapshot_data()
    data['recipes'][0].update(yield_quantity='7',process_loss_rate='.3')
    for p in data['forecast']['predictions']:
        p.update(p25='1',p50='1',p75='1')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    # 1/(7*(1-.3)) = 10/49, rounded once to 50 significant digits.
    expected=Decimal('0.20408163265306122448979591836734693877551020408163')
    assert {c.quantity for c in result.contributions}=={expected}


def test_input_ordering_does_not_change_output_or_mutate_input():
    from copy import deepcopy
    data=snapshot_data()
    add_product(data)
    extra=UUID(int=105)
    data['ingredients'].append(data['ingredients'][0] | dict(ingredient_id=extra,unit='ml'))
    data['recipes'][0]['lines'].append(dict(ingredient_id=extra,quantity='2',unit='ml'))
    data['issues']=[issue('OPTIONAL_INFO','WARNING','ingredient',INGREDIENT),
                    issue('OTHER_INFO','INFO','ingredient',extra)]
    data['source_references'].append(data['source_references'][0] | dict(entity='recipe',entity_id=RECIPE,version=1))
    original=deepcopy(data)
    prepared=PreparedDecisionInput.model_validate(data)
    before=prepared.model_dump()
    expected=expand_bom(prepared)
    reordered=deepcopy(data)
    for name in ('products','ingredients','recipes','lots','supplier_terms','constraints','issues','assumptions','source_references'):
        reordered[name].reverse()
    reordered['forecast']['predictions'].reverse()
    for recipe in reordered['recipes']:
        recipe['lines'].reverse()
    assert expand_bom(PreparedDecisionInput.model_validate(reordered))==expected
    assert data==original and prepared.model_dump()==before
    with pytest.raises(ValidationError):
        expected.totals[0].quantity=Decimal(99)


def test_captured_provenance_and_issues_survive_live_caller_changes():
    data=snapshot_data()
    data['issues']=[issue('QUALITY_UNPROVEN','WARNING','product',PRODUCT)]
    data['forecast']['warnings']=[dict(code='LOW_COVERAGE',severity='WARNING',field='quantiles',
        entity='forecast_run',impact='Unproven calibration',product_id=PRODUCT)]
    snapshot=PreparedDecisionInput.model_validate(data)
    result=expand_bom(snapshot)
    data['forecast']['predictions'][0]['p50']='999'
    data['recipes'][0]['lines'][0]['quantity']='999'
    data['supplier_terms'][0]['pack_cost']='999'
    data['issues'][0]['impact']='changed live source'
    assert expand_bom(snapshot)==result
    assert result.prepared.forecast.model_type=='historical_quantile_baseline'
    assert result.prepared.forecast.input_fingerprint=='forecast-fixture'
    assert result.prepared.source_references==snapshot.source_references
    assert result.prepared.forecast.warnings[0].impact=='Unproven calibration'
    assert result.issues[0].impact=='Capability unavailable'


def test_constructed_input_and_nonfinite_float_bool_cannot_bypass_boundary():
    prepared=capture()
    for value in (Decimal('NaN'),Decimal('Infinity'),1.0,True):
        recipe=prepared.recipes[0].model_copy(update={'yield_quantity':value})
        with pytest.raises(ValidationError):
            expand_bom(prepared.model_copy(update={'recipes':(recipe,)}))
    with pytest.raises(ValidationError):
        expand_bom(PreparedDecisionInput.model_construct(**(prepared.model_dump() | {'products':()})))


def test_extreme_scaled_quantities_and_exact_subnormal_no_fake_zero():
    from decimal import MIN_EMIN
    data=snapshot_data()
    for value in ('1e300','1e-2000000',f'1e{MIN_EMIN-49}'):
        for p in data['forecast']['predictions']:
            p.update(p25=value,p50=value,p75=value)
        result=expand_bom(PreparedDecisionInput.model_validate(data))
        assert result.status=='COMPLETE'
        assert {c.quantity for c in result.contributions}=={Decimal(value)}
        assert {t.quantity for t in result.totals}=={Decimal(value)}


@pytest.mark.parametrize('defect,code',[('output_boundary','BOM_NUMERIC_BOUNDARY'),
    ('underflow','BOM_NUMERIC_UNDERFLOW'),('loss_capacity','BOM_NUMERIC_CAPACITY'),
    ('aggregate_capacity','BOM_NUMERIC_CAPACITY'),('coefficient_capacity','BOM_NUMERIC_CAPACITY')])
def test_numeric_failure_is_typed_atomic_and_not_fabricated_zero(defect,code):
    from decimal import MAX_EMAX, MIN_EMIN
    data=snapshot_data()
    if defect=='output_boundary':
        value='1e300'
        data['recipes'][0]['lines'][0]['quantity']='1e300'
    elif defect=='underflow':
        value=f'1e{MIN_EMIN-49}'
        data['recipes'][0]['yield_quantity']='100'
    elif defect=='loss_capacity':
        value='1'
        data['recipes'][0]['process_loss_rate']='1e-10001'
    elif defect=='coefficient_capacity':
        value='1.'+'1'*10000
    else:
        value='1e300'
        add_product(data,quantity='1e-10000',line_quantity='1')
    for p in data['forecast']['predictions']:
        if p['product_id']==PRODUCT:
            p.update(p25=value,p50=value,p75=value)
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    assert result.status=='ARITHMETIC_BLOCKED'
    assert result.decision_readiness=='DATA_BLOCKED'
    assert not result.paths and not result.contributions and not result.totals
    assert result.issues[-1].code==code
    assert result.issues[-1].day==D+timedelta(days=1)


def test_domain_decimal_exponent_bounds_and_overflow_without_public_boundary_relaxation():
    from decimal import MAX_EMAX
    from app.domain.demand.arithmetic import contribution_quantity, BOMArithmeticError
    for value in ('1e2000000','1e-2000000'):
        assert contribution_quantity(Decimal(value),Decimal(1),Decimal(1),Decimal(0))==Decimal(value)
    with pytest.raises(BOMArithmeticError) as error:
        contribution_quantity(Decimal(f'9e{MAX_EMAX}'),Decimal(2),Decimal(1),Decimal(0))
    assert error.value.code=='BOM_NUMERIC_OVERFLOW'
    data=snapshot_data()
    for p in data['forecast']['predictions']:
        p.update(p25=Decimal('1e2000000'),p50=Decimal('1e2000000'),p75=Decimal('1e2000000'))
    with pytest.raises(ValidationError):
        expand_bom(PreparedDecisionInput.model_validate(data))


def test_g01_bom_only_normal_week_100g_daily_700g_total():
    data=snapshot_data()
    data['recipes'][0].update(yield_quantity='10',process_loss_rate='.2')
    data['recipes'][0]['lines'][0]['quantity']='100'
    for p in data['forecast']['predictions']:
        p.update(p25='8',p50='8',p75='8')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    assert {t.quantity for t in result.totals}=={Decimal(100)}
    assert sum(t.quantity for t in result.totals if t.path_id=='BASE')==Decimal(700)


def test_g13_shared_ingredient_design_totals_are_not_calibrated_quantiles():
    data=snapshot_data()
    add_product(data,quantity='0',line_quantity='1')
    for p in data['forecast']['predictions']:
        p.update(p25='0',p50='5',p75='10')
    result=expand_bom(PreparedDecisionInput.model_validate(data))
    assert [(t.path_id,t.quantity) for t in result.totals if t.day==D+timedelta(days=1)]==[
        ('LOW',Decimal(0)),('BASE',Decimal(10)),('HIGH',Decimal(20))]


@pytest.mark.parametrize('last,expected',[('2','2'),('3','4')])
def test_precision50_half_even_ties(last,expected):
    from app.domain.demand.arithmetic import contribution_quantity
    quantity=Decimal('1.'+'0'*48+last+'5')
    assert contribution_quantity(quantity,Decimal(1),Decimal(1),Decimal(0))==Decimal('1.'+'0'*48+expected)


def test_near_one_loss_is_exact_before_division_not_ambient_rounded_to_one():
    data=snapshot_data()
    data['recipes'][0]['process_loss_rate']='0.'+'9'*60
    for p in data['forecast']['predictions']:
        p.update(p25='1',p50='1',p75='1')
    prepared=PreparedDecisionInput.model_validate(data)
    with localcontext() as context:
        context.prec=2
        context.traps[__import__('decimal').Inexact]=True
        result=expand_bom(prepared)
    assert {c.quantity for c in result.contributions}=={Decimal('1e60')}


def test_bom_domain_import_isolated_from_framework_persistence_and_providers(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    script='''
import sys
class Guard:
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {'pydantic','sqlalchemy','psycopg','fastapi','httpx','lightgbm','numpy'} or name.startswith(('app.application','app.models','app.infrastructure','app.api')):
            raise AssertionError(name)
sys.meta_path.insert(0,Guard())
from app.domain.demand.bom import expand_dated_bom
from app.domain.demand.arithmetic import contribution_quantity
from decimal import Decimal
assert contribution_quantity(Decimal(40),Decimal(1000),Decimal(10),Decimal('.2'))==Decimal(5000)
'''
    result=subprocess.run([sys.executable,'-c',script],cwd=tmp_path,text=True,capture_output=True,
        env=os.environ | {'PYTHONPATH':str(Path(__file__).resolve().parents[2]),'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0,result.stderr
    assert list(tmp_path.iterdir())==[]
