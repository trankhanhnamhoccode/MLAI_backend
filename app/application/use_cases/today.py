"""D01 coherent, section-authorized overview of existing application facts."""
import logging
from zoneinfo import ZoneInfo
from app.application.contracts import discovery as dto
from app.application.contracts.auth import AuthError
from app.application.import_identity import content_digest
from app.application.readiness_evaluation import ACTION_READS,evaluate
from app.application.forecast_preparation import prepare_observations
from app.application.use_cases.import_staging import ImportStaging
from app.application.use_cases.mapping_submissions import drift
from app.application.use_cases.public_reads import PublicReads
from app.application.use_cases.planning_public import READ_PERMISSIONS
from app.domain.collaboration import permission_request_state
from app.infrastructure.database.auth_session import auth_session
from app.repositories import discovery as repo
from app.repositories.public_reads import PublicReadRepository
from app.repositories.planning import PlanningRepository
from app.repositories.readiness import load_readiness

log=logging.getLogger(__name__)
SECTIONS=('inventory','imports','mapping','permissions','readiness','planning')


def section(value,resource,*,updated=None,empty=False,completeness='unknown',version=None):
    return dto.TodaySection(availability='empty' if empty else 'available',value=value,updated_at=updated,
        completeness=completeness,reason_codes=(),source=dto.SectionSource(resource=resource,
            version=version or content_digest(value.model_dump(mode='json') if value is not None else None)))


def denied():
    return dto.TodaySection(availability='forbidden',value=None,updated_at=None,completeness='unknown',
        reason_codes=('PERMISSION_DENIED',),source=None)


def tasks(items,resource,limit,*,source_versions=()):
    items=sorted(items,key=lambda item:(item.updated_at,str(item.id)),reverse=True)
    return section(dto.TodayTaskList(total_count=len(items),items=tuple(items[:limit]),has_more=len(items)>limit),resource,
        updated=max((item.updated_at for item in items),default=None),empty=not items,completeness='confirmed',
        version=content_digest([[item.model_dump(mode='json') for item in items],source_versions]))


def sensitive(batches,permissions):
    if any(not set(ImportStaging._sensitive_reads(b))<=set(permissions) for b in batches):
        raise AuthError('PERMISSION_DENIED',403)


