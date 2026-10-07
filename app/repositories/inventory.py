"""Received lot and audit persistence primitives; caller owns audited mutations."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryLot, InventoryMovement
from app.repositories._guards import require_new, require_store


class InventoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_lot(self, store_id: UUID, lot: InventoryLot) -> None:
        """Stage a new lot; future receipt use case must also append a movement."""
        require_store(store_id, lot.store_id)
        require_new(lot)
        self._session.add(lot)

    def get_lot(self, store_id: UUID, lot_id: UUID) -> InventoryLot | None:
        return self._session.scalar(select(InventoryLot).where(InventoryLot.store_id == store_id, InventoryLot.id == lot_id))

    def get_lot_for_update(self, store_id: UUID, lot_id: UUID) -> InventoryLot | None:
        """Lock and refresh the lot; lock lasts until the caller ends its transaction.

        Call before editing. populate_existing refreshes an already cached balance;
        this is not a balance update or an inventory mutation service.
        """
        return self._session.scalar(select(InventoryLot).where(
            InventoryLot.store_id == store_id, InventoryLot.id == lot_id,
        ).with_for_update().execution_options(populate_existing=True))

    def list_lots(self, store_id: UUID, ingredient_id: UUID) -> list[InventoryLot]:
        """All received lots, including expired/zero/unknown expiry; no FEFO filter."""
        return list(self._session.scalars(select(InventoryLot).where(InventoryLot.store_id == store_id, InventoryLot.ingredient_id == ingredient_id).order_by(InventoryLot.expiry_date.asc().nulls_last(), InventoryLot.id)))

    def append_movement(self, store_id: UUID, movement: InventoryMovement) -> None:
        require_store(store_id, movement.store_id)
        require_new(movement)
        self._session.add(movement)

    def get_movement(self, store_id: UUID, movement_id: UUID) -> InventoryMovement | None:
        return self._session.scalar(select(InventoryMovement).where(InventoryMovement.store_id == store_id, InventoryMovement.id == movement_id))

    def list_movements(self, store_id: UUID, lot_id: UUID) -> list[InventoryMovement]:
        return list(self._session.scalars(select(InventoryMovement).where(InventoryMovement.store_id == store_id, InventoryMovement.lot_id == lot_id).order_by(InventoryMovement.occurred_at, InventoryMovement.id)))
