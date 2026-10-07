from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Minimal declarative metadata shared by explicit persistence models."""
