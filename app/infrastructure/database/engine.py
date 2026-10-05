from sqlalchemy import Engine, create_engine

from app.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Construct a synchronous PostgreSQL engine; connect only on DB operations."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
