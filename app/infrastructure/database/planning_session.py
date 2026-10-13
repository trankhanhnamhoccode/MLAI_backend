"""Owned planning Session cleanup preserving primary exceptions."""
from contextlib import contextmanager
import logging
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def secondary(primary,phase,error):
    primary.add_note(f'Planning {phase}: {type(error).__name__}; see trusted diagnostics')
    log.error('Planning %s failed',phase,exc_info=(type(error),error,error.__traceback__))


@contextmanager
def planning_session(engine):
    session = Session(engine)
    primary = None
    try:
        yield session
    except BaseException as error:
        primary = error
        raise
    finally:
        if primary is not None:
            try:
                session.rollback()
            except Exception as error:
                secondary(primary,'rollback',error)
                try: session.invalidate()
                except Exception as invalid: secondary(primary,'invalidation',invalid)
        try:
            session.close()
        except Exception as error:
            secondary(primary or error,'close',error)
            try: session.invalidate()
            except Exception as invalid: secondary(primary or error,'invalidation',invalid)
            if primary is None:
                raise
