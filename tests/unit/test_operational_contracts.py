"""S1.7 operational shapes and exact inventory arithmetic, independent of DB."""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.contracts.store import CreateStoreInput
from app.application.contracts.catalog import CreateIngredientInput
from app.application.contracts.supplier import CreateSupplierTermInput
from app.application.contracts.recipe import CreateRecipeVersionInput
from app.application.contracts.inventory import ReceiveInventoryInput, AdjustInventoryInput
from app.domain.inventory.balance import corrected_balance, InvalidInventoryBalance

STORE, PRODUCT, INGREDIENT, SUPPLIER, LOT = [UUID(int=i) for i in range(100, 105)]
DAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def term_values():
    return dict(store_id=STORE, supplier_id=SUPPLIER, ingredient_id=INGREDIENT,
        unit='g', version=1, effective_from=DAY, pack_size_base_quantity='15000',
        minimum_order_packs=1, pack_cost='420000', lead_time_days=3)


def recipe_values():
    return dict(store_id=STORE, product_id=PRODUCT, version=1, effective_from=DAY,
        yield_quantity='10', process_loss_rate='0.05', lines=[dict(
            ingredient_id=INGREDIENT, quantity='800.125', unit='ml')])


def receipt_values():
    return dict(store_id=STORE, ingredient_id=INGREDIENT, quantity='50', unit='ml', occurred_at=NOW)


def adjustment_values():
    return dict(store_id=STORE, lot_id=LOT, quantity_delta='-5', unit='ml',
        movement_type='COUNT_CORRECTION', occurred_at=NOW, note='Confirmed physical count')


def test_store_frozen_defaults_and_current_shape_contract():
    data = CreateStoreInput(name='Cafe')
    assert data.timezone == 'Asia/Ho_Chi_Minh' and data.currency == 'VND'
    # Current contract is shape, not an unaccepted IANA/ISO catalog.
    assert CreateStoreInput(name='Cafe', timezone='Explicit zone', currency='USD').currency == 'USD'


@pytest.mark.parametrize('changes', [{'name': ' '}, {'timezone': ''}, {'timezone': 'x'*65}, {'currency': 'vnd'}, {'currency': 'VNDD'}, {'currency': 'VND\n'}])
def test_store_invalid_shape(changes):
    with pytest.raises(ValidationError):
        CreateStoreInput(**(dict(name='Cafe') | changes))


@pytest.mark.parametrize('changes', [{'name': ''}, {'base_unit': ' '}, {'sku': ''}, {'base_unit': 'x'*33}])
def test_ingredient_invalid_shape(changes):
    with pytest.raises(ValidationError):
        CreateIngredientInput(**(dict(store_id=STORE, name='Milk', base_unit='ml') | changes))


@pytest.mark.parametrize('changes', [
    {'version': 0}, {'version': True}, {'effective_from': None}, {'effective_to': date(2026, 9, 30)},
    {'pack_size_base_quantity': '0'}, {'minimum_order_packs': 0}, {'pack_cost': '-1'},
    {'pack_cost': 420000.1}, {'lead_time_days': -1}, {'shelf_life_days': -1},
])
def test_supplier_term_invalid_shape(changes):
    with pytest.raises(ValidationError):
        CreateSupplierTermInput(**(term_values() | changes))


def test_supplier_pack_cost_stays_exact_and_required_date():
    data = CreateSupplierTermInput(**term_values())
    assert data.pack_cost == Decimal('420000') and data.pack_size_base_quantity == Decimal('15000')
    values = term_values()
    del values['effective_from']
    with pytest.raises(ValidationError):
        CreateSupplierTermInput(**values)


@pytest.mark.parametrize('changes', [
    {'version': 0}, {'yield_quantity': '0'}, {'process_loss_rate': '-0.1'},
    {'process_loss_rate': '1'}, {'effective_to': date(2026, 9, 30)},
    {'lines': [dict(ingredient_id=INGREDIENT, quantity='0', unit='ml')]},
    {'lines': recipe_values()['lines'] * 2},
])
def test_recipe_invalid_shape(changes):
    with pytest.raises(ValidationError):
        CreateRecipeVersionInput(**(recipe_values() | changes))


@pytest.mark.parametrize('changes', [
    {'quantity': '0'}, {'quantity': '-1'}, {'quantity': 'NaN'}, {'quantity': 1.5},
    {'unit': ''}, {'unit_cost': '-1'}, {'occurred_at': datetime(2026, 10, 1)},
    {'reference_type': 'SUPPLIER'}, {'reference_id': 'receipt-1'},
    {'received_date': DAY, 'expiry_date': date(2026, 9, 30)},
])
def test_receipt_invalid_shape(changes):
    with pytest.raises(ValidationError):
        ReceiveInventoryInput(**(receipt_values() | changes))


def test_receipt_unknown_business_date_not_derived_from_event_time():
    instant = datetime(2026, 10, 2, 0, 30, tzinfo=timezone(timedelta(hours=7)))
    data = ReceiveInventoryInput(**(receipt_values() | {'occurred_at': instant, 'unit_cost': '30.125'}))
    assert data.received_date is None
    assert data.occurred_at == datetime(2026, 10, 1, 17, 30, tzinfo=timezone.utc)
    assert data.occurred_at.utcoffset() == timedelta(0) and data.unit_cost == Decimal('30.125')


@pytest.mark.parametrize('changes', [
    {'quantity_delta': '0'}, {'quantity_delta': 'Infinity'}, {'quantity_delta': -5.1},
    {'movement_type': 'RECEIPT'}, {'movement_type': 'EXPIRED'}, {'note': ''},
    {'note': None}, {'reference_type': 'COUNT'}, {'occurred_at': datetime(2026, 10, 1)},
])
def test_adjustment_invalid_shape(changes):
    with pytest.raises(ValidationError):
        AdjustInventoryInput(**(adjustment_values() | changes))


def test_balance_math_exact_despite_ambient_decimal_precision():
    with localcontext() as context:
        context.prec = 4
        assert corrected_balance(Decimal('123456789012345678901234567890.125'), Decimal('-0.005')) == Decimal('123456789012345678901234567890.120')
        assert corrected_balance(Decimal('1'), Decimal('0.00000000000000000000000000001')) == Decimal('1.00000000000000000000000000001')
        assert corrected_balance(Decimal('10'), Decimal('-10')) == Decimal('0')


def test_negative_result_rejected():
    with pytest.raises(InvalidInventoryBalance):
        corrected_balance(Decimal('10'), Decimal('-20'))


def test_inventory_domain_imports_without_framework_or_persistence():
    import subprocess
    import sys
    code = '''
import builtins
original = builtins.__import__
def checked(name, *args, **kwargs):
    assert not name.startswith(('fastapi', 'sqlalchemy', 'app.models', 'app.api', 'app.infrastructure'))
    return original(name, *args, **kwargs)
builtins.__import__ = checked
from decimal import Decimal
from app.domain.inventory.balance import corrected_balance
assert corrected_balance(Decimal('50'), Decimal('-5')) == Decimal('45')
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)
