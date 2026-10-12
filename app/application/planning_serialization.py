"""planning_storage/1 exact, deterministic typed JSON (not source authenticity)."""
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import math
from uuid import UUID
from pydantic import BaseModel


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError('Nonfinite retained Decimal')
    if value == 0:
        return '0'
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop(); exponent += 1
    # Coefficient/exponent avoids expanding extremely large/small quantities.
    return ('-' if sign else '') + ''.join(map(str, digits)) + 'e' + str(exponent)


def exact_json(value):
    if isinstance(value, BaseModel):
        return exact_json(value.model_dump(mode='python', round_trip=True))
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, (date, datetime, UUID)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, dict):
        return {k: exact_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [exact_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite diagnostic float')
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError('Unsupported retained type')


def canonical_bytes(value) -> bytes:
    return json.dumps(exact_json(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(role: str, value) -> str:
    return sha256(('shelfcash.planning.' + role + '/1\n').encode() + canonical_bytes(value)).hexdigest()


def request_identity(request):
    """Preserve list order and presence; only typed numeric wire fields normalize."""
    from app.application.contracts.planning_setup import PlanningRequest
    value = PlanningRequest.model_validate(request).model_dump(mode='json', round_trip=True)
    def normalize(node):
        if isinstance(node, dict):
            return {k: decimal_text(Decimal(v)) if k in {'budget_limit', 'min_fill_rate_percent'}
                    and v is not None else normalize(v) for k, v in node.items()}
        if isinstance(node, list):
            return [normalize(v) for v in node]
        return node
    return normalize(value)


def request_digest(request) -> str:
    return digest('idempotency_request', request_identity(request))
