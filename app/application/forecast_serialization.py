"""Versioned input identity, independent of run/model identity and Decimal context."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import json

from pydantic import ValidationError

from app.application.contracts.forecast_execution import PreparedForecastInput

SERIALIZATION_VERSION = 1
PREFIX = b'shelfcash.forecast-input.v1\n'


class RetainedInputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SerializedForecastInput:
    canonical_json: str
    digest: str
    serialization_version: int = SERIALIZATION_VERSION


def _decimal_string(value: Decimal) -> str:
    if value == 0:
        return '0'
    # Formatting does not round or consult caller precision. Strip fractional zeros only.
    rendered = format(value, 'f')
    return rendered.rstrip('0').rstrip('.') if '.' in rendered else rendered


def serialize_prepared(prepared: PreparedForecastInput) -> SerializedForecastInput:
    prepared = PreparedForecastInput.model_validate(prepared)
    payload = prepared.model_dump(mode='json')
    for row, observation in zip(payload['observations'], prepared.observations, strict=True):
        row['quantity'] = _decimal_string(observation.quantity)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    return SerializedForecastInput(encoded, hashlib.sha256(PREFIX + encoded.encode('utf-8')).hexdigest())


def restore_prepared(payload: object, serialization_version: int, digest: str) -> PreparedForecastInput:
    if type(serialization_version) is not int or serialization_version != SERIALIZATION_VERSION:
        raise RetainedInputError('UNSUPPORTED_SERIALIZATION_VERSION')
    try:
        prepared = PreparedForecastInput.model_validate(payload)
    except ValidationError as error:
        raise RetainedInputError('INVALID_RETAINED_INPUT') from error
    actual = serialize_prepared(prepared).digest
    if not isinstance(digest, str) or not digest.isascii() or not hmac.compare_digest(actual, digest):
        raise RetainedInputError('INPUT_DIGEST_MISMATCH')
    return prepared
