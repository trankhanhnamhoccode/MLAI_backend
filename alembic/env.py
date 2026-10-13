from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import create_database_engine
import app.models  # Register the accepted persistence tables in Base.metadata.


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = Settings()
    url = make_url(settings.database_url)
    # Test migrations, including subprocess callers, recheck effective identity.
    # Normal development/demo migration behavior is unchanged.
    if settings.environment == "test":
        from scripts.dev import validate_reset_target
        validate_reset_target(settings)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            if settings.environment == "test":
                identity = connection.execute(text('SELECT current_database(), current_user')).one()
                if identity[0] != url.database or (url.database == 'shelfcash_integration_test' and identity[1] != url.username):
                    raise ValueError('Effective test migration identity mismatch')
                connection.rollback()
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