class TodayReads:
    def __init__(self,auth,planning,readiness,reads):
        self.auth,self.engine,self.planning,self.readiness,self.reads=auth,auth.engine,planning,readiness,reads

    def inventory(self,s,store,today,limit):
        rows,total,summary,_=PublicReadRepository(s).inventory(store,today,None,(),(),'name',None,limit)
        items=[]
        for row in rows[:limit]:
            stock=self.reads._stock(row)
            items.append(dto.InventoryAttentionItem(ingredient_id=stock.ingredient_id,status=stock.status,
                reason_codes=tuple(r.code for r in stock.status_reasons),usable_quantity=stock.usable_quantity,unit=stock.unit))
        value=dto.InventoryAttention(as_of_date=today,expired_lot_count=int(summary['expired_lot_count']),
            near_expiry_lot_count=int(summary['near_expiry_lot_count']),low_stock_ingredient_count=summary['low_stock_ingredient_count'],
            unknown_assessment_ingredient_count=summary['unknown_assessment_ingredient_count'],items=tuple(items),has_more=total>limit)
        return section(value,'inventory',updated=PublicReadRepository(s).updated(store,catalog=False),empty=not total,
            completeness='confirmed' if total and not summary['unknown_assessment_ingredient_count'] else 'unknown',
            version=content_digest([{k:str(v) for k,v in PublicReadRepository(s).basis(store).items()},str(today)]))

    def imports(self,s,store,actor,authority,permissions,limit):
        batches,profiles,audits,jobs=repo.import_task_sources(s,store,None if authority.role=='OWNER' else actor.user_id)
        batches=[b for b in batches if not (b.analysis_json or {}).get('completion')]
        sensitive(batches,permissions)
        profile_batch={str(p.id):p.import_id for p in profiles}
        mapping_batch={str(i['mapping_id']):b.id for b in batches for i in (b.analysis_json or {}).get('issues',())}
        updates={b.id:b.imported_at or b.created_at for b in batches}
        for record in audits:
            facts=record.record_json
            ident=next((b.id for b in batches if str(b.id)==facts.get('import_id')),None)
            ident=ident or profile_batch.get(facts.get('profile_id')) or mapping_batch.get(facts.get('mapping_id'))
            if ident in updates:updates[ident]=max(updates[ident],record.occurred_at)
        for job in jobs:
            if job.import_id in updates:updates[job.import_id]=max(updates[job.import_id],job.completed_at or job.started_at or job.created_at)
        return tasks([dto.TodayTask(type='import',id=b.id,state=b.status,updated_at=updates[b.id],allowed_actions=('open',))
                      for b in batches],'imports',limit,source_versions=[(str(b.id),b.revision,b.mapping_revision,b.file_set_version) for b in batches])

    def mapping(self,s,store,actor,authority,permissions,limit):
        records=repo.mapping_tasks(s,store,None if authority.role=='OWNER' else actor.user_id)
        sensitive([batch for _,batch,_ in records],permissions)
        items=[]
        for row,batch,profile in records:
            stale=row.state=='submitted' and drift(row,batch,profile)
            eligible=row.state=='submitted' and not stale and not batch.active_job_id and not (batch.analysis_json or {}).get('completion')
            if authority.role=='OWNER' and not eligible:continue
            items.append(dto.TodayTask(type='mapping_submission',id=row.id,state='stale' if stale else row.state,
                updated_at=row.submitted_at,allowed_actions=('open',)))
        return tasks(items,'mapping_submissions',limit,source_versions=[(str(row.id),row.version,batch.revision,profile.lifecycle_revision) for row,batch,profile in records])

    def permissions(self,s,store,actor,authority,limit):
        rows,grants=repo.permission_tasks(s,store,None if authority.role=='OWNER' else actor.user_id)
        items=[]
        for row,member,active in rows:
            state=permission_request_state(row.state,tuple(row.facts['requested_permissions']),tuple(grants[member.id]),
                eligible=member.active and member.role=='STAFF' and active)
            if state=='pending':items.append(dto.TodayTask(type='permission_request',id=row.id,state=state,
                updated_at=row.updated_at,allowed_actions=('approve','reject') if authority.role=='OWNER' else ('cancel',)))
        return tasks(items,'permission_requests',limit)

    def readiness_section(self,s,store,now,today,permissions):
        actions=tuple(a for a,required in ACTION_READS.items() if set(required)<=set(permissions))
        if not actions:return denied()
        facts=load_readiness(s,store);assessment=None
        forecast=self.readiness.forecast
        if forecast is not None and facts.serving and {'forecast','planning'}&set(actions):
            try:prepared=prepare_observations(facts,store,today)
            except AuthError as error:
                if error.code!='NO_COMPUTABLE_PRODUCTS':raise
            else:assessment=forecast.assess(prepared,facts.serving)
        value=evaluate(facts,store,now,today,actions,permissions,forecast_assessment=assessment,
            forecast_available=forecast is not None,planning_available=self.readiness.planning_available())
        # Section versions/counters are also sensitive; omit facts the actor cannot read.
        permitted={
            'catalog':'menu.read' in permissions,
            'recipes':{'menu.read','recipe.read'}<=set(permissions),
            'inventory':{'ingredient.read','inventory.read'}<=set(permissions),
            'sales':'sales.read' in permissions,
            'suppliers':{'supplier.read','procurement.cost.read'}<=set(permissions),
            'fees':'procurement.cost.read' in permissions,
            'planning_config':{'budget.read','procurement.cost.read'}<=set(permissions),
            'model_configuration':'planning.context.read' in permissions,
            'declarations':{'budget.read','procurement.cost.read','inventory.read','sales.read'}<=set(permissions),
        }
        source_versions=value.source_versions.model_copy(update={key:None for key,allowed in permitted.items() if not allowed})
        value=value.model_copy(update={'source_versions':source_versions})
        if not {'budget.read','procurement.cost.read'}<=set(permissions):
            value=value.model_copy(update={'scope_estimate':None,'history_watermark':None})
        public=value.model_dump(mode='json',exclude={'evaluated_at','data_version'})
        value=value.model_copy(update={'data_version':content_digest(public)})
        return section(value,'readiness',version=value.data_version)

    def latest(self,s,store):
        rows=list(PlanningRepository(s).history_page(store,(),None,None,0,1))
        if not rows:return section(None,'procurement_plans',empty=True,completeness='confirmed')
        record,view=self.planning.retained.read(rows[0])
        return section(dto.LatestRun(run_id=record.run_id,status=record.status,accepted_at=record.accepted_at,
            result_digest=record.result_digest,outcome=record.outcome,error_code=record.error_code),
            'procurement_plans',updated=record.finished_at or record.started_at or record.accepted_at,version=view.response_version)

    def read(self,token,store,request_id,selected=None,limit=5,snapshot_id=None):
        selected=tuple(selected.split(',')) if selected is not None else SECTIONS
        if not selected or len(set(selected))!=len(selected) or not set(selected)<=set(SECTIONS) or not 1<=limit<=20:
            raise AuthError('INVALID_FILTER',422)
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with auth_session(connection) as s:
                actor,authority,permissions=self.auth.authorize_in_session(s,token,store,())
                basis=PublicReadRepository(s).basis(store);now=self.auth.clock()
                today=now.astimezone(ZoneInfo(basis['timezone'])).date()
                required={'inventory':('inventory.read','ingredient.read'),'imports':('import.read',),
                    'mapping':('import.read','mapping.read'),'permissions':(),'readiness':(), 'planning':READ_PERMISSIONS}
                values={}
                for name in selected:
                    if not set(required[name])<=set(permissions):values[name]=denied();continue
                    try:
                        # A technical dependency failure must not abort other read sections.
                        with s.begin_nested():
                            if name=='inventory':value=self.inventory(s,store,today,limit)
                            elif name=='imports':value=self.imports(s,store,actor,authority,permissions,limit)
                            elif name=='mapping':value=self.mapping(s,store,actor,authority,permissions,limit)
                            elif name=='permissions':value=self.permissions(s,store,actor,authority,limit)
                            elif name=='readiness':value=self.readiness_section(s,store,now,today,permissions)
                            else:value=self.latest(s,store)
                        values[name]=value
                    except AuthError as error:
                        if error.code=='PERMISSION_DENIED':values[name]=denied()
                        else:raise
                    except Exception as error:
                        log.error('Today section unavailable (%s)',type(error).__name__)
                        values[name]=dto.TodaySection(availability='unavailable',value=None,updated_at=None,
                            completeness='unknown',reason_codes=('SERVICE_UNAVAILABLE',),source=None)
                data=dto.Today(store_id=store,sections=dto.TodaySections(**values))
                public=data.model_dump(mode='json',exclude_unset=True)
                if public['sections'].get('readiness',{}).get('value') is not None:
                    public['sections']['readiness']['value'].pop('evaluated_at',None)
                snapshot=content_digest([public,authority.authorization_version,str(today),basis['timezone'],limit])
                if snapshot_id is not None and snapshot_id!=snapshot:raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
                s.commit()
                return dto.TodayEnvelope(data=data,meta=dto.TodayMeta(request_id=request_id,snapshot_id=snapshot,
                    observed_at=now,as_of_date=today,timezone=basis['timezone']),error=None)
