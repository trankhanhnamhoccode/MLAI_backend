"""Explicit supported Store serving selection and immutable forecast reuse pins."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime,ForeignKey,String,ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.infrastructure.database.base import Base


class ModelServingConfiguration(Base):
    __tablename__='model_serving_configurations'
    store_id: Mapped[UUID]=mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),primary_key=True)
    version: Mapped[str]=mapped_column(String(128),nullable=False)
    configuration_json: Mapped[dict]=mapped_column(JSONB,nullable=False)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    operator_reference: Mapped[str]=mapped_column(String(200),nullable=False)
    evidence_reference: Mapped[str]=mapped_column(String(1000),nullable=False)


class ForecastServingIdentity(Base):
    __tablename__='forecast_serving_identities'
    __table_args__=(ForeignKeyConstraint(['forecast_run_id','store_id'],['forecast_runs.id','forecast_runs.store_id'],ondelete='RESTRICT'),)
    forecast_run_id: Mapped[UUID]=mapped_column(primary_key=True)
    store_id: Mapped[UUID]=mapped_column(ForeignKey('stores.id',ondelete='RESTRICT'),nullable=False,index=True)
    identity_digest: Mapped[str]=mapped_column(String(100),nullable=False,index=True)
    identity_json: Mapped[dict]=mapped_column(JSONB,nullable=False)
