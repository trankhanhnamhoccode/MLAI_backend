from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Persistence metadata for future models; no business tables exist yet."""
