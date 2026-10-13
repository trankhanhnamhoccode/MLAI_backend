"""A2 exact semantics on synthetic detached inputs; no DB/provider."""
from uuid import uuid4
import pytest
from tests.unit.test_import_preview import case
from app.application.contracts.import_domains import SOURCE_MODELS
from app.application.contracts.import_field_values import ProfileConstant


def usage(ingredient, **changes):
    return dict(source_record_key='usage-line-1', evidence_reference='Recorded POS consumption',
        ingredient_id=str(ingredient), usage_date='2026-10-09', observed_at=None,
        quantity='0', unit='g', **changes)


def purchase(ingredient):
    return dict(source_record_key='purchase-line-1', evidence_reference='Supplier historical invoice',
        ingredient_id=str(ingredient), supplier_id=None, quantity='1000', unit='g',
        order_date=None, received_date=None, report_date='2026-10-09',
        price='12.5', price_basis='PER_QUANTITY', price_quantity='100', price_unit='g', currency='VND')


def snap(ingredient):
    return dict(ingredients=[dict(id=str(ingredient), base_unit='g')], stores=[dict(currency='VND')])


@pytest.mark.parametrize('schema', ['calendar_events', 'promotion_observations', 'usage_history', 'purchase_history'])
def test_no_business_facts_are_profile_defaults(schema):
    field = {'calendar_events':'is_closed', 'promotion_observations':'promotion_applied',
             'usage_history':'quantity', 'purchase_history':'price'}[schema]
    with pytest.raises(ValueError, match='SHARED_FIELD_NOT_ALLOWED'):
        ProfileConstant(target_field=schema+'.'+field, declaration_id=uuid4(), value='0', evidence_reference='Test')


def test_usage_zero_explicit_null_missing_and_observation_day():
    ingredient=uuid4()
    row,=case('usage_history',[usage(ingredient)],snap(ingredient))
    assert row.proposed_action=='CREATE_HISTORY_RECORD' and row.after.quantity=='0'
    missing=usage(ingredient); del missing['quantity']
    # Model boundary rejects missing and explicitly unknown quantities independently.
    with pytest.raises(ValueError): SOURCE_MODELS['usage_history'].model_validate(missing)
    null=usage(ingredient); null['quantity']=None
    with pytest.raises(ValueError): SOURCE_MODELS['usage_history'].model_validate(null)
    wrong=usage(ingredient); wrong['observed_at']='2026-10-08T10:00:00Z'
    row,=case('usage_history',[wrong],snap(ingredient))
    assert any(b.code=='USAGE_DAY_TIMESTAMP_MISMATCH' for b in row.blockers)


def test_purchase_dates_and_declared_price_basis_never_default():
    ingredient=uuid4(); record=purchase(ingredient)
    row,=case('purchase_history',[record],snap(ingredient))
    assert not row.blockers and row.after.order_date is None and row.after.received_date is None
    assert row.after.price_quantity=='100' and row.after.price=='12.5'
    record['price_basis']='UNKNOWN'
    row,=case('purchase_history',[record],snap(ingredient))
    assert row.blockers
    record.update(price=None, price_quantity=None, price_unit=None)
    row,=case('purchase_history',[record],snap(ingredient))
    assert not row.blockers and row.after.price is None


def test_calendar_future_declaration_event_and_observed_promotion_are_separate():
    calendar=dict(source_record_key='holiday-1', evidence_reference='Owner announced closure',
        event_name='Tết', effective_from='2027-02-01', effective_to='2027-02-03',
        declared_at='2026-10-09T00:00:00Z', is_closed=False, is_holiday=None)
    row,=case('calendar_events',[calendar])
    assert not row.blockers and row.after.is_closed is False and row.after.is_holiday is None
    assert {w.code for w in row.warnings}=={'RECORDED_HISTORY_ONLY','CALENDAR_NOT_FORECAST_FEATURE'}
    calendar['declared_at']='2027-01-01T00:00:00Z'
    assert case('calendar_events',[calendar])[0].blockers
    product=uuid4()
    promo=dict(source_record_key='promo-1', evidence_reference='POS observed',product_id=str(product),
        sales_date='2026-10-11',promotion_name='Weekend special',promotion_applied=None)
    assert any(b.code=='FUTURE_HISTORY_NOT_OBSERVED' for b in case('promotion_observations',[promo],
        dict(products=[dict(id=str(product),selling_unit='cup')]))[0].blockers)


def test_duplicate_and_conflict_are_blockers_not_sales_contribution_sums():
    ingredient=uuid4(); record=usage(ingredient)
    rows=case('usage_history',[record,record],snap(ingredient))
    assert all(any(b.code=='DUPLICATE_HISTORY_IDENTITY' for b in r.blockers) for r in rows)
    changed=dict(record,quantity='12')
    rows=case('usage_history',[record,changed],snap(ingredient))
    assert all(any(b.code=='CONFLICTING_HISTORY_IDENTITY' for b in r.blockers) for r in rows)


def test_history_conversion_scales_quantity_and_price_denominator_exactly():
    from tests.unit.test_import_supplier_basis import conversion
    from decimal import localcontext
    ingredient=uuid4(); record=purchase(ingredient)
    record.update(quantity='1.25',unit='kg',price='0',price_quantity='0.5',price_unit='kg')
    with localcontext() as context:
        context.prec=2
        row,=case('purchase_history',[record],snap(ingredient),conversions=(conversion(),))
    assert not row.blockers
    assert (row.after.quantity,row.after.unit,row.after.price,row.after.price_quantity,row.after.price_unit)==('1250','g','0','500','g')
    assert next(p for p in row.provenance if p.field=='price_quantity').source_value=='0.5'
    record['price_unit']='l'
    blocked,=case('purchase_history',[record],snap(ingredient),conversions=(conversion(),conversion('l','g','1000')))
    assert any(b.code=='INCOMPATIBLE_HISTORY_UNIT_CONVERSION' for b in blocked.blockers)


def test_exact_quantity_spellings_do_not_create_spurious_history_correction():
    ingredient=uuid4(); record=usage(ingredient);record['quantity']='1.00'
    row,=case('usage_history',[record],snap(ingredient))
    assert row.after.quantity=='1'
    state=snap(ingredient);state['import_history_records']=[dict(id=str(uuid4()),domain='usage_history',
        source_system_key='POS-A',report_type='report-1',source_record_key=record['source_record_key'],
        version=1,payload=row.after.model_dump(mode='json'))]
    record['quantity']='1.0'
    repeat,=case('usage_history',[record],state)
    assert repeat.proposed_action=='NO_OP' and repeat.expected_version=='1'


def test_history_field_labels_do_not_alias_stock_count_or_retail_price():
    from app.application.import_descriptors import column_candidates, options, SCHEMAS
    assert column_candidates('Giá bán','purchase_history')==()
    assert column_candidates('Thời điểm kiểm kê','usage_history')==()
    assert all('?' not in SCHEMAS[d][0] for d in ('calendar_events','promotion_observations','usage_history','purchase_history'))
