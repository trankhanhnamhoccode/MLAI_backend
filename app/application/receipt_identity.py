"""Canonical stock request spelling shared by N6 and frozen import plans."""
from datetime import timezone
from decimal import Decimal
import hashlib,json
from app.domain.inventory.read_rules import decimal_text


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def normalized(body):
    values=body.model_dump(mode='json')
    for key in ('quantity','unit_cost','minimum_usable_quantity'):
        if values.get(key) is not None:
            value=decimal_text(Decimal(values[key]))
            values[key]=value.rstrip('0').rstrip('.') if '.' in value else value
    if 'observed_at' in values:
        values['observed_at']=body.observed_at.astimezone(timezone.utc).isoformat()
    return values
