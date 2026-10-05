"""Internal errors; future transports decide their own status mapping."""
from enum import Enum
from sqlalchemy.exc import IntegrityError


class ErrorCategory(str, Enum):
    VALIDATION_ERROR = 'VALIDATION_ERROR'
    NOT_FOUND = 'NOT_FOUND'
    CONFLICT = 'CONFLICT'
    INVALID_LIFECYCLE = 'INVALID_LIFECYCLE'


class ApplicationError(Exception):
    def __init__(self, category: ErrorCategory, message: str) -> None:
        self.category = category
        super().__init__(message)


def known_conflict(error: IntegrityError, constraint: str, *, sqlstate: str = '23505') -> ApplicationError | None:
    """Translate only an exact known PostgreSQL unique/exclusion failure."""
    original = error.orig
    if (getattr(original, 'sqlstate', None) == sqlstate
            and getattr(getattr(original, 'diag', None), 'constraint_name', None) == constraint):
        return ApplicationError(ErrorCategory.CONFLICT, 'Canonical record already exists')
    return None
