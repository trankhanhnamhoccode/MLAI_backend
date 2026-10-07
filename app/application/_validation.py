"""Small explicit preconditions; no transaction helper or framework."""
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session
from app.application.errors import ApplicationError, ErrorCategory
from app.repositories.catalog import CatalogRepository
from app.repositories.identity import StoreRepository
from app.repositories.supplier import SupplierRepository
from app.models import Ingredient


def require_idle_session(session: Session) -> None:
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ApplicationError(ErrorCategory.CONFLICT, 'Write use case requires an idle clean Session')


def require_store(session: Session, store_id: UUID) -> None:
    if StoreRepository(session).get_store_by_id(store_id) is None:
        raise ApplicationError(ErrorCategory.NOT_FOUND, 'Store not found')


def require_product(session: Session, store_id: UUID, product_id: UUID) -> None:
    if CatalogRepository(session).get_product(store_id, product_id) is None:
        raise ApplicationError(ErrorCategory.NOT_FOUND, 'Product not found in Store')


def require_terminal_time(started_at: datetime, completed_at: datetime) -> None:
    if completed_at < started_at:
        raise ApplicationError(ErrorCategory.VALIDATION_ERROR, 'Terminal time precedes run start')


def load_ingredient(session: Session, store_id: UUID, ingredient_id: UUID) -> Ingredient:
    row = CatalogRepository(session).get_ingredient(store_id, ingredient_id)
    if row is None:
        raise ApplicationError(ErrorCategory.NOT_FOUND, 'Ingredient not found in Store')
    return row


def require_supplier(session: Session, store_id: UUID, supplier_id: UUID) -> None:
    if SupplierRepository(session).get_supplier(store_id, supplier_id) is None:
        raise ApplicationError(ErrorCategory.NOT_FOUND, 'Supplier not found in Store')


def require_unit(expected: str, supplied: str) -> None:
    if expected != supplied:
        raise ApplicationError(ErrorCategory.VALIDATION_ERROR, 'Unit must exactly match canonical base unit')
