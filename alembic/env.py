from pathlib import Path

from alembic import context
from sqlalchemy.engine import make_url

from app.config import BACKEND_ROOT, Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import create_database_engine


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = make_url(Settings().database_url)
    if url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            url = url.set(database=str(BACKEND_ROOT / path))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
