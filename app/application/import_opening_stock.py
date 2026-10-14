"""Excel opening-stock adapter into the same canonical receipt boundary as N6."""
from datetime import date,datetime
from uuid import UUID,uuid4
from sqlalchemy.orm import Session
from app.application.contracts import stock_writes as stock
from app.application.contracts.inventory import InventoryMutationResult,InventoryLotResult,InventoryMovementResult
from app.application.contracts.import_domains import OpeningSource,OpeningValue
from app.application.contracts.import_mapping import PreviewRow
from app.application.receipt_identity import normalized,fingerprint
from app.application.use_cases.inventory_receipts import InventoryReceipts,ReservedReceiptIds
from app.models import InventoryLot,InventoryMovement


def receipt_facts(value: OpeningSource | OpeningValue,system: str) -> stock.StockReceiptFacts:
    return stock.StockReceiptFacts.model_validate(dict(origin='OPENING_STOCK',
        receipt_identity=dict(source_system_key=system,source_record_id=value.source_record_id),
        **value.model_dump(exclude={'domain','lot_id','source_record_id'})))


def receipt_semantics(value: OpeningSource | OpeningValue,system: str) -> dict:
    return normalized(receipt_facts(value,system))


def write_opening(session: Session,store_id: UUID,row: PreviewRow,system: str,
                  actor_id: UUID,recorded_at: datetime,today: date) -> InventoryMutationResult:
    value=row.after
    result=InventoryReceipts(session,store_id).create(receipt_facts(value,system),
        actor_id=actor_id,now=recorded_at,today=today,store_timezone='UTC',currency=value.currency,
        inventory_version=lambda:'import-'+str(row.row_id),reserved=ReservedReceiptIds(uuid4(),value.lot_id),
        provenance=row.model_dump(mode='json'),opening_evidence_checked=True)
    return InventoryMutationResult(lot=InventoryLotResult.model_validate(session.get(InventoryLot,result.lot.lot_id)),
        movement=InventoryMovementResult.model_validate(session.get(InventoryMovement,result.movement.movement_id)))
