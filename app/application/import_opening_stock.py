"""Excel opening-stock planning and the existing transaction-owned inventory writer."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.application.contracts import stock_writes as stock
from app.application.contracts.inventory import ReceiveInventoryInput, InventoryMutationResult
from app.application.contracts.import_domains import OpeningSource, OpeningValue
from app.application.contracts.import_mapping import PreviewRow
from app.application.contracts.public_reads import MovementRead, MovementReference
from app.application.use_cases.inventory import InventoryUseCases
from app.application.use_cases.public_reads import PublicReads, issue
from app.application.use_cases.stock_writes import normalized, fingerprint
from app.models import Ingredient, InventoryLot, InventoryMovement
from app.models.operational_import import InventoryReceiptRecord, InventoryAudit
from app.repositories.public_reads import PublicReadRepository


def receipt_semantics(value: OpeningSource | OpeningValue, system: str) -> dict:
    body = stock.StockReceiptRequest.model_validate(dict(
        origin="OPENING_STOCK", receipt_identity=dict(source_system_key=system,
            source_record_id=value.source_record_id),
        **value.model_dump(exclude={"domain", "lot_id", "source_record_id"}),
        expected_inventory_version="import-frozen-read-set"))
    result = normalized(body)
    result.pop("expected_inventory_version")
    return result


def write_opening(session: Session, store_id: UUID, row: PreviewRow, system: str,
                  actor_id: UUID, recorded_at: datetime, today: date) -> InventoryMutationResult:
    value = row.after
    semantic = receipt_semantics(value, system)
    rid, aid = uuid4(), uuid4()
    result = InventoryUseCases(session).receive_in_transaction(ReceiveInventoryInput(
        store_id=store_id, ingredient_id=value.ingredient_id, supplier_id=value.supplier_id,
        lot_code=value.lot_code, quantity=Decimal(value.quantity), unit=value.unit,
        received_date=value.received_date, expiry_date=value.expiry_date,
        unit_cost=Decimal(value.unit_cost) if value.unit_cost is not None else None,
        occurred_at=value.observed_at, reference_type="OPENING_STOCK", reference_id=str(rid),
        note=value.reason), opening=True, reserved_id=value.lot_id)
    movement = session.get(InventoryMovement, result.movement.id)
    session.add(InventoryAudit(id=aid, store_id=store_id, actor_id=actor_id,
        movement_id=movement.id, occurred_at=recorded_at,
        record_json=dict(origin="OPENING_STOCK", receipt_id=str(rid), request=semantic,
            import_row=row.model_dump(mode="json"))))
    session.flush()
    ingredient = session.get(Ingredient, value.ingredient_id)
    lot = session.get(InventoryLot, value.lot_id)
    inventory_version = "import-" + str(row.row_id)
    repo = PublicReadRepository(session)
    ingredient_values = {c.name: getattr(ingredient, c.name) for c in Ingredient.__table__.columns}
    _, _, first = repo.lots(store_id, ingredient_values, today, None, 100, True)
    lot_values = {c.name: getattr(lot, c.name) for c in InventoryLot.__table__.columns}
    lot_values["origin"] = "OPENING_STOCK"
    # _lot is a pure projection; the N6 retained receipt has the same public shape.
    projected = PublicReads._lot(lot_values, ingredient_values, today, first,
        value.currency, True, inventory_version)
    warnings = tuple(issue(code, "inventory_lot", lot.id, field, code)
        for condition, code, field in (
            (value.received_date is None, "MISSING_RECEIVED_DATE", "received_date"),
            (value.expiry_date is not None and value.expiry_date < today, "LOT_EXPIRED", "expiry_date")) if condition)
    receipt = stock.StockReceiptResult(receipt_id=rid, origin="OPENING_STOCK", lot=projected,
        movement=MovementRead(movement_id=movement.id, lot_id=lot.id, batch_code=value.lot_code,
            kind="count_correction", quantity_delta=value.quantity, unit=value.unit,
            occurred_at=value.observed_at.astimezone(timezone.utc), recorded_at=movement.created_at,
            actor_user_id=actor_id, reason=value.reason, reference=MovementReference(
                type="OPENING_STOCK", id=str(rid)), origin="OPENING_STOCK"),
        inventory_version=inventory_version, audit_reference=aid, warnings=warnings)
    session.add(InventoryReceiptRecord(id=rid, store_id=store_id, source_system_key=system,
        source_record_key=value.source_record_id, ingredient_id=value.ingredient_id,
        lot_id=lot.id, origin="OPENING_STOCK", payload_digest=fingerprint(semantic),
        record_json=receipt.model_dump(mode="json")))
    session.flush()
    return result
