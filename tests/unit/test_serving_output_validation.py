"""Mutate actual outputs; independent invariants, never simulator replay."""
from fractions import Fraction
from pydantic import ValidationError
import pytest

from app.application.contracts.serving import ProductServingDay, ServingSimulationResult
from app.application.use_cases.serving import _quantity, simulate_serving
from scripts.demo_serving_fefo import milk_input
from datetime import timedelta
from uuid import UUID
import json
from app.application.contracts.bom import BOMIssue
from tests.unit.test_serving import run
from tests.unit.test_decision_execution import snapshot_data, issue, D, PRODUCT, INGREDIENT, LOT


def quantity(value):
    return _quantity(Fraction(value)).model_dump()


@pytest.fixture(scope='module')
def valid():
    return simulate_serving(milk_input())


def test_standalone_product_rejects_requested1_fulfilled2_lost0():
    row=simulate_serving(milk_input()).products[0].model_dump()
    row.update(requested=_quantity(Fraction(1)),fulfilled=_quantity(Fraction(2)),lost=_quantity(Fraction(0)))
    with pytest.raises(ValidationError,match='Product'):
        ProductServingDay.model_validate(row)


def test_forged_recipe_attribution_preserving_totals_rejected():
    result=simulate_serving(milk_input())
    # Different captured recipe, same all quantities and all aggregate sums.
    other=result.products[1].recipe_id
    changed=result.products[0].model_copy(update={'recipe_id':other})
    forged=result.model_copy(update={'products':(changed,*result.products[1:])})
    with pytest.raises(ValidationError,match='recipe'):
        ServingSimulationResult.model_validate(forged)


@pytest.mark.parametrize('group',['products','contributions','lots','ingredients'])
@pytest.mark.parametrize('defect',['missing','duplicate','foreign','unit','date','path'])
def test_row_scope_coverage_mutations(valid,group,defect):
    data=valid.model_dump()
    row=data[group][0]
    if defect=='missing':data[group]=data[group][1:]
    elif defect=='duplicate':data[group]=(*data[group],row)
    elif defect=='foreign':row[{'products':'product_id','contributions':'ingredient_id','lots':'lot_id','ingredients':'ingredient_id'}[group]]=UUID(int=9999)
    elif defect=='unit':row['unit']='wrong-unit'
    elif defect=='date':row['day']-=timedelta(days=1)
    else:row['path_id']='OTHER'
    with pytest.raises(ValidationError):ServingSimulationResult.model_validate(data)


@pytest.mark.parametrize('field,value',[('requested',21),('fulfilled',16),('lost',0)])
def test_product_quantities_invalid(valid,field,value):
    data=valid.model_dump();data['products'][0][field]=quantity(value)
    with pytest.raises(ValidationError):ServingSimulationResult.model_validate(data)


def test_balanced_product_requested_does_not_match_captured_forecast(valid):
    data=valid.model_dump();data['products'][0].update(requested=quantity(21),lost=quantity(6))
    with pytest.raises(ValidationError,match='forecast'):ServingSimulationResult.model_validate(data)


def test_canonical_but_wrong_fulfilled_contribution_rejected(valid):
    data=valid.model_dump();data['contributions'][0]['quantity']=quantity(4)
    with pytest.raises(ValidationError,match='Contribution'):ServingSimulationResult.model_validate(data)


@pytest.mark.parametrize('field',['opening','arrivals','consumed','ending','pre_service_expired','close_expired','other_waste'])
def test_lot_standalone_balance_mutations(valid,field):
    data=valid.model_dump();data['lots'][0][field]=quantity(1)
    with pytest.raises(ValidationError,match='Lot'):ServingSimulationResult.model_validate(data)


def test_balanced_wrong_source_opening_and_continuity(valid):
    for day_index in (0,1):
        data=valid.model_dump()
        data['lots'][day_index].update(opening=quantity(7),ending=quantity(1 if day_index==0 else 7))
        with pytest.raises(ValidationError,match='opening'):ServingSimulationResult.model_validate(data)


@pytest.mark.parametrize('field',['requested','available','shortage','consumed','expired','ending','other_waste'])
def test_ingredient_mutations(valid,field):
    data=valid.model_dump();data['ingredients'][0][field]=quantity(1)
    with pytest.raises(ValidationError,match='Ingredient'):ServingSimulationResult.model_validate(data)


def test_balanced_ingredient_requested_and_shortage_wrong_capture(valid):
    data=valid.model_dump();data['ingredients'][0].update(requested=quantity(9),shortage=quantity(3))
    with pytest.raises(ValidationError,match='requested'):ServingSimulationResult.model_validate(data)


