"""Shared Store/source receipt identity lookup; caller owns canonical fences."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.operational_import import InventoryReceiptRecord


class InventoryReceiptRepository:
    def __init__(self,session: Session):
        self.session=session

    def receipt(self,store: UUID,system: str,record: str) -> InventoryReceiptRecord | None:
        return self.session.scalar(select(InventoryReceiptRecord).where(InventoryReceiptRecord.store_id==store,
            InventoryReceiptRecord.source_system_key==system,InventoryReceiptRecord.source_record_key==record))
