"""IMP11 first-upload history from retained metadata, current sensitive rights."""
from collections import Counter
from datetime import date,datetime,time,timezone
from zoneinfo import ZoneInfo
from time import sleep
from sqlalchemy.exc import OperationalError
from app.repositories.import_staging import ImportHistoryRepository
from app.application.contracts import history as dto,import_mapping as imports
from app.application.contracts.auth import AuthError
from app.application.import_identity import content_digest
from app.application.history_cursor import page
from app.infrastructure.database.auth_session import auth_session

# Only approved category meanings; other schemas remain uncategorized.
CATEGORIES={'sales':'sales','inventory_count':'inventory','recipes':'recipes',
    'suppliers':'supplier','supplier_terms':'supplier','payable_fees':'supplier',
    'calendar_events':'calendar','promotion_observations':'sales',
    'usage_history':'usage','purchase_history':'purchase'}
MAX_HISTORY_BATCHES=1000


def history_status(batch):
    completion=(batch.analysis_json or {}).get('completion')
    if completion:
        if content_digest(completion)!=batch.analysis_json.get('completion_digest'):raise AuthError('SOURCE_INTEGRITY_ERROR',409)
        return imports.ImportCompletion.model_validate(completion).status
    if batch.status=='failed':return 'failed'
    return 'in_progress'


class ImportHistoryReads:
    def __init__(self,staging):
        self.staging,self.auth,self.engine=staging,staging.auth,staging.engine

    def _read(self,token,store,start,end,category,status,q,build):
        # H01/H02 run concurrently in the real FE. Session sliding expiry writes
        # can conflict under REPEATABLE READ even though the business read is pure.
        # Retry the entire rolled-back read with fresh authority/snapshot, only for
        # PostgreSQL serialization failure; never retry mutations/other failures.
        for attempt in range(5):
            try:
                return self._read_once(token,store,start,end,category,status,q,build)
            except OperationalError as error:
                if getattr(error.orig,'sqlstate',None)!='40001' or attempt==4:
                    raise
                # Let the concurrent session writer finish before taking a new
                # snapshot. Total backoff is bounded to 0.75 seconds.
                sleep(0.05 * (2 ** attempt))

    def _read_once(self,token,store,start,end,category,status,q,build):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with auth_session(connection) as s:
                actor,authority,_=self.auth.authorize_in_session(s,token,store,('import.read',))
                repo=ImportHistoryRepository(s)
                timezone_name=repo.store_timezone(store)
                tz=ZoneInfo(timezone_name)
                lower=datetime.combine(start,time.min,tz).astimezone(timezone.utc)
                upper=datetime.combine(end,time.min,tz).astimezone(timezone.utc)
                batches=repo.batches(store,lower,upper,MAX_HISTORY_BATCHES+1)
                if len(batches)>MAX_HISTORY_BATCHES:raise AuthError('RESOURCE_LIMIT_EXCEEDED',413)
                # Counts must not leak batches that current grants cannot read.
                # Whole-response denial follows existing I04 sensitive authority.
                for batch in batches:self.staging._authority(s,token,batch,'import.read',sensitive=True)
                ids=[b.id for b in batches]
                files=repo.uploaded_files(ids)
                grouped={b.id:[] for b in batches}
                for f in files:grouped[f.import_id].append(f)
                matched=[];revision=[]
                for batch in batches:
                    normalized=history_status(batch)
                    sheets=(batch.analysis_json or {}).get('sheets',[])
                    categories={}
                    for sh in sheets:
                        if not sh.get('ignored'):
                            category_name=CATEGORIES.get(sh.get('selected_type'))
                            if category_name:categories.setdefault(sh['file_id'],set()).add(category_name)
                    matching_file=any((category is None or category in categories.get(str(f.id),set())) and
                        (q is None or q.casefold() in f.filename.casefold()) for f in grouped[batch.id])
                    revision.append([str(batch.id),batch.revision,normalized,
                        [[str(f.id),f.filename,sorted(categories.get(str(f.id),set()))] for f in grouped[batch.id]]])
                    if (status is None or normalized==status) and matching_file:
                        matched.append(dto.ImportHistoryItem(import_id=batch.id,display_number='IMP-'+str(batch.id),data_date=batch.data_date,
                            imported_at=batch.imported_at,file_count=len(grouped[batch.id]),status=normalized))
                identity=[str(actor.user_id),str(store),authority.authorization_version,str(start),str(end),timezone_name,category,status,q]
                result=build(matched,len(batches),timezone_name,identity,content_digest(revision))
                s.commit()
                return result

    def calendar(self,token,store,month,category,status,q,request_id):
        try:
            start=date.fromisoformat(month+'-01')
            if start.strftime('%Y-%m')!=month:raise ValueError()
            end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
        except (ValueError,OverflowError):raise AuthError('INVALID_MONTH',422) from None
        def build(items,total,tz,identity,revision):
            counts=Counter(i.imported_at.astimezone(ZoneInfo(tz)).date() for i in items)
            return dto.HistoryEnvelope[dto.ImportCalendar,dto.HistoryMeta](data=dto.ImportCalendar(month=month,timezone=tz,
                matched_import_count=len(items),unfiltered_import_count=total,
                days=tuple(dto.CalendarDay(date=d,import_count=n) for d,n in sorted(counts.items()))),meta=dto.HistoryMeta(request_id=request_id),error=None)
        return self._read(token,store,start,end,category,status,q,build)

    def history(self,token,store,day,category,status,q,limit,cursor,request_id):
        from datetime import timedelta
        try:end=day+timedelta(days=1)
        except OverflowError:raise AuthError('INVALID_DATE',422) from None
        def build(items,total,tz,identity,revision):
            rows,pagination=page(self.auth.cursor_signer,token,'import-history',identity+[limit],revision,items,limit,cursor)
            return dto.HistoryEnvelope[dto.ImportHistory,dto.ImportHistoryMeta](data=dto.ImportHistory(items=tuple(rows)),
                meta=dto.ImportHistoryMeta(request_id=request_id,pagination=pagination,unfiltered_date_count=total),error=None)
        return self._read(token,store,day,end,category,status,q,build)
