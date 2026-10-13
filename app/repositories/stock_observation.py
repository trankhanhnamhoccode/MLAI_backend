"""Scoped persisted evidence used by the opening-stock application validator."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import InventoryLot, InventoryMovement
from app.models.import_staging import ImportAudit


@dataclass(frozen=True)
class StockObservationEvidence:
    lots: tuple[InventoryLot, ...]
    movements: tuple[InventoryMovement, ...]
    counts: tuple[tuple[datetime, tuple[str, ...]], ...]


def observation_evidence(session: Session, store: UUID, ingredient: UUID, observed_at: datetime) -> StockObservationEvidence:
    lots = tuple(session.scalars(select(InventoryLot).where(
        InventoryLot.store_id == store, InventoryLot.ingredient_id == ingredient)))
    movements = tuple(session.scalars(select(InventoryMovement).where(
        InventoryMovement.store_id == store, InventoryMovement.ingredient_id == ingredient)))
    audits = session.scalars(select(ImportAudit).where(ImportAudit.store_id == store,
        ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED", ImportAudit.occurred_at >= observed_at))
    counts = tuple((a.occurred_at, tuple(r["canonical_id"] for r in
        a.record_json.get("completion", {}).get("canonical_references", ())
        if r.get("canonical_domain") == "inventory_count")) for a in audits)
    return StockObservationEvidence(lots,movements,counts)
