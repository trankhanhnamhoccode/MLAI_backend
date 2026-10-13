"""Concrete serving/reuse SQL queries, no model execution."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Store
from app.models.model_serving import ModelServingConfiguration,ForecastServingIdentity


def serving_row(s: Session,store: UUID) -> ModelServingConfiguration | None:
    return s.get(ModelServingConfiguration,store)


def lock_store(s: Session,store: UUID) -> Store | None:
    return s.scalar(select(Store).where(Store.id==store).with_for_update())


def reuse_candidates(s: Session,store: UUID,digest: str) -> tuple[ForecastServingIdentity,...]:
    return tuple(s.scalars(select(ForecastServingIdentity).where(ForecastServingIdentity.store_id==store,
        ForecastServingIdentity.identity_digest==digest).order_by(ForecastServingIdentity.forecast_run_id)))
