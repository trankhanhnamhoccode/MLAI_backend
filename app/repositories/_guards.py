"""Small staging guards; no CRUD, transaction or domain framework."""
from uuid import UUID

from sqlalchemy import inspect

from app.infrastructure.database.base import Base


def require_store(expected: UUID, actual: UUID) -> None:
    if actual != expected:
        raise ValueError("Row does not belong to the requested Store")


def require_new(row: Base) -> None:
    if not inspect(row).transient:
        raise ValueError("Insert requires a new transient row; existing rows cannot be merged")
