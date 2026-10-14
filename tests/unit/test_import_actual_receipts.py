"""Actual receipts retain facts and plan one positive effect per proven identity."""
from datetime import timedelta
from uuid import uuid4
import pytest
from tests.unit.test_import_preview import case,NOW


def receipt(ingredient, **changes):
    record=dict(source_record_id='DELIVERY-1',ingredient_id=str(ingredient),supplier_id=None,
        lot_code='DELIVERY-LOT',quantity='1.25',unit='l',received_date=None,expiry_date=None,
        unit_cost=None,currency='VND',observed_at=(NOW-timedelta(days=1)).isoformat(),
        reason='Explicit synthetic delivery')
    return {**record,**changes}


def rows(records,ingredient,**kwargs):
    snapshot=dict(ingredients=[dict(id=str(ingredient),base_unit='l',expiry_tracking=False)])
    snapshot.update(kwargs.pop('snapshot',{}))
    return case('inventory_receipts',records,snapshot,context_fields={'inventory_semantics':'actual_receipt'},**kwargs)


def test_receipt_new_effect_keeps_unknown_facts_and_late_evidence():
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    assert not row.blockers
    assert row.after.origin=='ACTUAL_RECEIPT'
    assert row.after.receipt_identity.source_system_key=='POS-A'
    assert row.after.received_date is row.after.supplier_id is row.after.unit_cost is None
    effect=row.receipt_effect
    assert effect.action=='CREATE_RECEIPT' and effect.quantity_delta=='1.25'
    assert effect.receipt_id and effect.lot_id and effect.movement_id
    assert effect.recorded_at is None and effect.occurred_at==NOW-timedelta(days=1)
    assert 'LATE_RECEIPT_RECORDED' in {n.code for n in row.warnings}


def test_duplicate_identity_coalesces_locations_and_conflict_is_order_independent():
    ingredient=uuid4();record=receipt(ingredient)
    identical=rows([record,record],ingredient)
    assert len(identical)==1 and len(identical[0].source_locations)==2
    assert len(identical[0].nested_provenance)==2
    for records in ([record,{**record,'quantity':'2'}],[{**record,'quantity':'2'},record]):
        conflicting=rows(records,ingredient)
        assert all('RECEIPT_IDENTITY_CONFLICT' in {n.code for n in row.blockers} for row in conflicting)


@pytest.mark.parametrize('changes,code',[
    ({'quantity':'0'},'INVALID_SOURCE_VALUE'),
    ({'quantity':None},'MISSING_REQUIRED_VALUE'),
    ({'observed_at':'2026-10-09'},'INVALID_SOURCE_VALUE'),
    ({'observed_at':'45000'},'INVALID_SOURCE_VALUE'),
    ({'observed_at':'2026-10-09T02:00:00'},'INVALID_SOURCE_VALUE'),
    ({'observed_at':'2099-01-01T00:00:00Z'},'STALE_STOCK_OBSERVATION'),
    ({'unit':'kg'},'INVALID_UNIT'),
])
def test_invalid_receipt_cannot_plan_inventory(changes,code):
    ingredient=uuid4();row=rows([{**receipt(ingredient),**changes}],ingredient)[0]
    assert code in {n.code for n in row.blockers}


@pytest.mark.parametrize('cost,expected', [('0','0'), ('2','0.002')])
def test_physical_conversion_keeps_raw_quantity_and_zero_cost_without_density(cost,expected):
    from app.application.contracts import import_mapping as dto
    ingredient=uuid4();record=receipt(ingredient,unit_cost=cost,unit='kg')
    conversion=dto.Conversion(kind='declared_conversion',from_unit='kg',to_unit='g',
        factor=dict(numerator='1000',denominator='1'),evidence_reference='Explicit mass factor')
    row=rows([record],ingredient,snapshot=dict(ingredients=[dict(id=str(ingredient),base_unit='g',expiry_tracking=False)]),
        conversions=(conversion,))[0]
    assert not row.blockers and row.after.quantity=='1250' and row.after.unit_cost==expected
    assert row.after.unit=='g'
    assert next(p for p in row.provenance if p.field=='quantity').source_value=='1.25'
    incompatible=conversion.model_copy(update={'to_unit':'l'})
    blocked=rows([record],ingredient,conversions=(incompatible,))[0]
    assert 'INCOMPATIBLE_STOCK_UNIT_CONVERSION' in {n.code for n in blocked.blockers}


def test_expiry_tracking_and_nullable_cost_supplier_remain_distinct_from_zero():
    ingredient=uuid4();record=receipt(ingredient,unit_cost='0')
    blocked=rows([record],ingredient,snapshot=dict(ingredients=[dict(id=str(ingredient),base_unit='l',expiry_tracking=True)]))[0]
    assert 'REQUIRED_EXPIRY_MISSING' in {n.code for n in blocked.blockers}
    valid=rows([{**record,'expiry_date':'2026-10-20'}],ingredient,
        snapshot=dict(ingredients=[dict(id=str(ingredient),base_unit='l',expiry_tracking=True)]))[0]
    assert not valid.blockers and valid.after.unit_cost=='0' and valid.after.supplier_id is None


def test_receipt_writer_rejects_effect_facts_drift_before_touching_session():
    from app.application.import_actual_receipts import write_actual_receipt
    from app.application.contracts.auth import AuthError
    ingredient=uuid4();row=rows([receipt(ingredient)],ingredient)[0]
    corrupted=row.model_copy(update={'receipt_effect':row.receipt_effect.model_copy(update={'quantity_delta':'9'})})
    with pytest.raises(AuthError) as failure:
        write_actual_receipt(None,uuid4(),corrupted,actor=uuid4(),now=NOW,store_timezone='UTC',currency='VND')
    assert failure.value.code=='SOURCE_INTEGRITY_ERROR'


def test_actual_and_opening_cannot_share_one_source_receipt_identity():
    from types import SimpleNamespace
    from app.application.import_actual_receipts import finish_receipts
    from app.application.contracts.import_domains import OpeningValue
    ingredient = uuid4()
    actual = rows([receipt(ingredient)], ingredient)[0]
    opening = actual.model_copy(update={
        'row_id': uuid4(),
        'after': OpeningValue(**receipt(ingredient), lot_id=uuid4()),
        'receipt_effect': None,
    })
    specs = {str(opening.source_location.sheet_id): SimpleNamespace(
        scope=SimpleNamespace(source_system_key='POS-A'))}
    for ordered in ([opening, actual], [actual, opening]):
        result = finish_receipts(ordered, specs)
        assert len(result) == 2
        assert all('RECEIPT_IDENTITY_CONFLICT' in {n.code for n in row.blockers} for row in result)
