from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import ConnectionPoolEntry

from app.config import BACKEND_ROOT, Settings


def create_database_engine(settings: Settings) -> Engine:
    """Build a synchronous SQLite engine for migration/integration boundaries."""
    url = make_url(settings.database_url)
    if url.database and url.database != ":memory:":
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = BACKEND_ROOT / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(database_path))

    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(
        connection: Connection, _record: ConnectionPoolEntry
    ) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
