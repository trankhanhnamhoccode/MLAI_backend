"""Supplier identities and dated canonical purchasing inputs; no supplier choice."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Supplier, SupplierTerm
from app.repositories._guards import require_new, require_store


class SupplierRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_supplier(self, store_id: UUID, supplier: Supplier) -> None:
        require_store(store_id, supplier.store_id)
        require_new(supplier)
        self._session.add(supplier)

    def get_supplier(self, store_id: UUID, supplier_id: UUID) -> Supplier | None:
        return self._session.scalar(select(Supplier).where(Supplier.store_id == store_id, Supplier.id == supplier_id))

    def list_suppliers(self, store_id: UUID) -> list[Supplier]:
        return list(self._session.scalars(select(Supplier).where(Supplier.store_id == store_id).order_by(Supplier.name, Supplier.id)))

    def add_supplier_term(self, store_id: UUID, term: SupplierTerm) -> None:
        require_store(store_id, term.store_id)
        require_new(term)
        self._session.add(term)

    def get_supplier_term(self, store_id: UUID, term_id: UUID) -> SupplierTerm | None:
        return self._session.scalar(select(SupplierTerm).where(SupplierTerm.store_id == store_id, SupplierTerm.id == term_id))

    def list_supplier_terms(self, store_id: UUID, ingredient_id: UUID) -> list[SupplierTerm]:
        return list(self._session.scalars(select(SupplierTerm).where(SupplierTerm.store_id == store_id, SupplierTerm.ingredient_id == ingredient_id).order_by(SupplierTerm.supplier_id, SupplierTerm.version, SupplierTerm.id)))

    def list_active_supplier_terms(self, store_id: UUID, ingredient_id: UUID, day: date) -> list[SupplierTerm]:
        return list(self._session.scalars(select(SupplierTerm).where(
            SupplierTerm.store_id == store_id, SupplierTerm.ingredient_id == ingredient_id,
            SupplierTerm.active.is_(True), SupplierTerm.effective_from <= day,
            SupplierTerm.effective_to.is_(None) | (SupplierTerm.effective_to >= day),
        ).order_by(SupplierTerm.supplier_id, SupplierTerm.version, SupplierTerm.id)))

    def get_effective_term(self, store_id: UUID, supplier_id: UUID, ingredient_id: UUID, day: date) -> SupplierTerm | None:
        return self._session.scalars(select(SupplierTerm).where(
            SupplierTerm.store_id == store_id, SupplierTerm.supplier_id == supplier_id,
            SupplierTerm.ingredient_id == ingredient_id, SupplierTerm.active.is_(True),
            SupplierTerm.effective_from <= day,
            SupplierTerm.effective_to.is_(None) | (SupplierTerm.effective_to >= day),
        )).one_or_none()
