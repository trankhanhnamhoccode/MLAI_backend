"""Retained acceptance projections; no current budget or operational lookup."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from app.application.contracts.auth import AuthError
from app.application.contracts.history import CapturedBudget
from app.domain.inventory.read_rules import decimal_text


def local_created_range(start, end, zone):
    if start and end and start > end: raise AuthError('INVALID_FILTER',422)
    try:
        zone = ZoneInfo(zone)
        lower=datetime.combine(start,time.min,zone).astimezone(timezone.utc) if start else None
        upper=datetime.combine(end+timedelta(days=1),time.min,zone).astimezone(timezone.utc) if end else None
    except (OverflowError,ValueError): raise AuthError('INVALID_FILTER',422) from None
    return lower,upper


def captured_budget(record):
    budget = record.get('resolution',{}).get('budget')
    if not budget or budget.get('amount') is None or budget.get('currency') is None:
        return CapturedBudget(availability='unavailable',limit=None,currency=None)
    from decimal import Decimal
    return CapturedBudget(availability='available',limit=decimal_text(Decimal(budget['amount'])),currency=budget['currency'])
