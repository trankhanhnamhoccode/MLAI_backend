"""One owned, read-only MVCC snapshot; configured before first SQL/autobegin."""

from contextlib import contextmanager
from app.infrastructure.database.auth_session import auth_session
from app.repositories.public_reads import PublicReadRepository


@contextmanager
def public_read_snapshot(engine):
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True
    ) as connection:
        with auth_session(connection) as session:
            yield PublicReadRepository(session)
