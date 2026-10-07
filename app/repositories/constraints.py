"""Controlled constraint storage/date selection; no feasibility computation."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BusinessConstraint
from app.repositories._guards import require_new, require_store


class ConstraintsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_constraint(self, store_id: UUID, constraint: BusinessConstraint) -> None:
        require_store(store_id, constraint.store_id)
        require_new(constraint)
        self._session.add(constraint)

    def get_constraint(self, store_id: UUID, constraint_id: UUID) -> BusinessConstraint | None:
        return self._session.scalar(select(BusinessConstraint).where(BusinessConstraint.store_id == store_id, BusinessConstraint.id == constraint_id))

    def list_constraints(self, store_id: UUID) -> list[BusinessConstraint]:
        return list(self._session.scalars(select(BusinessConstraint).where(BusinessConstraint.store_id == store_id).order_by(BusinessConstraint.scope_type, BusinessConstraint.scope_id.asc().nulls_first(), BusinessConstraint.constraint_type, BusinessConstraint.version, BusinessConstraint.id)))

    def get_effective_budget(self, store_id: UUID, day: date) -> BusinessConstraint | None:
        return self._session.scalars(select(BusinessConstraint).where(
            BusinessConstraint.store_id == store_id, BusinessConstraint.scope_type == "STORE",
            BusinessConstraint.scope_id.is_(None), BusinessConstraint.constraint_type == "BUDGET_LIMIT",
            BusinessConstraint.active.is_(True), BusinessConstraint.effective_from <= day,
            BusinessConstraint.effective_to.is_(None) | (BusinessConstraint.effective_to >= day),
        )).one_or_none()

    def list_active_constraints(self, store_id: UUID, day: date) -> list[BusinessConstraint]:
        return list(self._session.scalars(select(BusinessConstraint).where(
            BusinessConstraint.store_id == store_id, BusinessConstraint.active.is_(True),
            BusinessConstraint.effective_from <= day,
            BusinessConstraint.effective_to.is_(None) | (BusinessConstraint.effective_to >= day),
        ).order_by(BusinessConstraint.scope_type, BusinessConstraint.scope_id.asc().nulls_first(), BusinessConstraint.constraint_type, BusinessConstraint.version, BusinessConstraint.id)))

    def get_effective_safety_stock(self, store_id: UUID, ingredient_id: UUID, day: date) -> BusinessConstraint | None:
        return self._session.scalars(select(BusinessConstraint).where(
            BusinessConstraint.store_id == store_id, BusinessConstraint.scope_type == "INGREDIENT",
            BusinessConstraint.scope_id == ingredient_id, BusinessConstraint.constraint_type == "MIN_SAFETY_STOCK",
            BusinessConstraint.active.is_(True), BusinessConstraint.effective_from <= day,
            BusinessConstraint.effective_to.is_(None) | (BusinessConstraint.effective_to >= day),
        )).one_or_none()
