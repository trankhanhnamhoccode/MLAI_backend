"""Atomic received lots and justified corrections, without FEFO or expiry automation."""
from sqlalchemy.orm import Session
from app.application._validation import load_ingredient, require_idle_session, require_supplier, require_unit
from app.application.contracts.inventory import AdjustInventoryInput, GetInventoryLotInput, InventoryLotResult, InventoryMovementResult, InventoryMutationResult, ReceiveInventoryInput
from app.application.errors import ApplicationError, ErrorCategory
from app.domain.inventory.balance import corrected_balance, InvalidInventoryBalance
from app.models import InventoryLot, InventoryMovement
from app.repositories.inventory import InventoryRepository


class InventoryUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.inventory = InventoryRepository(session)

    def receive(self, data: ReceiveInventoryInput) -> InventoryMutationResult:
        data = ReceiveInventoryInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            ingredient = load_ingredient(self.session, data.store_id, data.ingredient_id)
            require_unit(ingredient.base_unit, data.unit)
            if data.supplier_id is not None:
                require_supplier(self.session, data.store_id, data.supplier_id)
            if ingredient.expiry_tracking and data.expiry_date is None:
                raise ApplicationError(ErrorCategory.VALIDATION_ERROR, 'Tracked Ingredient receipt requires expiry_date')
            lot = InventoryLot(store_id=data.store_id, ingredient_id=data.ingredient_id,
                supplier_id=data.supplier_id, lot_code=data.lot_code, received_date=data.received_date,
                expiry_date=data.expiry_date, on_hand_quantity=data.quantity, unit=data.unit,
                unit_cost=data.unit_cost)
            self.inventory.add_lot(data.store_id, lot)
            self.session.flush()
            movement = InventoryMovement(store_id=data.store_id, lot_id=lot.id,
                ingredient_id=data.ingredient_id, movement_type='RECEIPT', quantity_delta=data.quantity,
                occurred_at=data.occurred_at, reference_type=data.reference_type,
                reference_id=data.reference_id, note=data.note)
            self.inventory.append_movement(data.store_id, movement)
            self.session.flush()
            result = InventoryMutationResult(lot=InventoryLotResult.model_validate(lot),
                movement=InventoryMovementResult.model_validate(movement))
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    def adjust(self, data: AdjustInventoryInput) -> InventoryMutationResult:
        data = AdjustInventoryInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            lot = self.inventory.get_lot_for_update(data.store_id, data.lot_id)
            if lot is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'InventoryLot not found in Store')
            require_unit(lot.unit, data.unit)
            # Plain Python domain function owns exact nonnegative balance arithmetic.
            lot.on_hand_quantity = corrected_balance(lot.on_hand_quantity, data.quantity_delta)
            movement = InventoryMovement(store_id=data.store_id, lot_id=lot.id,
                ingredient_id=lot.ingredient_id, movement_type=data.movement_type,
                quantity_delta=data.quantity_delta, occurred_at=data.occurred_at,
                reference_type=data.reference_type, reference_id=data.reference_id, note=data.note)
            self.inventory.append_movement(data.store_id, movement)
            self.session.flush()
            result = InventoryMutationResult(lot=InventoryLotResult.model_validate(lot),
                movement=InventoryMovementResult.model_validate(movement))
            self.session.commit()
            return result
        except InvalidInventoryBalance as error:
            self.session.rollback()
            raise ApplicationError(ErrorCategory.VALIDATION_ERROR, str(error)) from error
        except Exception:
            self.session.rollback()
            raise

    def get(self, data: GetInventoryLotInput) -> InventoryLotResult:
        data = GetInventoryLotInput.model_validate(data)
        with self.session.no_autoflush:
            lot = self.inventory.get_lot(data.store_id, data.lot_id)
            if lot is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'InventoryLot not found in Store')
            return InventoryLotResult.model_validate(lot)

    def movements(self, data: GetInventoryLotInput) -> tuple[InventoryMovementResult, ...]:
        data = GetInventoryLotInput.model_validate(data)
        with self.session.no_autoflush:
            self.get(data)
            return tuple(InventoryMovementResult.model_validate(row) for row in
                         self.inventory.list_movements(data.store_id, data.lot_id))
