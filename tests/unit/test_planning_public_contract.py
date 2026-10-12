"""PLAN5/9 boundary; no mocked engine or persistence evidence."""
from datetime import date,datetime,timezone
from uuid import UUID
import pytest
from pydantic import ValidationError
from app.application.contracts.planning_public import Accepted,PollMeta,RunView,ExactQuantity,Service


def test_receipt_has_single_run_identity_not_generic_job():
    accepted=Accepted(run_id=UUID(int=1),status='queued',accepted_at=datetime(2026,10,11,tzinfo=timezone.utc))
    assert set(accepted.model_dump())=={'run_id','status','accepted_at'}
    with pytest.raises(ValidationError):Accepted(**accepted.model_dump(),job_id=UUID(int=2))
    assert PollMeta(warnings=(),poll_after_ms=2000).poll_after_ms==2000


def test_exact_quantity_and_service_wire_keep_fraction_strings():
    quantity=ExactQuantity(numerator='1',denominator='3',decimal_view='0.33333333333333333333333333333333333333333333333333')
    assert quantity.model_dump()['numerator']=='1'
    with pytest.raises(ValidationError):ExactQuantity(numerator=1,denominator='3',decimal_view='0.3')
    assert Service(numerator='1',denominator='2',percent_view='50').percent_view=='50'


def test_training_provenance_reports_exact_intersection_without_changing_selection():
    from app.application.planning_public_projection import forecast_window_warnings
    start=date(2026,10,10);end=date(2026,10,16)
    assert forecast_window_warnings(date(2026,10,1),date(2026,10,9),start,end)==()
    overlap=forecast_window_warnings(date(2026,10,1),date(2026,10,11),start,end)
    assert overlap[0].code=='FORECAST_TRAINING_OVERLAP'
    assert overlap[0].details.affected_dates==(start,date(2026,10,11))
    assert forecast_window_warnings(None,None,start,end)[0].code=='FORECAST_TRAINING_BOUNDS_UNKNOWN'
