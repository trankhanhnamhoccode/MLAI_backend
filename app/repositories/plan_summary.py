"""Concrete queries; the application owns all transactions and authority."""
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.models.plan_summary import PlanSummaryGeneration, PlanSummaryReceipt
from app.application.planning_serialization import exact_json, digest


class SummaryRepository:
    def __init__(self, session): self.session = session

    def get(self, store, run, ident, *, lock=False):
        query = select(PlanSummaryGeneration).where(PlanSummaryGeneration.id==ident,
            PlanSummaryGeneration.store_id==store,PlanSummaryGeneration.run_id==run)
        if lock: query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def receipt(self, actor, store, run, key):
        return self.session.get(PlanSummaryReceipt,(actor,store,run,key))

    def accept(self, record, key, fingerprint):
        value = dict(id=record.generation_id,actor_id=record.actor_id,store_id=record.store_id,run_id=record.run_id,
            identity_digest=record.identity_digest,record_digest=digest('summary',record),status=record.status,
            created_at=record.created_at,record_json=exact_json(record))
        inserted = self.session.scalar(insert(PlanSummaryGeneration).values(**value).on_conflict_do_nothing(
            index_elements=['actor_id','store_id','run_id','identity_digest'],index_where=PlanSummaryGeneration.status!='failed').returning(PlanSummaryGeneration.id))
        ident = inserted or self.session.scalar(select(PlanSummaryGeneration.id).where(
            PlanSummaryGeneration.actor_id==record.actor_id,PlanSummaryGeneration.store_id==record.store_id,
            PlanSummaryGeneration.run_id==record.run_id,PlanSummaryGeneration.identity_digest==record.identity_digest,PlanSummaryGeneration.status!='failed'))
        self.session.execute(insert(PlanSummaryReceipt).values(actor_id=record.actor_id,store_id=record.store_id,
            run_id=record.run_id,key_digest=key,request_digest=fingerprint,generation_id=ident).on_conflict_do_nothing())
        self.session.expire_all()
        return self.receipt(record.actor_id,record.store_id,record.run_id,key), bool(inserted)

    def save(self, row, record):
        row.status=record.status
        row.record_json=exact_json(record)
        row.record_digest=digest('summary',record)

    def running_count(self, store):
        return self.session.scalar(select(func.count()).select_from(PlanSummaryGeneration).where(
            PlanSummaryGeneration.store_id==store,PlanSummaryGeneration.status=='running'))
