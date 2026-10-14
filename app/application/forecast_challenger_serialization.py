"""Separate versioned challenger identities; historical forecast bytes untouched."""
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from uuid import UUID

from pydantic import BaseModel


def canonical_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode='python'))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('Nonfinite Decimal')
        if value == 0:
            return '0'
        text = format(value, 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (UUID, date)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): canonical_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical_value(v) for v in value]
    return value


def canonical_bytes(value: object) -> bytes:
    # UUID/date/Enum are otherwise canonical str values, never floats for quantities.
    return json.dumps(canonical_value(value), default=str, sort_keys=True,
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def challenger_digest(role: str, value: object) -> str:
    return hashlib.sha256(f'shelfcash.forecast-challenger.{role}.v1\n'.encode()
                          + canonical_bytes(value)).hexdigest()
