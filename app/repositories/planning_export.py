"""PDF persistence only. The caller owns Session, authority and transactions."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import select, func, tuple_
from sqlalchemy.orm import Session
from app.models import PlanningExport
from app.application.contracts.planning_export import ExportRecord
from app.application.planning_serialization import exact_json, digest


class PlanningExportRepository:
    def __init__(self, session: Session):
        self.session=session

    def get(self, export_id: UUID, *, lock: bool = False) -> PlanningExport | None:
        if not lock:return self.session.get(PlanningExport,export_id)
        return self.session.scalar(select(PlanningExport).where(PlanningExport.id==export_id)
            .with_for_update().execution_options(populate_existing=True))

    def by_key(self, actor_id: UUID, store_id: UUID, run_id: UUID, key_digest: str) -> PlanningExport | None:
        return self.session.scalar(select(PlanningExport).where(PlanningExport.actor_id==actor_id,
            PlanningExport.store_id==store_id,PlanningExport.run_id==run_id,PlanningExport.key_digest==key_digest))

    def outstanding_count(self, store_id: UUID) -> int:
        return self.session.scalar(select(func.count()).select_from(PlanningExport)
            .where(PlanningExport.store_id==store_id,PlanningExport.status.in_(('queued','running'))))

    def next_queued_id(self) -> UUID | None:
        return self.session.scalar(select(PlanningExport.id).where(PlanningExport.status=='queued')
            .order_by(PlanningExport.created_at,PlanningExport.id).limit(1))

    def running_page(self, after: tuple[datetime, UUID] | None) -> tuple[PlanningExport, ...]:
        query=select(PlanningExport).where(PlanningExport.status=='running')
        if after is not None:query=query.where(tuple_(PlanningExport.created_at,PlanningExport.id)>after)
        return tuple(self.session.scalars(query.order_by(PlanningExport.created_at,PlanningExport.id).limit(100)))

    def by_job(self, job_id: UUID) -> PlanningExport | None:
        return self.session.scalar(select(PlanningExport).where(PlanningExport.job_id==job_id))

    def add_accepted(self, record: ExportRecord) -> None:
        self.session.add(PlanningExport(id=record.export_id,job_id=record.job_id,run_id=record.run_id,
            store_id=record.store_id,actor_id=record.actor_id,key_digest=record.key_digest,
            request_digest=record.request_digest,status='queued',created_at=record.created_at,
            revision=1,record_json=exact_json(record),record_digest=digest('export',record)))
