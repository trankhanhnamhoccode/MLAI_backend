"""Short-transaction current snapshots with session/authority/filter-bound cursors."""
import base64
from datetime import datetime
import hmac
import json
from uuid import UUID
from app.application.contracts.auth import AuthError
from app.application.use_cases.auth import version
from app.infrastructure.auth_crypto import digest


def mutation_headers(key, match=None, *, cas=False):
    if cas and match is None:
        raise AuthError("PRECONDITION_REQUIRED", 428)
    try:
        if str(UUID(key)) != key:
            raise ValueError()
        if cas and (not 3 <= len(match.encode()) <= 258 or match[0] != '"' or match[-1] != '"' or '"' in match[1:-1]):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise AuthError("INVALID_REQUEST", 400) from None
    return digest(key), match[1:-1] if cas else None


def page(auth, token, domain, items, authority, filters, limit, cursor, *, fingerprint_facts=()):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AuthError("INVALID_FILTER", 422)
    fingerprint = version([[item.model_dump(mode="json") for item in items], fingerprint_facts])
    start, end, meta = window(auth, token, domain, len(items), fingerprint, authority, filters, limit, cursor)
    return tuple(items[start:end]), meta


def window(auth, token, domain, total, fingerprint, authority, filters, limit, cursor):
    """Validate a snapshot and bound a page without constructing every evidence DTO."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AuthError("INVALID_FILTER", 422)
    offset, observed = 0, auth.clock()
    if cursor:
        try:
            encoded, signature = cursor.split(".")
            if len(cursor.encode()) > 4096 or not hmac.compare_digest(signature, auth.cursor_signer.sign(token, domain, encoded)):
                raise ValueError()
            value = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            # Different authorization is a changed snapshot, not a filter error.
            if value["filters"] != filters or value["limit"] != limit:
                raise ValueError()
            if value["authority"] != authority or value["fingerprint"] != fingerprint:
                raise AuthError("SNAPSHOT_NOT_AVAILABLE", 409)
            offset, observed = value["offset"], datetime.fromisoformat(value["observed"])
            if type(offset) is not int or not 0 < offset < total or observed.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise AuthError("INVALID_CURSOR", 422) from None
    end = offset + limit
    next_cursor = None
    if end < total:
        payload = dict(authority=authority, filters=filters, limit=limit, fingerprint=fingerprint, offset=end, observed=observed.isoformat())
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        next_cursor = encoded + "." + auth.cursor_signer.sign(token, domain, encoded)
    return offset, min(end, total), dict(snapshot_id=fingerprint, observed_at=observed,
        pagination=dict(limit=limit, next_cursor=next_cursor, total_count=total))
