"""Public quantity bounds prevent representational failures reaching PostgreSQL."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.application.contracts.stock_writes import StockReceiptRequest,ThresholdRequest

def test_stock_quantity_exact_boundary_and_oversized_fraction_rejection():
    quantity="0."+"0"*197+"1"
    body=dict(origin="OPENING_STOCK",receipt_identity=dict(source_system_key="source",source_record_id="receipt"),
        ingredient_id=uuid4(),supplier_id=None,lot_code=None,quantity=quantity,unit="l",received_date=None,expiry_date=None,
        unit_cost=None,currency="VND",observed_at="2026-10-11T02:00:00Z",reason="Current stock",expected_inventory_version="stock-example")
    assert StockReceiptRequest(**body).quantity==quantity
    assert ThresholdRequest(minimum_usable_quantity=quantity,unit="l",reason="Exact threshold").minimum_usable_quantity==quantity
    with pytest.raises(ValidationError):StockReceiptRequest(**{**body,"quantity":quantity+"1"})
    with pytest.raises(ValidationError):ThresholdRequest(minimum_usable_quantity=quantity+"1",unit="l",reason="Too long")
