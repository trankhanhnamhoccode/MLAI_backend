"""Write-ahead budget fence for the one authorized L3.1/L3.2 batch."""
import json
from decimal import Decimal
from pathlib import Path

MAX_ATTEMPTS=30
MAX_USD=Decimal('1.00')
BOUND=Decimal('0.0140592')


def reservations(base: Path):
    paths=sorted(p for folder in ('conversational-l31-live','conversational-l32-live') for p in (base/folder).glob('attempt-*.json'))
    rows=[json.loads(p.read_text(encoding='utf8')) for p in paths]
    amounts=[Decimal(r['reserved_usd']) for r in rows]
    if any(not a.is_finite() or a<=0 for a in amounts):raise ValueError('Invalid historical reservation')
    return rows,sum(amounts,Decimal(0))


def reserve(base: Path, record):
    root=base/'conversational-l32-live';root.mkdir(parents=True,exist_ok=True)
    lock=root/'reservation.lock'
    # Crash leaves the lock fail-closed. Reconciliation requires explicit review;
    # no automatic lock removal, slot refund, retry or timeout inference.
    with lock.open('x',encoding='utf8') as handle:handle.write('Reservation in progress; do not blindly remove.\n')
    try:
        rows,total=reservations(base)
        if len(rows)>=MAX_ATTEMPTS or total+BOUND>MAX_USD:raise ValueError('Shared L3.1/L3.2 cap exhausted')
        n=len(rows)+1
        path=root/f'attempt-{n}.json'
        with path.open('x',encoding='utf8') as out:
            json.dump(dict(record,attempt=n,reserved_usd=str(BOUND),budget_group='L31-L32-shared-30-usd-1.00'),out,ensure_ascii=False,indent=2)
            out.flush()
            import os
            os.fsync(out.fileno())
        return n
    finally:lock.unlink()