def test_expiry_disposal_moved_to_wrong_day_with_conserved_balance():
    data=snapshot_data();data['lots'][0].update(on_hand_quantity='4',expiry_date=D+timedelta(days=1))
    result=run(data)
    mutated=result.model_dump()
    mutated['lots'][0].update(close_expired=quantity(0),ending=quantity(2)) # LOW consumes2, remainder2 must expire.
    with pytest.raises(ValidationError,match='expiry'):ServingSimulationResult.model_validate(mutated)
    mutated=result.model_dump()
    mutated['lots'][0].update(pre_service_expired=quantity(4),consumed=quantity(0),close_expired=quantity(0),ending=quantity(0))
    with pytest.raises(ValidationError,match='expiry'):ServingSimulationResult.model_validate(mutated)


def test_expired_stock_consumption_and_disposal_repeated_rejected():
    data=snapshot_data();data['lots'][0]['expiry_date']=D
    result=run(data)
    mutated=result.model_dump();mutated['lots'][0].update(pre_service_expired=quantity(29),consumed=quantity(1))
    with pytest.raises(ValidationError,match='expiry'):ServingSimulationResult.model_validate(mutated)
    mutated=result.model_dump();mutated['lots'][1].update(opening=quantity(1),pre_service_expired=quantity(1))
    with pytest.raises(ValidationError,match='opening'):ServingSimulationResult.model_validate(mutated)


def arrival_result():
    data=snapshot_data();data['lots']=[]
    return run(data,[dict(lot_id=UUID(int=710),store_id=data['request']['store_id'],ingredient_id=INGREDIENT,
        unit='g',arrival_day=D+timedelta(days=2),quantity='6')])


def test_stock_before_arrival_and_wrong_arrival_amount_rejected():
    result=arrival_result()
    data=result.model_dump();data['lots'][0].update(arrivals=quantity(1),consumed=quantity(1))
    with pytest.raises(ValidationError,match='arrivals'):ServingSimulationResult.model_validate(data)
    data=result.model_dump();data['lots'][1].update(arrivals=quantity(7),ending=quantity(5)) # LOW consumption2.
    with pytest.raises(ValidationError,match='arrivals'):ServingSimulationResult.model_validate(data)


def test_excluded_future_lot_cannot_be_added_or_warning_erased():
    data=snapshot_data();data['lots'][0]['received_date']=D+timedelta(days=2)
    result=run(data)
    mutated=result.model_dump();mutated['issues']=[]
    with pytest.raises(ValidationError,match='warning'):ServingSimulationResult.model_validate(mutated)
    # Forge a canonical zero lot flow; foreign eligibility must still reject it.
    lot=simulate_serving(milk_input()).lots[0].model_dump()
    lot.update(lot_id=LOT,ingredient_id=INGREDIENT,unit='g')
    for field in ('opening','arrivals','pre_service_expired','consumed','close_expired','other_waste','ending'):lot[field]=quantity(0)
    mutated=result.model_dump();mutated['lots']=(lot,)
    with pytest.raises(ValidationError,match='Lot'):ServingSimulationResult.model_validate(mutated)


def test_fefo_later_lot_consumption_rejected_even_when_all_totals_and_continuity_match():
    data=snapshot_data()
    for p in data['forecast']['predictions']:
        amount='3' if p['forecast_date']==D+timedelta(days=1) else '0'
        p.update(p25=amount,p50=amount,p75=amount)
    data['lots'][0]['on_hand_quantity']='5'
    second=UUID(int=712)
    data['lots'].append(data['lots'][0] | dict(id=second,received_date=D))
    data['lots'][0]['received_date']=D-timedelta(days=1)
    result=run(data)
    modified=result.model_dump()
    for r in modified['lots']:
        if r['path_id']!='BASE':continue
        first=r['lot_id']==LOT
        r.update(consumed=quantity(0 if first else (3 if r['day']==D+timedelta(days=1) else 0)),
                 opening=quantity(5 if r['day']==D+timedelta(days=1) or first else 2),ending=quantity(5 if first else 2))
    with pytest.raises(ValidationError,match='FEFO'):ServingSimulationResult.model_validate(modified)


def test_provenance_or_input_bom_mismatch_rejected(valid):
    data=valid.model_dump();data['bom']['prepared']['forecast']['input_fingerprint']='wrong'
    with pytest.raises(ValidationError,match='provenance'):ServingSimulationResult.model_validate(data)
    data=valid.model_dump();data['input']['prepared']['source_references'][0]['origin']='UNKNOWN'
    with pytest.raises(ValidationError,match='provenance'):ServingSimulationResult.model_validate(data)


def test_captured_bom_issues_cannot_be_erased_even_if_both_outputs_erased():
    data=snapshot_data();data['issues']=[issue('NOTE','WARNING','product',PRODUCT)]
    result=run(data)
    for erase_bom in (False,True):
        mutated=result.model_dump();mutated['issues']=[]
        if erase_bom:mutated['bom']['issues']=[]
        with pytest.raises(ValidationError,match='issues'):ServingSimulationResult.model_validate(mutated)


