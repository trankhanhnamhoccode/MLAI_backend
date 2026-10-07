"""Purpose-specific execution diagnostics; no model binary or evaluation/provenance bag."""
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ForecastExecutionMetadata(Base):
    __tablename__ = 'forecast_execution_metadata'
    __table_args__ = (
        ForeignKeyConstraint(['forecast_run_id','store_id'], ['forecast_runs.id','forecast_runs.store_id'],
            name='fk_forecast_execution_metadata_run_store', ondelete='RESTRICT'),
        CheckConstraint("jsonb_typeof(details_json) = 'object'", name='ck_forecast_execution_metadata_object'),
        CheckConstraint("details_json ? 'schema_version' AND jsonb_typeof(details_json->'schema_version') = 'number' AND details_json->>'schema_version' = '1'", name='ck_forecast_execution_metadata_version'),
    )
    forecast_run_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    store_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
