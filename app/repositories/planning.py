"""Concrete scoped access. Caller owns short transactions; no update/delete API."""
from datetime import date, datetime
from collections.abc import Iterator
from sqlalchemy import select, tuple_, func, String, cast, literal
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy.dialects.postgresql import insert
from app.models.planning_run import PlanningRun
from app.application.planning_serialization import digest, exact_json, canonical_bytes
from app.application.contracts.planning_run import PlanningRunRecord, PlanningPersistenceError


class PlanningRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, store_id: UUID, run_id: UUID, *, lock: bool = False) -> PlanningRun | None:
        query = select(PlanningRun).where(PlanningRun.store_id==store_id,PlanningRun.id==run_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(query)

    def by_key(self, actor_id: UUID, store_id: UUID, key_digest: str) -> PlanningRun | None:
        return self.session.scalar(select(PlanningRun).where(PlanningRun.actor_id==actor_id,
            PlanningRun.store_id==store_id,PlanningRun.operation=='C02',PlanningRun.key_digest==key_digest))

    def owning_store(self, run_id: UUID) -> UUID | None:
        """Identity only; the caller authorizes before reading retained content."""
        return self.session.scalar(select(PlanningRun.store_id).where(PlanningRun.id==run_id))

    def next_public_queued(self) -> PlanningRun | None:
        return self.session.scalars(select(PlanningRun).where(PlanningRun.status=='queued',
            PlanningRun.record_json.has_key('public_acceptance'))
            .order_by(PlanningRun.accepted_at,PlanningRun.id).limit(1)).first()

    def public_running_page(self, after: tuple[datetime, UUID] | None) -> tuple[PlanningRun, ...]:
        query=select(PlanningRun).where(PlanningRun.status=='running',
            PlanningRun.record_json.has_key('public_acceptance'))
        if after is not None:query=query.where(tuple_(PlanningRun.accepted_at,PlanningRun.id)>after)
        return tuple(self.session.scalars(query.order_by(PlanningRun.accepted_at,PlanningRun.id).limit(100)))

    @staticmethod
    def _history_conditions(store_id: UUID, statuses: tuple[str, ...], start_from: date | None, start_to: date | None):
        conditions=[PlanningRun.store_id==store_id,PlanningRun.record_json.has_key('public_acceptance')]
        if statuses:conditions.append(PlanningRun.status.in_(statuses))
        forecast_start=cast(PlanningRun.record_json['request']['forecast_start_date'].astext,String)
        if start_from:conditions.append(forecast_start>=str(start_from))
        if start_to:conditions.append(forecast_start<=str(start_to))
        return conditions

    def history_revision(self, store_id: UUID, statuses: tuple[str, ...], start_from: date | None, start_to: date | None) -> tuple[int, str]:
        stamp=cast(PlanningRun.id,String)+':'+cast(PlanningRun.revision,String)+':'+PlanningRun.record_digest
        metadata=func.coalesce(func.string_agg(stamp,aggregate_order_by(literal(','),PlanningRun.id)),'')
        total,revision=self.session.execute(select(func.count(),
            func.encode(func.sha256(func.convert_to(metadata,'UTF8')),'hex'))
            .where(*self._history_conditions(store_id,statuses,start_from,start_to))).one()
        return total,revision

    def history_page(self, store_id: UUID, statuses: tuple[str, ...], start_from: date | None, start_to: date | None,
                     offset: int, limit: int) -> Iterator[PlanningRun]:
        return iter(self.session.scalars(select(PlanningRun)
            .where(*self._history_conditions(store_id,statuses,start_from,start_to))
            .order_by(PlanningRun.accepted_at.desc(),PlanningRun.id.desc()).offset(offset).limit(limit)
            .execution_options(yield_per=1)))

    def accept(self, record: PlanningRunRecord) -> PlanningRun | None:
        value = exact_json(record)
        identifier = self.session.scalar(insert(PlanningRun).values(id=record.run_id,
            actor_id=record.actor_id,store_id=record.store_id,operation='C02',
            key_digest=record.key_digest,request_digest=record.request_digest,status='queued',
            accepted_at=record.accepted_at,revision=1,record_json=value,
            record_digest=digest('aggregate',value)).on_conflict_do_nothing(
                constraint='uq_planning_runs_key_scope').returning(PlanningRun.id))
        return self.get(record.store_id,identifier) if identifier else self.by_key(record.actor_id,record.store_id,record.key_digest)

    def _replace_locked(self, row: PlanningRun, record: PlanningRunRecord) -> None:
        # Only called by fenced lifecycle writer after verifying the locked aggregate.
        record = PlanningRunRecord.model_validate(record)
        new = exact_json(record)
        old = row.record_json
        immutable = ('run_id','actor_id','store_id','operation','key_digest','request_digest',
                     'request','resolution','accepted_at','storage_version','package_schema_version','public_acceptance')
        if any(canonical_bytes(old.get(k))!=canonical_bytes(new.get(k)) for k in immutable):
            raise PlanningPersistenceError('ACCEPTANCE_IMMUTABLE',row.id,row.status)
        if row.status in {'completed','failed'}:
            raise PlanningPersistenceError('TERMINAL_CONFLICT',row.id,row.status)
        allowed = {'queued': {'running'}, 'running': {'running','completed','failed'}}
        if record.status not in allowed[row.status]:
            raise PlanningPersistenceError('INVALID_TRANSITION',row.id,row.status)
        if old['started_at'] is not None and canonical_bytes(old['started_at'])!=canonical_bytes(new['started_at']):
            raise PlanningPersistenceError('START_IMMUTABLE',row.id,row.status)
        if row.status=='running' and canonical_bytes(old['claim'])!=canonical_bytes(new['claim']):
            raise PlanningPersistenceError('STALE_CLAIM',row.id,row.status)
        if record.result is not None and old['capture'] is None:
            raise PlanningPersistenceError('INPUT_NOT_RETAINED',row.id,row.status)
        if old['capture'] is not None and canonical_bytes(old['capture'])!=canonical_bytes(new['capture']):
            raise PlanningPersistenceError('INPUT_ALREADY_RETAINED',row.id,row.status)
        if old['capture'] is not None and canonical_bytes(old['declarations'])!=canonical_bytes(new['declarations']):
            raise PlanningPersistenceError('INPUT_ALREADY_RETAINED',row.id,row.status)
        if old.get('public_capture') is not None and canonical_bytes(old['public_capture'])!=canonical_bytes(new.get('public_capture')):
            raise PlanningPersistenceError('INPUT_ALREADY_RETAINED',row.id,row.status)
        prior_audit=old.get('public_audit',[])
        if new.get('public_audit',[])[:len(prior_audit)]!=prior_audit:
            raise PlanningPersistenceError('AUDIT_IMMUTABLE',row.id,row.status)
        row.status = record.status
        row.revision += 1
        row.record_json = new
        row.record_digest = digest('aggregate',row.record_json)
