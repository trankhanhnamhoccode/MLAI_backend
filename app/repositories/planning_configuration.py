"""Concrete Store configuration queries; caller owns snapshot/transaction."""
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Product
from app.models.planning_configuration import PlanningBudget, PlanningDefault, SavedRequirement
from app.application.contracts.planning_setup import DefaultRequirementsRecord


def fence_save_products(session: Session) -> None:
    session.execute(text('LOCK TABLE products IN SHARE ROW EXCLUSIVE MODE'))


def configuration_rows(session: Session, store: UUID) -> tuple[PlanningDefault | None,PlanningBudget | None,tuple[Product,...]]:
    return (session.get(PlanningDefault, store), session.get(PlanningBudget, store),
            tuple(session.scalars(select(Product).where(Product.store_id == store).order_by(Product.id))))


def default_record(row: PlanningDefault | None) -> DefaultRequirementsRecord | None:
    return DefaultRequirementsRecord(version=row.version, updated_at=row.updated_at, requirements=row.requirements_json) if row else None


def saved_row(session: Session, store: UUID, ident: UUID) -> SavedRequirement | None:
    return session.scalar(select(SavedRequirement).where(SavedRequirement.store_id == store, SavedRequirement.id == ident))


def active_saved(session: Session, store: UUID) -> tuple[SavedRequirement,...]:
    return tuple(session.scalars(select(SavedRequirement).where(SavedRequirement.store_id == store,
        SavedRequirement.state == 'active').order_by(SavedRequirement.updated_at.desc(),SavedRequirement.id)))
