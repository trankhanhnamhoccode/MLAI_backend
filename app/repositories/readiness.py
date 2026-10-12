"""Detached canonical facts for IMP14; caller owns the read snapshot/commit."""
from dataclasses import dataclass
from sqlalchemy import select,text
from app.models import BusinessConstraint
from app.models.model_serving import ModelServingConfiguration
from app.repositories.import_staging import read_set_in_session,json_value
from app.repositories.planning_configuration import configuration_rows,default_record,active_saved
from app.application.planning_configuration_values import detail
from app.application.contracts.model_serving import ServingRecord
from app.application.contracts.planning_setup import BudgetCeilingRecord
from app.application.contracts.planning_setup import DefaultRequirementsRecord
from app.application.contracts.planning_configuration import SavedDetail


def fence_readiness_inputs(s):
    from app.repositories.import_staging import OPERATIONAL
    for name in sorted({m.__tablename__ for m in OPERATIONAL} | {'business_constraints'}):
        s.execute(text('LOCK TABLE "'+name+'" IN SHARE ROW EXCLUSIVE MODE'))


@dataclass(frozen=True)
class ReadinessFacts:
    snapshot: dict
    defaults: DefaultRequirementsRecord | None
    cap: BudgetCeilingRecord | None
    serving: ServingRecord | None
    saved: tuple[SavedDetail,...]


def load_readiness(s,store):
    snapshot,_=read_set_in_session(s,store)
    constraints=s.scalars(select(BusinessConstraint).where(BusinessConstraint.store_id==store).order_by(BusinessConstraint.id))
    snapshot['business_constraints']=[{c.name:json_value(getattr(row,c.name)) for c in BusinessConstraint.__table__.columns} for row in constraints]
    defaults,cap,products=configuration_rows(s,store)
    default=default_record(defaults)
    budget=BudgetCeilingRecord(amount=cap.amount,currency=snapshot['stores'][0]['currency'],version=cap.version,
        updated_at=cap.updated_at,provenance='Owner-configured Store ceiling') if cap else None
    row=s.get(ModelServingConfiguration,store)
    serving=ServingRecord(version=row.version,policy=row.configuration_json) if row else None
    saved=tuple(detail(row,default,cap,products) for row in active_saved(s,store))
    return ReadinessFacts(snapshot=snapshot,defaults=default,cap=budget,serving=serving,saved=saved)
