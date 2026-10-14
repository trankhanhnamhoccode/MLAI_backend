"""N6 canonical receipt/lot/movement/audit boundary, reused inside atomic Import."""
from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal
from typing import Callable
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.application.contracts.auth import AuthError
from app.application.contracts.inventory import ReceiveInventoryInput
from app.application.contracts import stock_writes as dto
from app.application.contracts.public_reads import MovementRead,MovementReference
from app.application.receipt_identity import fingerprint,normalized
from app.application.stock_observation import validate_opening_observation
from app.application.use_cases.inventory import InventoryUseCases
from app.application.use_cases.public_reads import PublicReads,issue
from app.domain.inventory.read_rules import decimal_text
from app.models import Ingredient,InventoryLot,InventoryMovement
from app.models.operational_import import InventoryAudit,InventoryReceiptRecord
from app.repositories.inventory_receipts import InventoryReceiptRepository
from app.repositories.public_reads import PublicReadRepository


@dataclass(frozen=True)
class ReservedReceiptIds:
    receipt_id: UUID
    lot_id: UUID
    movement_id: UUID | None = None


class InventoryReceipts:
    def __init__(self,session: Session,store: UUID):
        self.session,self.store=session,store

    def replay(self,facts: dto.StockReceiptFacts) -> dto.StockReceiptResult | None:
        old=InventoryReceiptRepository(self.session).receipt(self.store,
            facts.receipt_identity.source_system_key,facts.receipt_identity.source_record_id)
        if old is None: return None
        if old.payload_digest!=fingerprint(normalized(facts)):
            raise AuthError('RECEIPT_IDENTITY_CONFLICT',409)
        return dto.StockReceiptResult.model_validate(old.record_json)

    def create(self,facts: dto.StockReceiptFacts,*,actor_id: UUID,now: datetime,today: date,
               store_timezone: str,currency: str,inventory_version: Callable[[],str],
               reserved: ReservedReceiptIds | None=None,provenance: dict | None=None,
               opening_evidence_checked: bool=False) -> dto.StockReceiptResult:
        """No commit: caller has current auth, inventory/read-set and identity fences."""
        facts=dto.StockReceiptFacts.model_validate(facts)
        s=self.session;repo=PublicReadRepository(s)
        ingredient=repo.ingredient(self.store,facts.ingredient_id)
        if ingredient is None: raise AuthError('RESOURCE_NOT_FOUND',404)
        if facts.unit!=ingredient['base_unit']: raise AuthError('INVALID_UNIT',422)
        if ingredient['expiry_tracking'] and facts.expiry_date is None: raise AuthError('REQUIRED_EXPIRY_MISSING',422)
        if facts.currency!=currency: raise AuthError('VALIDATION_ERROR',422)
        if facts.observed_at>now: raise AuthError('STALE_STOCK_OBSERVATION',409)
        if facts.received_date is not None and facts.received_date>today: raise AuthError('VALIDATION_ERROR',422)
        if facts.origin=='OPENING_STOCK' and not opening_evidence_checked:
            validate_opening_observation(s,self.store,facts.ingredient_id,facts.observed_at,facts.lot_code)
        ids=reserved or ReservedReceiptIds(uuid4(),uuid4())
        aid=uuid4();semantic=normalized(facts)
        mutation=InventoryUseCases(s).receive_in_transaction(ReceiveInventoryInput(
            store_id=self.store,ingredient_id=facts.ingredient_id,supplier_id=facts.supplier_id,
            lot_code=facts.lot_code,quantity=Decimal(facts.quantity),unit=facts.unit,
            received_date=facts.received_date,expiry_date=facts.expiry_date,
            unit_cost=Decimal(facts.unit_cost) if facts.unit_cost is not None else None,
            occurred_at=facts.observed_at,reference_type=facts.origin,reference_id=str(ids.receipt_id),note=facts.reason),
            opening=facts.origin=='OPENING_STOCK',reserved_id=ids.lot_id,reserved_movement_id=ids.movement_id)
        movement=s.get(InventoryMovement,mutation.movement.id)
        audit=dict(origin=facts.origin,receipt_id=str(ids.receipt_id),request=semantic)
        if provenance is not None: audit['import_row']=provenance
        s.add(InventoryAudit(id=aid,store_id=self.store,actor_id=actor_id,movement_id=movement.id,
            occurred_at=now,record_json=audit));s.flush()
        version=inventory_version()
        _,_,first=repo.lots(self.store,ingredient,today,None,100,True)
        lot=s.get(InventoryLot,mutation.lot.id)
        values={c.name:getattr(lot,c.name) for c in InventoryLot.__table__.columns}
        values['origin']=facts.origin
        projected=PublicReads._lot(values,ingredient,today,first,currency,True,version)
        warnings=tuple(issue(code,'inventory_lot',lot.id,field,code)
            for condition,code,field in (
                (facts.received_date is None,'MISSING_RECEIVED_DATE','received_date'),
                (facts.expiry_date is not None and facts.expiry_date<today,'LOT_EXPIRED','expiry_date'),
                (facts.origin=='ACTUAL_RECEIPT' and (facts.observed_at.astimezone(ZoneInfo(store_timezone)).date()<today
                    or facts.received_date is not None and facts.received_date<today),'LATE_RECEIPT_RECORDED','observed_at')) if condition)
        result=dto.StockReceiptResult(receipt_id=ids.receipt_id,origin=facts.origin,lot=projected,
            movement=MovementRead(movement_id=movement.id,lot_id=lot.id,batch_code=facts.lot_code,
                kind=movement.movement_type.lower(),quantity_delta=decimal_text(movement.quantity_delta),unit=facts.unit,
                occurred_at=movement.occurred_at,recorded_at=movement.created_at,actor_user_id=actor_id,
                reason=facts.reason,reference=MovementReference(type=facts.origin,id=str(ids.receipt_id)),origin=facts.origin),
            inventory_version=version,audit_reference=aid,warnings=warnings)
        s.add(InventoryReceiptRecord(id=ids.receipt_id,store_id=self.store,
            source_system_key=facts.receipt_identity.source_system_key,source_record_key=facts.receipt_identity.source_record_id,
            ingredient_id=facts.ingredient_id,lot_id=lot.id,origin=facts.origin,payload_digest=fingerprint(semantic),
            record_json=result.model_dump(mode='json')));s.flush()
        return result
