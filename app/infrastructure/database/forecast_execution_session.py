"""Concrete S2.3 owned-Session cleanup and trusted error diagnostics."""
from collections.abc import Iterator
from contextlib import contextmanager
import logging

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session


_logger = logging.getLogger(__name__)


def _note_secondary(primary: BaseException, phase: str, secondary: BaseException) -> None:
    # Notes contain only classification; raw diagnostics stay in trusted logs.
    primary.add_note(f'S2.3 {phase} failed: {type(secondary).__name__}; see trusted diagnostics.')
    _logger.error('S2.3 %s failed', phase,
                  exc_info=(type(secondary), secondary, secondary.__traceback__))


@contextmanager
def _execution_session(bind: Engine | Connection | None) -> Iterator[Session]:
    """Owned S2.3 Session; cleanup must not replace an active primary error."""
    session = Session(bind=bind)
    primary: BaseException | None = None
    try:
        yield session
    except BaseException as error:
        primary = error
        raise
    finally:
        if primary is not None:
            try:
                session.rollback()
            except Exception as cleanup_error:
                _note_secondary(primary, 'rollback', cleanup_error)
                try:
                    session.invalidate()
                except Exception as invalidation_error:
                    _note_secondary(primary, 'invalidation after rollback', invalidation_error)
        try:
            session.close()
        except Exception as cleanup_error:
            active = primary if primary is not None else cleanup_error
            _note_secondary(active, 'close', cleanup_error)
            try:
                session.invalidate()
            except Exception as invalidation_error:
                _note_secondary(active, 'invalidation after close', invalidation_error)
            if primary is None:
                raise