def test_captured_blocker_complete_and_partial_blocked_output_rejected(valid):
    data=snapshot_data();data['ingredients'][0]['expiry_tracking']=True
    data['issues']=[issue('MISSING_EXPIRY','DATA_BLOCKER','inventory_lot',LOT)]
    blocked=run(data)
    modified=blocked.model_dump();modified.update(status='COMPLETE',decision_readiness='NOT_ASSESSED',issues=[])
    with pytest.raises(ValidationError):ServingSimulationResult.model_validate(modified)
    modified=blocked.model_dump();modified['products']=(valid.products[0].model_dump(),)
    with pytest.raises(ValidationError,match='partial'):ServingSimulationResult.model_validate(modified)


def test_tracked_arrival_blocker_and_numeric_reason_cannot_disappear():
    data=snapshot_data();data['ingredients'][0]['expiry_tracking']=True;data['lots']=[]
    result=run(data,[dict(lot_id=UUID(int=714),store_id=data['request']['store_id'],ingredient_id=INGREDIENT,
        unit='g',arrival_day=D+timedelta(days=1),quantity='1')])
    mutated=result.model_dump();mutated['issues']=[BOMIssue.model_validate(issue('OTHER','DATA_BLOCKER','product',PRODUCT)).model_dump()]
    with pytest.raises(ValidationError,match='arrival expiry'):ServingSimulationResult.model_validate(mutated)
    data=snapshot_data();data['lots'][0]['on_hand_quantity']='1e-2000'
    numeric=run(data)
    mutated=numeric.model_dump();mutated['issues']=[BOMIssue.model_validate(issue('OTHER','DATA_BLOCKER','product',PRODUCT)).model_dump()]
    with pytest.raises(ValidationError,match='numeric'):ServingSimulationResult.model_validate(mutated)


def test_copy_construct_json_roundtrip_revalidation_and_valid_order_independence(valid):
    assert ServingSimulationResult.model_validate_json(valid.model_dump_json())==valid
    data=valid.model_dump()
    for group in ('products','contributions','lots','ingredients'):data[group]=tuple(reversed(data[group]))
    assert ServingSimulationResult.model_validate(data).status=='COMPLETE'
    copied=valid.products[0].model_copy(update={'recipe_id':UUID(int=9999)})
    constructed=ProductServingDay.model_construct(**copied.model_dump())
    for row in (copied,constructed):
        with pytest.raises(ValidationError):ServingSimulationResult.model_validate(valid.model_copy(update={'products':(row,*valid.products[1:])}))
    data=valid.model_dump(mode='json');data['contributions'][0]['quantity']=_quantity(Fraction(4)).model_dump(mode='json')
    with pytest.raises(ValidationError):ServingSimulationResult.model_validate_json(json.dumps(data))


def test_validation_is_independent_of_simulator_and_does_not_prove_fairness(valid,monkeypatch):
    import app.application.use_cases.serving as usecase
    import app.domain.decision.serving as domain
    def forbidden(*args,**kwargs):raise AssertionError('Simulator/allocator must not be called')
    monkeypatch.setattr(usecase,'simulate_serving',forbidden)
    monkeypatch.setattr(domain,'simulate',forbidden);monkeypatch.setattr(domain,'allocate',forbidden)
    assert ServingSimulationResult.model_validate(valid).status=='COMPLETE'
    data=valid.model_dump()
    # Conserving but unequal fractions: A10/B10 instead of A15/B7.5. Validator
    # intentionally does not claim progressive fairness from conservation alone.
    for row in data['products']:
        if row['path_id']=='BASE' and row['day']==D+timedelta(days=1):
            a=row['product_id']==valid.input.prepared.products[0].product_id
            row.update(fulfilled=quantity(10),lost=quantity(10 if a else 0))
    for row in data['contributions']:
        if row['path_id']=='BASE' and row['day']==D+timedelta(days=1):
            a=row['product_id']==valid.input.prepared.products[0].product_id
            row['quantity']=quantity(2 if a else 4)
    assert ServingSimulationResult.model_validate(data).status=='COMPLETE'


@pytest.mark.parametrize('amount',['1e-999','1e300'])
def test_valid_extreme_outputs_and_exact_intermediates_keep_existing_limits(amount):
    data=snapshot_data();data['lots'][0]['on_hand_quantity']='1'
    for point in data['forecast']['predictions']:point.update(p25=amount,p50=amount,p75=amount)
    result=run(data)
    assert result.status=='COMPLETE'
    assert ServingSimulationResult.model_validate_json(result.model_dump_json())==result
    if amount=='1e-999':
        assert len(result.products[0].requested.denominator)==1000
        assert result.lots[0].ending.decimal_view==1 # exact remainder is not rounded state.
