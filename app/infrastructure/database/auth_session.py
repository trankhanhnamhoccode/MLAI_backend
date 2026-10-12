"""Owned sessions; sanitized cleanup diagnostics preserve primary errors."""
from contextlib import contextmanager
import logging
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


@contextmanager
def auth_session(engine):
    session = Session(engine, expire_on_commit=False)
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
                primary.add_note("Auth rollback failed: " + type(error).__name__)
                log.error("Auth rollback failed (%s)", type(error).__name__)
        try:
            session.close()
        except Exception as error:
            log.error("Auth close failed (%s)", type(error).__name__)
            if primary is not None:
                primary.add_note("Auth close failed: " + type(error).__name__)
            try:
                session.invalidate()
            except Exception as invalid:
                log.error("Auth invalidate failed (%s)", type(invalid).__name__)
            if primary is None:
                raise
