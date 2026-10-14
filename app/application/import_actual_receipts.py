"""Frozen actual receipt plans and one adapter into the canonical N6 writer."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.application.contracts import import_mapping as dto,import_domains as domains,stock_writes as stock
from app.application.contracts.auth import AuthError
from app.application.receipt_identity import fingerprint,normalized
from app.application.use_cases.inventory_receipts import InventoryReceipts,ReservedReceiptIds


def canonical_receipt(value: domains.ActualReceiptSource,system: str) -> domains.ActualReceiptValue:
    return domains.ActualReceiptValue(receipt_identity=stock.ReceiptIdentity(source_system_key=system,
        source_record_id=value.source_record_id),**value.model_dump(exclude={'domain','source_record_id'}))


def receipt_facts(value: domains.ActualReceiptValue) -> stock.StockReceiptFacts:
    return stock.StockReceiptFacts.model_validate(value.model_dump(exclude={'domain'}))


def planned_effect(value: domains.ActualReceiptValue,snapshot: dict) -> dto.ReceiptEffect:
    identity=value.receipt_identity
    old=next((r for r in snapshot.get('inventory_receipt_records',())
        if (r['source_system_key'],r['source_record_key'])==(identity.source_system_key,identity.source_record_id)),None)
    if old is not None:
        retained=stock.StockReceiptResult.model_validate(old['record_json'])
        conflict=old['payload_digest']!=fingerprint(normalized(receipt_facts(value)))
        return dto.ReceiptEffect(action='BLOCKED' if conflict else 'REUSE_RECEIPT',source_identity=identity,
            receipt_id=old['id'],lot_id=old['lot_id'],movement_id=retained.movement.movement_id,
            quantity_delta=value.quantity,unit=value.unit,occurred_at=value.observed_at,
            recorded_at=retained.movement.recorded_at,conflict_code='RECEIPT_IDENTITY_CONFLICT' if conflict else None)
    return dto.ReceiptEffect(action='CREATE_RECEIPT',source_identity=identity,receipt_id=uuid4(),lot_id=uuid4(),
        movement_id=uuid4(),quantity_delta=value.quantity,unit=value.unit,occurred_at=value.observed_at,
        recorded_at=None,conflict_code=None)


def finish_receipts(rows,specs):
    """Coalesce proven identical receipts, preserve every physical source location."""
    groups={}
    for row in rows:
        value=row.after
        if isinstance(value,domains.ActualReceiptValue):
            identity=value.receipt_identity
            key=identity.source_system_key,identity.source_record_id
        elif isinstance(value,domains.OpeningValue):
            key=specs[str(row.source_location.sheet_id)].scope.source_system_key,value.source_record_id
        else: continue
        groups.setdefault(key,[]).append(row)
    removed=set();updated={}
    for group in groups.values():
        if not any(isinstance(r.after,domains.ActualReceiptValue) for r in group): continue
        digests=set()
        for row in group:
            if isinstance(row.after,domains.ActualReceiptValue):
                semantic=normalized(receipt_facts(row.after))
            else:
                from app.application.import_opening_stock import receipt_semantics
                semantic=receipt_semantics(row.after,specs[str(row.source_location.sheet_id)].scope.source_system_key)
            digests.add(fingerprint(semantic))
        if len(digests)>1:
            for row in group:
                code='RECEIPT_IDENTITY_CONFLICT'
                blockers=row.blockers+(dto.Notice(code=code,severity='ERROR',message=code,source_location=row.source_location),)
                effect=row.receipt_effect.model_copy(update={'action':'BLOCKED','conflict_code':code}) if row.receipt_effect else None
                updated[row.row_id]=row.model_copy(update=dict(classification='CONFLICT',proposed_action='BLOCKED',blockers=blockers,receipt_effect=effect))
        else:
            first=group[0]
            locations=tuple(location for row in group for location in (row.source_locations or (row.source_location,)))
            source_provenance=tuple(dto.NestedRecordProvenance(path=f'receipt_sources[{index}]',
                source_location=row.source_location,provenance={p.field:dto.ProvenanceValue.model_validate(
                    p.model_dump(exclude={'field'})) for p in row.provenance}) for index,row in enumerate(group))
            updated[first.row_id]=first.model_copy(update={'source_locations':locations,'nested_provenance':source_provenance})
            removed.update(r.row_id for r in group[1:])
    return [updated.get(r.row_id,r) for r in rows if r.row_id not in removed]


def write_actual_receipt(session: Session,store: UUID,row: dto.PreviewRow,*,actor: UUID,now: datetime,
                         store_timezone: str,currency: str) -> tuple[stock.StockReceiptResult,bool]:
    effect=row.receipt_effect
    if effect is None or not all((effect.receipt_id,effect.lot_id,effect.movement_id)):
        raise AuthError('SOURCE_INTEGRITY_ERROR',409)
    writer=InventoryReceipts(session,store);facts=receipt_facts(row.after)
    if (effect.action!=row.proposed_action or effect.source_identity!=facts.receipt_identity
        or Decimal(effect.quantity_delta)!=Decimal(facts.quantity) or effect.unit!=facts.unit
        or effect.occurred_at!=facts.observed_at):
        raise AuthError('SOURCE_INTEGRITY_ERROR',409)
    old=writer.replay(facts)
    if row.proposed_action=='REUSE_RECEIPT':
        if old is None or (old.receipt_id,old.lot.lot_id,old.movement.movement_id)!=(effect.receipt_id,effect.lot_id,effect.movement_id):
            raise AuthError('PREVIEW_STALE',409)
        return old,True
    if row.proposed_action!='CREATE_RECEIPT' or old is not None:
        raise AuthError('PREVIEW_STALE',409)
    return writer.create(facts,actor_id=actor,now=now,today=now.astimezone(ZoneInfo(store_timezone)).date(),
        store_timezone=store_timezone,currency=currency,inventory_version=lambda:'import-'+str(row.row_id),
        reserved=ReservedReceiptIds(effect.receipt_id,effect.lot_id,effect.movement_id),provenance=row.model_dump(mode='json')),False
